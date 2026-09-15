# -*- coding: utf-8 -*-
"""
baixador.py — Download do pacote em segundo plano, com extracao.

Roda como QgsTask porque o maior SIG do acervo tem 1,3 GB: baixar na thread da
interface congela o QGIS e o Windows marca "nao esta respondendo". O QgsTask
tambem da barra de progresso e botao de cancelar sem trabalho extra.

A rede passa pelo QgsNetworkAccessManager, nao pelo urllib: o NAM ja respeita
o proxy, os certificados e o timeout configurados pelo usuario. Numa rede
institucional, urllib falharia sem explicacao.
"""

import os
import zipfile
from pathlib import Path

from qgis.core import QgsTask, QgsMessageLog, Qgis
from qgis.PyQt.QtCore import pyqtSignal, QUrl, QEventLoop
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

from . import pacote
from .catalogo import limpar_nome, bytes_legivel as legivel
from .config import EXTENSOES_ARQUIVO_MORTO

MIN_BYTES = 64          # abaixo disso e pagina de erro, nao arquivo
ETIQUETA = "Acervo CPRM"


def registrar(msg: str, nivel=Qgis.MessageLevel.Info):
    QgsMessageLog.logMessage(msg, ETIQUETA, nivel)


class ErroDownload(Exception):
    pass


def caminhos_do_pacote(camada, pasta_destino):
    r"""
    Onde o pacote fica em disco: (arquivo_baixado, pasta_do_pacote).

    Nem tudo no acervo e ZIP: 112 arquivos sao .las ou .jp2 soltos e 129 sao
    planilhas .xlsx/.xls de geoquimica. Forcar a extensao .zip renomeava esses
    arquivos e a extracao morria com BadZipFile. Entao respeitamos o nome real
    do servidor e decidimos pelo conteudo, nao pela extensao.

    O arquivo baixado vai DENTRO da pasta do pacote. Assim "ja baixado" e a
    mesma pergunta nos dois casos — a pasta existe e tem conteudo —, seja ela
    o resultado de uma extracao ou apenas o abrigo de um arquivo solto.

    UM nivel so sob o destino, e de proposito. O plugin ja espelhou a arvore de
    quatro niveis do acervo: medido sobre os 5.258 pacotes do catalogo, isso
    dava mediana de 209 caracteres e maximo de 333, com 267 pacotes passando
    dos 260 do Windows ANTES de o ZIP abrir. Era a causa de "Nenhum arquivo que
    o QGIS abra neste pacote" — acima de 260, rglob devolve lista vazia calada.

    Tambem nao ha pasta por tipo. Agrupar e escolha de quem usa, nao nossa, e
    cada nivel que inventamos e caractere gasto no orcamento dos 260.

    O prefixo \\?\ (ver pacote.py) continua valendo para o que sobra: um
    destino longo escolhido pelo usuario, e os nomes internos dos ZIP, que quem
    escolhe e o SGB.

    Funcao pura, sem Qt: o painel a chama a cada mudanca de selecao.
    """
    nome = limpar_nome(camada.nome_arquivo or f"{camada.id}.zip", 90)
    raiz = nome.rsplit(".", 1)[0] if "." in nome else nome
    pasta = Path(pasta_destino) / limpar_nome(raiz, 80)
    return pasta / nome, pasta


def pacote_em_disco(camada, pasta_destino) -> bool:
    """True se o pacote ja foi baixado e extraido."""
    _, pasta = caminhos_do_pacote(camada, pasta_destino)
    return pacote.pasta_tem_conteudo(pasta)


class TarefaBaixar(QgsTask):
    """
    Baixa, verifica e extrai um pacote.

    Sinais (emitidos na thread principal pelo `finished` do QgsTask):
        concluido(str pasta_extraida)
        falhou(str mensagem)
    """

    concluido = pyqtSignal(str)
    falhou = pyqtSignal(str)

    #: Texto para a barra de progresso: "142,3 MB de 365,6 MB".
    #:
    #: A `QgsTask` ja tem `progressChanged`, mas ela e so um numero, e o
    #: indicador do canto inferior direito do QGIS e discreto demais para um
    #: pacote de 1,6 GB. Quem esta esperando precisa ver quanto falta.
    andamento = pyqtSignal(str, int)

    def __init__(self, camada, pasta_destino: Path, forcar: bool = False):
        super().__init__(f"Baixando {camada.titulo[:50]}", QgsTask.Flag.CanCancel)
        self.camada = camada
        self.forcar = forcar        # ignora o que ja esta em disco
        self.arquivo, self.pasta_extraida = caminhos_do_pacote(
            camada, pasta_destino)
        self.pasta = self.pasta_extraida
        # nomes antigos, mantidos para nao quebrar quem ja os usava
        self.zip_path = self.arquivo
        self.nome_zip = self.arquivo.name
        self.mensagem = ""
        self._bytes = 0

    # ─── execucao em segundo plano ───────────────────────────────────────────

    def run(self) -> bool:
        try:
            if self.forcar:
                self._limpar_pasta()
            elif self._ja_extraido():
                registrar(f"[{self.camada.id}] ja estava em disco: "
                          f"{self.pasta_extraida}")
                # Ainda assim passa pelo alfa: o pacote pode ter sido baixado
                # por uma versao do plugin anterior a esta.
                self._tirar_moldura_branca()
                self.setProgress(100)
                return True

            pacote.criar_pasta(self.pasta)
            if self.forcar or not self._arquivo_utilizavel():
                self._baixar()
            if self.isCanceled():
                return False

            self.setProgress(88)
            if self._e_pacote_a_extrair():
                pacote.extrair(self.arquivo, self.pasta_extraida,
                               progresso=self._progresso_extracao)
                if self.isCanceled():
                    return False
                from .config import ler
                if not ler("manter_zip"):
                    try:
                        os.remove(pacote.caminho_longo(self.arquivo))
                    except OSError:
                        pass
            else:
                # .las, .jp2, .xlsx: nao ha o que extrair, o arquivo ja esta
                # na pasta do pacote.
                registrar(f"[{self.camada.id}] nao e zip; mantido como veio: "
                          f"{self.arquivo.name}")

            self._tirar_moldura_branca()
            self.setProgress(100)
            return True

        except Exception as e:                     # noqa: BLE001 - vai para a UI
            self.mensagem = str(e)
            registrar(f"[{self.camada.id}] {e}", Qgis.MessageLevel.Critical)
            return False

    def _limpar_pasta(self):
        """
        Esvazia a pasta do pacote antes de rebaixar.

        Sem isto, sobra o lixo da tentativa anterior — foi assim que um .xlsx
        extraido por engano deixou [Content_Types].xml e xl/ para tras.
        """
        import shutil
        alvo = Path(pacote.caminho_longo(self.pasta_extraida))
        if alvo.is_dir():
            shutil.rmtree(alvo, ignore_errors=True)
        registrar(f"[{self.camada.id}] pasta limpa para rebaixar")

    def _e_pacote_a_extrair(self) -> bool:
        """
        Verdadeiro so para arquivo morto de verdade.

        Exige as DUAS coisas: extensao de arquivo morto e conteudo de zip.
        So o conteudo nao basta — .xlsx, .docx e .kmz sao zip por dentro, e
        extrair uma planilha espalha [Content_Types].xml, _rels/ e xl/ na pasta
        e apaga a planilha em seguida. Extensao vazia tambem passa: ha pacote
        no acervo sem sufixo no nome do servidor.
        """
        ext = self.arquivo.suffix.lower()
        if ext and ext not in EXTENSOES_ARQUIVO_MORTO:
            return False
        return zipfile.is_zipfile(pacote.caminho_longo(self.arquivo))

    def _ja_extraido(self) -> bool:
        return pacote.pasta_tem_conteudo(self.pasta_extraida)

    def _arquivo_utilizavel(self) -> bool:
        """Um download completo de uma tentativa anterior evita rebaixar."""
        try:
            tam = os.path.getsize(pacote.caminho_longo(self.arquivo))
        except OSError:
            return False
        esperado = self.camada.tamanho_bytes
        return tam > MIN_BYTES and (not esperado or tam == esperado)

    def _progresso_extracao(self, feitos, total):
        if total:
            self.setProgress(88 + 8 * feitos / total)
            self.andamento.emit("extraindo %d de %d arquivos" % (feitos, total),
                                feitos)

    def _tirar_moldura_branca(self):
        """
        Da aos GeoTIFF da geofisica a banda alfa que o SGB nao gravou.

        Sem ela, cada raster chega com um retangulo branco cobrindo de 33% a
        49% da area — o mapa embaixo some. Automatico, sem perguntar: nao ha
        caso em que a moldura branca seja desejavel.

        SO nos pacotes de geofisica, e o limite importa. A regra "branco que
        alcanca a moldura e fundo" foi medida nos GeoTIFF renderizados do SGB,
        onde o branco e enquadramento. Num mapa geologico escaneado, que
        aparece como .tif dentro de pacote SIG, o branco e o papel — e papel e
        conteudo. As 56 ortofotos do acervo sao .jp2 e nunca chegariam aqui,
        mas um .tif solto num pacote vetorial chegaria.

        E seguro fazer sem perguntar: as bandas RGB saem byte a byte iguais, a
        georreferencia tambem, e o arquivo fica MENOR (nos 19 medidos, 32,2 MB
        viraram 7,3 MB). Nunca derruba o download: se um TIFF resistir, os
        outros seguem e o pacote continua utilizavel.
        """
        from . import alfa
        from .config import TIPO_COM_MOLDURA_BRANCA
        if self.camada.tipo != TIPO_COM_MOLDURA_BRANCA:
            return
        try:
            mexidos = alfa.aplicar_na_pasta(
                self.pasta_extraida,
                progresso=self._progresso_alfa,
                cancelado=self.isCanceled)
        except Exception as e:                       # noqa: BLE001
            registrar(f"[{self.camada.id}] moldura branca: {e}", Qgis.MessageLevel.Warning)
            return
        if mexidos:
            registrar(f"[{self.camada.id}] banda alfa em {mexidos} GeoTIFF")

    def _progresso_alfa(self, feitos, total):
        if total:
            self.setProgress(96 + 4 * feitos / total)
            self.andamento.emit(
                "tirando a moldura branca · %d de %d" % (feitos, total), feitos)

    # ─── rede ────────────────────────────────────────────────────────────────

    def _baixar(self):
        from qgis.core import QgsNetworkAccessManager

        parcial = self.arquivo.with_name(self.arquivo.name + ".parcial")
        pedido = QNetworkRequest(QUrl(self.camada.link))
        pedido.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        pedido.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader,
                         "QGIS Acervo CPRM")

        resposta = QgsNetworkAccessManager.instance().get(pedido)
        laco = QEventLoop()
        resposta.finished.connect(laco.quit)

        estado = {"escrito": 0, "total": self.camada.tamanho_bytes or 0,
                  "cabecalho": b"", "erro": None}

        with open(pacote.caminho_longo(parcial), "wb") as saida:
            def drenar():
                dados = bytes(resposta.readAll())
                if dados:
                    if not estado["cabecalho"]:
                        estado["cabecalho"] = dados[:64]
                    saida.write(dados)
                    estado["escrito"] += len(dados)

            def progresso(recebidos, total):
                if total > 0:
                    estado["total"] = total
                if estado["total"]:
                    self.setProgress(90 * recebidos / estado["total"])
                    self.andamento.emit(
                        "%s de %s" % (legivel(recebidos),
                                      legivel(estado["total"])), recebidos)
                else:
                    # Servidor sem Content-Length: sem total nao ha fracao,
                    # mas mostrar o que ja veio ainda e melhor que nada.
                    self.andamento.emit(legivel(recebidos) + " recebidos",
                                        recebidos)
                if self.isCanceled():
                    resposta.abort()

            resposta.readyRead.connect(drenar)
            resposta.downloadProgress.connect(progresso)
            laco.exec()
            drenar()

        if self.isCanceled():
            self._apagar(parcial)
            raise ErroDownload("cancelado")

        if resposta.error() != QNetworkReply.NetworkError.NoError:
            self._apagar(parcial)
            raise ErroDownload(f"rede: {resposta.errorString()}")

        codigo = resposta.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        tipo = resposta.header(QNetworkRequest.KnownHeaders.ContentTypeHeader) or ""

        # Licao do projeto anterior: link morto do RiGeo responde HTTP 200 com a
        # pagina do DSpace. Sem esta checagem, isso vira um .zip de 3 KB.
        if estado["escrito"] < MIN_BYTES or _parece_html(estado["cabecalho"], tipo):
            self._apagar(parcial)
            raise ErroDownload(
                f"o servidor devolveu uma pagina, nao o arquivo "
                f"(HTTP {codigo}, {tipo or 'sem tipo'})")

        # Licao do projeto anterior: download cortado virava arquivo truncado
        # marcado como bom, e nunca mais era tentado.
        esperado = estado["total"]
        if esperado and estado["escrito"] != esperado:
            self._apagar(parcial)
            raise ErroDownload(
                f"download incompleto: {estado['escrito']:,} de {esperado:,} bytes")

        os.replace(pacote.caminho_longo(parcial),
                   pacote.caminho_longo(self.arquivo))
        self._bytes = estado["escrito"]
        registrar(f"[{self.camada.id}] {estado['escrito']/2**20:.1f} MB "
                  f"-> {self.arquivo}")

    @staticmethod
    def _apagar(p):
        try:
            os.remove(pacote.caminho_longo(p))
        except OSError:
            pass

    # ─── volta para a thread principal ───────────────────────────────────────

    def finished(self, ok: bool):
        if ok:
            self.concluido.emit(str(self.pasta_extraida))
        elif self.isCanceled():
            self.falhou.emit("cancelado")
        else:
            self.falhou.emit(self.mensagem or "falhou")


_ASSINATURAS_HTML = (b"<!DOCTYPE", b"<!doctype", b"<html", b"<HTML", b"<?xml")


def _parece_html(cabecalho: bytes, tipo: str) -> bool:
    if str(tipo).split(";")[0].strip().lower() in ("text/html",
                                                   "application/xhtml+xml"):
        return True
    return cabecalho.lstrip()[:16].startswith(_ASSINATURAS_HTML[:4])
