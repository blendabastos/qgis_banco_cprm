# -*- coding: utf-8 -*-
"""
tarefa_xyz.py — Converte XYZ em tabela de pontos, em segundo plano.

Roda como QgsTask pela mesma razao do download, so que mais forte: o maior
arquivo do acervo, o 1112_MagLine.XYZ, tem 12,4 GB e cerca de 68 milhoes de
pontos. Medido no GDAL do QGIS 4.0.1, sao 53 mil pontos por segundo — perto de
21 minutos. Isso na thread da interface congelaria o QGIS a ponto de o Windows
oferecer encerrar o programa.

Como QgsTask, o usuario ve a barra de progresso do QGIS, pode cancelar, e pode
continuar trabalhando enquanto converte.
"""

from pathlib import Path

from qgis.core import QgsTask, QgsMessageLog, Qgis
from qgis.PyQt.QtCore import pyqtSignal

from . import xyz
from .pacote import caminho_para_abrir

ETIQUETA = "Acervo CPRM"


def registrar(msg, nivel=Qgis.Info):
    QgsMessageLog.logMessage(msg, ETIQUETA, nivel)


class TarefaConverterXyz(QgsTask):
    """
    Converte uma lista de (Esquema, caminho_de_saida).

    Sinais, emitidos na thread principal pelo `finished` do QgsTask:
        concluido(list)   — lista de (caminho_saida, n_pontos, problemas)
        falhou(str)
    """

    concluido = pyqtSignal(list)
    falhou = pyqtSignal(str)

    #: Emitido a cada lote gravado: (texto para a barra, pontos acumulados).
    #:
    #: A `QgsTask` ja tem `progressChanged`, mas ela e so um numero. O usuario
    #: precisa saber QUAL arquivo esta rodando e quantos pontos ja sairam —
    #: sem isso, uma conversao de 20 minutos parece um plugin travado.
    andamento = pyqtSignal(str, int)

    def __init__(self, trabalhos, formato="Parquet", apagar_origem=False):
        super().__init__("Convertendo XYZ aerogeofísico", QgsTask.CanCancel)
        self.trabalhos = list(trabalhos)
        self.formato = formato
        self.apagar_origem = apagar_origem
        self.liberado = 0          # bytes de XYZ original apagados
        self.resultados = []
        self.erro = ""
        self._pesos = []
        self._posicao = (1, len(self.trabalhos))

    def run(self):
        """Roda FORA da thread principal: nada de Qt de interface aqui."""
        try:
            self._pesos = [self._tamanho(esq) for esq, _ in self.trabalhos]
            total = sum(self._pesos) or 1
            feito = 0
            for i, (esq, destino) in enumerate(self.trabalhos):
                if self.isCanceled():
                    return True
                self._posicao = (i + 1, len(self.trabalhos))
                r = self._converter_um(esq, destino, feito, total)
                if r is None:
                    return True          # cancelado no meio do arquivo
                self.resultados.append(r)
                feito += self._pesos[i]
                self.setProgress(100.0 * feito / total)
            return True
        except Exception as e:                      # noqa: BLE001
            self.erro = "%s: %s" % (type(e).__name__, e)
            registrar(self.erro, Qgis.Critical)
            return False

    def _converter_um(self, esq, destino, feito, total):
        origem = Path(esq.arquivo)
        tamanho = self._tamanho(esq)

        def abrir():
            return open(caminho_para_abrir(origem), "r", encoding="latin-1")

        atual, quantos = getattr(self, "_posicao", (1, 1))
        prefixo = ("%d de %d · " % (atual, quantos)) if quantos > 1 else ""

        def progresso(fracao, n):
            self.setProgress(100.0 * (feito + fracao * tamanho) / total)
            self.andamento.emit(
                "%s%s — %s pontos" % (prefixo, origem.name,
                                      "{:,}".format(n).replace(",", ".")),
                n)

        # Primeiro sinal antes de ler qualquer byte: num arquivo de 12 GB o
        # primeiro lote so fecha depois de uns segundos, e ate la a barra
        # ficaria parada em zero sem dizer o que esta fazendo.
        self.andamento.emit("%s%s — lendo…" % (prefixo, origem.name), 0)

        destino = Path(destino)
        # Apaga TODA saida anterior desta origem, em qualquer formato — nao so
        # a que estamos prestes a gravar.
        #
        # Converter de novo escolhendo outro formato deixava a anterior ali: o
        # projeto 1117 acabou com o .parquet de 460 MB E o .gpkg de 2,61 GB do
        # mesmo arquivo, os dois aparecendo como camada para adicionar. Uma
        # conversao interrompida tambem deixa arquivo pela metade, e o driver
        # do Parquet nao sobrescreve.
        for velho in xyz.saidas_existentes(origem):
            try:
                velho.unlink()
                registrar("removida saída anterior: %s" % velho.name)
            except OSError as e:
                registrar("não consegui remover %s: %s" % (velho.name, e),
                          Qgis.Warning)

        r = xyz.converter(
            abrir, esq, caminho_para_abrir(destino), formato=self.formato,
            nome_camada=origem.stem, progresso=progresso,
            cancelado=self.isCanceled, tamanho_total=tamanho)

        if r["cancelado"]:
            try:
                Path(destino).unlink()
            except OSError:
                pass
            return None

        registrar("%s -> %s: %d pontos" % (origem.name, destino.name, r["n"]))
        for p in r["problemas"]:
            registrar("%s: %s" % (origem.name, p), Qgis.Warning)

        if self.apagar_origem and not r["problemas"] and r["n"] > 0:
            # So depois de uma conversao limpa. Apagar o original quando a
            # verificacao acusou algo deixaria o usuario sem o dado bruto
            # justamente no caso em que ele vai precisar conferir.
            try:
                origem.unlink()
                self.liberado += tamanho
                registrar("apagado o XYZ original: %s" % origem.name)
            except OSError as e:
                registrar("não consegui apagar %s: %s" % (origem.name, e),
                          Qgis.Warning)

        return (destino, r["n"], r["problemas"])

    @staticmethod
    def _tamanho(esq):
        try:
            return max(1, Path(esq.arquivo).stat().st_size)
        except OSError:
            return 1

    def finished(self, ok):
        """Roda na thread principal — aqui pode emitir sinal para a interface."""
        if self.isCanceled():
            self.falhou.emit("cancelado")
        elif ok:
            self.concluido.emit(self.resultados)
        else:
            self.falhou.emit(self.erro or "erro desconhecido na conversão")
