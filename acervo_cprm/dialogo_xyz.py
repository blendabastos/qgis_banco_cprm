# -*- coding: utf-8 -*-
"""
dialogo_xyz.py — Escolher quais XYZ aerogeofisicos converter em pontos.

O XYZ do Geosoft nao abre no QGIS, e ate agora o plugin so o deixava em disco.
Aqui ele vira tabela de pontos: uma linha por medida, com a linha de voo, a
data e todos os canais.

A tela mostra o que o plugin DEDUZIU de cada arquivo — quais colunas sao a
coordenada, qual CRS, e de onde tirou isso. Nao e enfeite: em 11 dos 126
projetos nao ha nome de coluna nenhum e a leitura sai de faixa de valores, e
em 3 o CRS e um Mercator sem codigo EPSG descrito em prosa dentro de um .doc.
Quem conhece o dado precisa poder discordar antes de esperar 20 minutos.

Arquivos de que nao sabemos o fuso aparecem desmarcados, com um seletor de CRS
ao lado: sem isso, so restaria converter errado ou nao converter.
"""

from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QDialogButtonBox, QAbstractItemView, QFrame, QComboBox, QCheckBox,
)

from . import xyz
from .catalogo import bytes_legivel as _legivel





def _tempo_legivel(segundos):
    if segundos < 90:
        return "%d s" % max(1, int(segundos))
    if segundos < 5400:
        return "%d min" % round(segundos / 60)
    return "%.1f h" % (segundos / 3600)


class DialogoXyz(QDialog):
    """
    Depois de exec(), quem chama le:
        escolhidos  — lista de (Esquema, caminho_de_saida)
        formato     — "Parquet" ou "GPKG"
    """

    #: O GeoParquet e o padrao por medida, nao por moda. Convertendo o
    #: 1117_MagLine.XYZ, de 1,79 GB: 460 MB em Parquet contra 2,61 GB em
    #: GeoPackage — 5,7 vezes menor, no mesmo tempo de escrita. O QGIS 4 abre
    #: os dois nativamente. O GeoPackage fica na lista porque e o que o ArcGIS
    #: e o QGIS 3 leem.
    FORMATOS = (("GeoParquet (menor)", "Parquet"),
                ("GeoPackage (mais compatível)", "GPKG"))

    #: Sufixo da saida. Mora em xyz.py porque a tarefa tambem precisa dele
    #: para limpar saidas antigas.
    SUFIXO = xyz.SUFIXO_AQUISICAO

    def __init__(self, esquemas, titulo_pacote, pasta, parent=None):
        super().__init__(parent)
        self.esquemas = list(esquemas)
        self.pasta = Path(pasta)
        self.escolhidos = []
        self.formato = "Parquet"
        self.apagar_origem = False
        self._seletores = {}
        self.setWindowTitle("Converter XYZ em tabela de pontos")
        self.setMinimumSize(900, 520)
        self._montar(titulo_pacote)

    # ─── Interface ───────────────────────────────────────────────────────────

    def _montar(self, titulo_pacote):
        leiaute = QVBoxLayout(self)

        cabeca = QLabel("<b>%s</b>" % titulo_pacote)
        cabeca.setWordWrap(True)
        leiaute.addWidget(cabeca)

        explica = QLabel(
            "Cada arquivo vira uma tabela de pontos: uma linha por medida, com "
            "a linha de voo, a data e os canais. As linhas de controle (Tie) "
            "entram junto, com uma coluna dizendo qual é.")
        explica.setWordWrap(True)
        explica.setStyleSheet("color: palette(mid);")
        leiaute.addWidget(explica)

        self.arvore = QTreeWidget()
        self.arvore.setColumnCount(6)
        self.arvore.setHeaderLabels(
            ["Arquivo", "Tamanho", "Colunas", "Coordenada e CRS", "Estimativa",
             "Em disco"])
        self.arvore.setRootIsDecorated(False)
        self.arvore.setAlternatingRowColors(True)
        self.arvore.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.arvore.itemSelectionChanged.connect(self._mostrar_procedencia)
        leiaute.addWidget(self.arvore, 1)

        for esq in self.esquemas:
            self._linha(esq)
        for i in range(6):
            self.arvore.resizeColumnToContents(i)

        self.detalhe = QLabel("Selecione um arquivo para ver como o plugin "
                              "chegou a essa leitura.")
        self.detalhe.setWordWrap(True)
        self.detalhe.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detalhe.setMinimumHeight(78)
        self.detalhe.setAlignment(Qt.AlignmentFlag.AlignTop)
        quadro = QFrame()
        quadro.setFrameShape(QFrame.Shape.StyledPanel)
        dentro = QVBoxLayout(quadro)
        dentro.setContentsMargins(8, 6, 8, 6)
        dentro.addWidget(self.detalhe)
        leiaute.addWidget(quadro)

        self.marca_apagar = QCheckBox(self._texto_apagar())
        self.marca_apagar.setToolTip(
            "O XYZ original só serve para abrir no Oasis Montaj. Se você não "
            "usa, a tabela de pontos substitui.")
        self.marca_apagar.setChecked(False)
        leiaute.addWidget(self.marca_apagar)

        linha_formato = QHBoxLayout()
        linha_formato.addWidget(QLabel("Formato de saída:"))
        self.combo_formato = QComboBox()
        for rotulo, _ in self.FORMATOS:
            self.combo_formato.addItem(rotulo)
        self.combo_formato.currentIndexChanged.connect(self._formato_mudou)
        linha_formato.addWidget(self.combo_formato)
        linha_formato.addStretch()
        self.resumo = QLabel()
        linha_formato.addWidget(self.resumo)
        leiaute.addLayout(linha_formato)

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        todos = botoes.addButton("Marcar todos",
                                 QDialogButtonBox.ButtonRole.ActionRole)
        todos.clicked.connect(self._marcar_todos)
        self.ok = botoes.addButton("Converter",
                                   QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setDefault(True)
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        leiaute.addWidget(botoes)

        self.arvore.itemChanged.connect(self._atualizar_resumo)
        self._atualizar_resumo()

    def _linha(self, esq):
        caminho = Path(esq.arquivo)
        try:
            tamanho = caminho.stat().st_size
        except OSError:
            tamanho = 0
        pontos, segundos = xyz.estimar(tamanho)

        item = QTreeWidgetItem(self.arvore)
        item.setText(0, caminho.name)
        item.setToolTip(0, str(caminho))
        item.setText(1, _legivel(tamanho))
        item.setText(2, str(esq.n_colunas) if esq.n_colunas else "—")
        item.setText(3, self._resumo_da_coordenada(esq))
        item.setText(4, "%s pontos · %s"
                     % ("{:,}".format(pontos).replace(",", "."),
                        _tempo_legivel(segundos)))
        item.setText(5, self._estado_da_saida(esq))
        item.setData(0, Qt.ItemDataRole.UserRole, esq)

        pronto = esq.tem_coordenada and not esq.problemas
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked if pronto
                           else Qt.CheckState.Unchecked)
        if not esq.tem_coordenada:
            item.setForeground(3, Qt.GlobalColor.darkRed)
            if esq.forma == "utm":
                self._por_seletor_de_crs(item, esq)
        elif esq.problemas:
            item.setForeground(3, Qt.GlobalColor.darkRed)

    def _por_seletor_de_crs(self, item, esq):
        """
        Para UTM sem fuso declarado: o usuario escolhe.

        So os fusos que cobrem o Brasil, e so em SAD69, que e o datum dos
        levantamentos aerogeofisicos anteriores a 2005. Uma lista curta de
        opcoes certas erra menos que o seletor de CRS inteiro do QGIS.
        """
        combo = QComboBox()
        combo.addItem("escolha o fuso…", "")
        for zona in range(18, 26):
            combo.addItem("SAD69 / UTM %dS  (MC %d°)"
                          % (zona, 6 * zona - 183), "EPSG:%d" % (29170 + zona))
        for zona in range(18, 26):
            combo.addItem("SIRGAS 2000 / UTM %dS" % zona,
                          "EPSG:%d" % (31960 + zona))
        combo.currentIndexChanged.connect(
            lambda _i, it=item, c=combo, e=esq: self._crs_escolhido(it, c, e))
        self.arvore.setItemWidget(item, 3, combo)
        self._seletores[id(esq)] = combo

    def _crs_escolhido(self, item, combo, esq):
        authid = combo.currentData()
        esq.crs = authid or ""
        if authid:
            esq.anotar("CRS: %s — escolhido na tela de conversão." % authid)
            esq.problemas = (xyz.verificar(esq, esq.extensao_amostra)
                             if esq.extensao_amostra else [])
        item.setCheckState(0, Qt.CheckState.Checked
                           if esq.tem_coordenada and not esq.problemas
                           else Qt.CheckState.Unchecked)
        self._mostrar_procedencia()
        self._atualizar_resumo()

    @staticmethod
    def _resumo_da_coordenada(esq):
        if not esq.forma:
            return "coordenada não identificada"
        rotulo = {"grau": "grau decimal", "gms": "grau/minuto/segundo",
                  "utm": "UTM", "mercator_em": "Mercator Equatorial"}[esq.forma]
        if not esq.crs:
            return "%s — falta o fuso" % rotulo
        if esq.crs.startswith("EPSG"):
            return "%s · %s" % (rotulo, esq.crs)
        return "%s · sem código EPSG" % rotulo

    # ─── Reacoes ─────────────────────────────────────────────────────────────

    def _itens(self):
        return [self.arvore.topLevelItem(i)
                for i in range(self.arvore.topLevelItemCount())]

    def _mostrar_procedencia(self):
        itens = self.arvore.selectedItems()
        if not itens:
            return
        esq = itens[0].data(0, Qt.ItemDataRole.UserRole)
        partes = ["• " + p for p in esq.procedencia]
        partes += ["⚠ " + p for p in esq.problemas]
        partes += ["⚠ " + a for a in esq.avisos]
        self.detalhe.setText("<br>".join(partes) if partes
                             else "Sem observações.")

    def _marcar_todos(self):
        alvo = Qt.CheckState.Checked
        prontos = [i for i in self._itens()
                   if i.data(0, Qt.ItemDataRole.UserRole).tem_coordenada]
        if prontos and all(i.checkState(0) == Qt.CheckState.Checked
                           for i in prontos):
            alvo = Qt.CheckState.Unchecked
        for item in prontos:
            item.setCheckState(0, alvo)

    def _formato_mudou(self, indice):
        _, self.formato = self.FORMATOS[indice]

    def _texto_apagar(self):
        """
        Rotulo da caixa de apagar o original, com o espaco que isso libera.

        Vem de um caso real: o projeto 1117 ocupou 5,3 GB numa pasta so — 2,2
        GB de XYZ original mais duas conversoes do mesmo dado. O XYZ serve para
        quem abre no Oasis Montaj; para quem nao abre, e peso morto.

        A caixa comeca DESMARCADA. Apagar o dado bruto do usuario por padrao
        seria decidir por ele, e a conversao e uma leitura nossa do arquivo —
        se ela estiver errada, o original e o unico jeito de descobrir.
        """
        total = 0
        for esq in self.esquemas:
            try:
                total += Path(esq.arquivo).stat().st_size
            except OSError:
                pass
        return ("Apagar o arquivo XYZ original depois de converter — libera "
                "até %s" % _legivel(total))

    @staticmethod
    def _estado_da_saida(esq):
        """
        O que ja existe em disco a partir deste XYZ.

        Precisa aparecer porque a conversao APAGA a saida anterior, em
        qualquer formato. Antes disso, converter de novo num formato diferente
        deixava as duas na pasta: no projeto 1117, o .parquet de 460 MB e o
        .gpkg de 2,61 GB do MESMO arquivo, os dois oferecidos como camada.
        """
        existentes = xyz.saidas_existentes(esq.arquivo)
        if not existentes:
            return "—"
        return "já convertido: " + ", ".join(
            p.suffix.lstrip(".") for p in existentes)

    def _atualizar_resumo(self, *_):
        marcados = [i for i in self._itens()
                    if i.checkState(0) == Qt.CheckState.Checked]
        if not marcados:
            self.resumo.setText("")
            self.ok.setEnabled(False)
            return
        total = 0
        for item in marcados:
            esq = item.data(0, Qt.ItemDataRole.UserRole)
            try:
                total += Path(esq.arquivo).stat().st_size
            except OSError:
                pass
        pontos, segundos = xyz.estimar(total)
        self.resumo.setText(
            "%d arquivo%s · ~%s pontos · ~%s"
            % (len(marcados), "s" if len(marcados) > 1 else "",
               "{:,}".format(pontos).replace(",", "."),
               _tempo_legivel(segundos)))
        self.ok.setEnabled(True)

    def _confirmar(self):
        self.escolhidos = []
        for item in self._itens():
            if item.checkState(0) != Qt.CheckState.Checked:
                continue
            esq = item.data(0, Qt.ItemDataRole.UserRole)
            if not esq.tem_coordenada:
                continue
            origem = Path(esq.arquivo)
            self.escolhidos.append(
                (esq, xyz.caminho_de_saida(origem, self.formato)))
        self.apagar_origem = self.marca_apagar.isChecked()
        self.accept()
