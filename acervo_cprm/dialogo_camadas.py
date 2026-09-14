# -*- coding: utf-8 -*-
"""
dialogo_camadas.py — Escolha de quais camadas do pacote entram no projeto.

Um pacote traz de 1 a 16 shapefiles. Adicionar todos poluiria o painel de
camadas; nao adicionar nenhum deixaria o trabalho com o usuario. Entao ele ve
o que veio, com geometria e contagem de feicoes, e marca o que interessa.
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QDialogButtonBox, QHeaderView, QWidget,
)


class DialogoCamadas(QDialog):
    """Devolve, em `selecionadas`, os CamadaEncontrada marcados."""

    def __init__(self, itens, nome_pacote: str, pasta=None, parent=None):
        super().__init__(parent)
        self.itens = itens
        self.pasta = pasta
        self.selecionadas = []
        self.setWindowTitle("Adicionar camadas ao projeto")
        self.resize(760, 480)
        self._montar(nome_pacote)

    def abrir_pasta(self):
        """Leva o usuario ao que foi extraido — inclusive o que o QGIS nao abre."""
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtGui import QDesktopServices
        if self.pasta:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.pasta)))

    def _montar(self, nome_pacote: str):
        leiaute = QVBoxLayout(self)

        conta = lambda esp: sum(1 for i in self.itens        # noqa: E731
                                if i.especie == esp and i.valida)
        partes = []
        for esp, singular, plural in (("vetor", "vetorial", "vetoriais"),
                                      ("raster", "raster", "rasters"),
                                      ("nuvem", "nuvem de pontos",
                                       "nuvens de pontos")):
            n = conta(esp)
            if n:
                partes.append(f"{n} {singular if n == 1 else plural}")
        so_download = conta("arquivo")
        if so_download:
            partes.append(f"{so_download} só para download")
        problemas = sum(1 for i in self.itens if not i.valida and i.eh_camada)
        if problemas:
            partes.append(f"{problemas} com problema")

        cabecalho = QLabel(
            f"<b>{nome_pacote}</b><br>"
            f"{len(self.itens)} arquivos no pacote — " + ", ".join(partes))
        cabecalho.setWordWrap(True)
        leiaute.addWidget(cabecalho)

        self.arvore = QTreeWidget()
        self.arvore.setColumnCount(5)
        self.arvore.setHeaderLabels(
            ["Camada", "Tipo", "Feições / Pixels", "CRS", "Subpasta"])
        self.arvore.setRootIsDecorated(False)
        self.arvore.setAlternatingRowColors(True)
        self.arvore.setSortingEnabled(True)

        for item in self.itens:
            linha = QTreeWidgetItem([
                item.nome,
                item.descricao,
                item.tamanho_descrito,
                item.crs or "—",
                item.subpasta or "—",
            ])
            linha.setData(0, Qt.ItemDataRole.UserRole, item)
            linha.setFlags(linha.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if not item.eh_camada:
                # Formato que o QGIS nao abre (XYZ do Geosoft, por exemplo).
                # Aparece para o usuario saber que veio, mas nao e selecionavel.
                linha.setCheckState(0, Qt.CheckState.Unchecked)
                linha.setDisabled(True)
                linha.setToolTip(
                    0, "O QGIS não abre este formato.\n"
                       "O arquivo está extraído na pasta do pacote.")
            elif item.valida:
                # Vetor sem nenhuma feicao raramente e o que se quer ver; vem
                # desmarcado. Raster nao tem contagem, entao entra marcado.
                vazio = item.especie == "vetor" and not item.feicoes
                linha.setCheckState(
                    0, Qt.CheckState.Unchecked if vazio else Qt.CheckState.Checked)
            else:
                linha.setCheckState(0, Qt.CheckState.Unchecked)
                linha.setDisabled(True)
                linha.setToolTip(0, item.erro)
            self.arvore.addTopLevelItem(linha)

        cab = self.arvore.header()
        cab.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 5):
            cab.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        leiaute.addWidget(self.arvore)

        # Tabela com LATITUDE/LONGITUDE pode virar camada de pontos. Vale para
        # os 129 pacotes de geoquimica que vem como planilha solta, sem o
        # shapefile que o SGB costuma anexar.
        self.espacializar = None
        self.seletor_crs = None
        com_coord = [i for i in self.itens
                     if i.especie == "tabela" and i.coordenadas and i.valida]
        if com_coord:
            leiaute.addWidget(self._bloco_espacializar(com_coord))

        atalhos = QHBoxLayout()
        for rotulo, estado in (("Marcar todas", Qt.CheckState.Checked),
                               ("Desmarcar todas", Qt.CheckState.Unchecked)):
            b = QPushButton(rotulo)
            b.clicked.connect(lambda _, e=estado: self._marcar_todas(e))
            atalhos.addWidget(b)
        atalhos.addStretch()
        if self.pasta:
            b_pasta = QPushButton("Abrir pasta do pacote")
            b_pasta.setToolTip("Onde tudo foi extraído, inclusive o que o "
                               "QGIS não abre")
            b_pasta.clicked.connect(self.abrir_pasta)
            atalhos.addWidget(b_pasta)
        leiaute.addLayout(atalhos)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.button(QDialogButtonBox.StandardButton.Ok).setText("Adicionar")
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        leiaute.addWidget(botoes)

    def _bloco_espacializar(self, com_coord) -> QWidget:
        """Opção de transformar as tabelas com coordenada em pontos."""
        from qgis.PyQt.QtWidgets import QCheckBox
        from .pacote import CRS_PADRAO

        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)

        quantas = len(com_coord)
        colunas = com_coord[0].coordenadas
        self.espacializar = QCheckBox(
            f"Converter {quantas} tabela{'s' if quantas > 1 else ''} em pontos "
            f"({colunas[0]}/{colunas[1]})")
        self.espacializar.setChecked(True)
        self.espacializar.setToolTip(
            "Grava um GeoPackage ao lado da planilha, com um ponto por linha.\n"
            "Linhas sem coordenada válida são puladas.")
        linha.addWidget(self.espacializar)

        try:
            from qgis.gui import QgsProjectionSelectionWidget
            from qgis.core import QgsCoordinateReferenceSystem
            self.seletor_crs = QgsProjectionSelectionWidget()
            self.seletor_crs.setCrs(QgsCoordinateReferenceSystem(CRS_PADRAO))
            self.seletor_crs.setToolTip(
                "A planilha não declara o datum. O padrão segue o que o próprio\n"
                "SGB usa no shapefile das mesmas análises: SIRGAS 2000.")
            linha.addWidget(self.seletor_crs, 1)
            self.espacializar.toggled.connect(self.seletor_crs.setEnabled)
        except ImportError:
            linha.addStretch()
        return caixa

    @property
    def crs_escolhido(self) -> str:
        from .pacote import CRS_PADRAO
        if self.seletor_crs is None:
            return CRS_PADRAO
        crs = self.seletor_crs.crs()
        return crs.authid() if crs.isValid() else CRS_PADRAO

    @property
    def converter_em_pontos(self) -> bool:
        return bool(self.espacializar and self.espacializar.isChecked())

    def _marcar_todas(self, estado):
        for i in range(self.arvore.topLevelItemCount()):
            linha = self.arvore.topLevelItem(i)
            if not linha.isDisabled():
                linha.setCheckState(0, estado)

    def _confirmar(self):
        self.selecionadas = [
            self.arvore.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            for i in range(self.arvore.topLevelItemCount())
            if self.arvore.topLevelItem(i).checkState(0) == Qt.CheckState.Checked
        ]
        self.accept()
