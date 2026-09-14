# -*- coding: utf-8 -*-
"""
plugin.py — Ponto de entrada: cria a acao na barra e o painel.

Deliberadamente magro. Toda a logica mora nos outros modulos; aqui so fica o
que o QGIS exige de um plugin: initGui, unload e o gatilho do painel.
"""

from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .painel import PainelAcervo

MENU = "&Acervo SIG - CPRM"


class PluginAcervoCPRM:

    def __init__(self, iface):
        self.iface = iface
        self.acao = None
        self.painel = None

    def initGui(self):
        icone = Path(__file__).resolve().parent / "icone.svg"
        self.acao = QAction(QIcon(str(icone)), "Acervo SIG - CPRM",
                            self.iface.mainWindow())
        self.acao.setCheckable(True)
        self.acao.setStatusTip("Baixar camadas vetoriais do acervo GEOSGB")
        self.acao.triggered.connect(self.alternar_painel)
        self.iface.addToolBarIcon(self.acao)
        self.iface.addPluginToWebMenu(MENU, self.acao)

    def unload(self):
        if self.painel is not None:
            self.iface.removeDockWidget(self.painel)
            self.painel.deleteLater()
            self.painel = None
        if self.acao is not None:
            self.iface.removeToolBarIcon(self.acao)
            self.iface.removePluginWebMenu(MENU, self.acao)
            self.acao = None

    def alternar_painel(self, marcado: bool):
        if self.painel is None:
            self.painel = PainelAcervo(self.iface, self.iface.mainWindow())
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                                     self.painel)
            # Se o usuario fechar pelo X, o botao da barra tem que desmarcar.
            self.painel.visibilityChanged.connect(self._sincronizar_botao)
        self.painel.setVisible(marcado)

    def _sincronizar_botao(self, visivel: bool):
        if self.acao is not None and self.acao.isChecked() != visivel:
            self.acao.setChecked(visivel)
