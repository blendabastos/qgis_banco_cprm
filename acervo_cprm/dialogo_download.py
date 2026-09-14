# -*- coding: utf-8 -*-
"""
dialogo_download.py — Confirmacao antes de baixar.

O acervo tem pacotes de 1,6 GB. Comecar a baixar por um duplo clique acidental
e o tipo de coisa que consome a franquia de internet de alguem em campo. Aqui o
usuario ve o que vai baixar, quanto pesa e onde vai parar, e decide.

Quando o pacote ja esta em disco o dialogo muda de tom: nao ha o que baixar, e
o botao passa a ser "Adicionar ao projeto".
"""

from pathlib import Path

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLabel, QCheckBox,
    QDialogButtonBox, QFrame,
)


class DialogoDownload(QDialog):
    """
    Confirma o download de um pacote.

    Depois de exec(), quem chama le:
        adicionar_depois  — se deve abrir a selecao de camadas ao terminar
        ja_em_disco       — se nao ha nada a baixar
    """

    def __init__(self, camada, pasta_destino: Path, pasta_extraida: Path,
                 parent=None):
        super().__init__(parent)
        self.camada = camada
        self.pasta_destino = Path(pasta_destino)
        self.pasta_extraida = Path(pasta_extraida)
        self.ja_em_disco = self._esta_em_disco()
        self.abriveis = self._contar_abriveis()
        self.adicionar_depois = True
        self.rebaixar = False
        self.setWindowTitle("Baixar camada" if not self.ja_em_disco
                            else "Pacote já baixado")
        self.setMinimumWidth(560)
        self._montar()

    def _esta_em_disco(self) -> bool:
        try:
            from . import pacote
            p = Path(pacote.caminho_longo(self.pasta_extraida))
            return p.is_dir() and any(p.iterdir())
        except Exception:
            return False

    def _contar_abriveis(self) -> int:
        """
        Quantos arquivos do pacote em disco o QGIS abre como camada.

        Existe por causa de um relato: o usuario clicou numa carta ja baixada,
        o dialogo ofereceu "Adicionar ao projeto", ele clicou, e nada entrou no
        mapa. O pacote era um PDF sem georreferencia. Prometer e nao cumprir e
        pior do que dizer de antemao que ali so ha o que abrir fora do QGIS.

        -1 quando nao da para saber (pacote ainda nao baixado): o dialogo nao
        muda de forma nesse caso.
        """
        if not self.ja_em_disco:
            return -1
        try:
            from . import pacote
            return sum(1 for _, especie in pacote.listar_arquivos(
                self.pasta_extraida) if especie != "arquivo")
        except Exception:
            return -1

    def _montar(self):
        leiaute = QVBoxLayout(self)

        titulo = QLabel(f"<b>{self.camada.titulo}</b>")
        titulo.setWordWrap(True)
        leiaute.addWidget(titulo)

        caminho = QLabel(" › ".join(self.camada.pastas))
        caminho.setWordWrap(True)
        caminho.setStyleSheet("color: palette(mid);")
        leiaute.addWidget(caminho)

        risco = QFrame()
        risco.setFrameShape(QFrame.Shape.HLine)
        risco.setStyleSheet("color: palette(mid);")
        leiaute.addWidget(risco)

        ficha = QFormLayout()
        from . import config
        ficha.addRow("Tipo:", QLabel(config.rotulo(self.camada.tipo)))
        ficha.addRow("Tamanho:", QLabel(self._texto_tamanho()))
        ficha.addRow("Arquivo:", self._rotulo_elidido(
            self.camada.nome_arquivo or "—"))
        ficha.addRow("Destino:", self._rotulo_elidido(str(self.pasta_destino)))
        ficha.addRow("ID no GEOSGB:", QLabel(self.camada.id))
        leiaute.addLayout(ficha)

        if self.ja_em_disco and self.abriveis == 0:
            aviso = QLabel(
                "Este pacote <b>já está baixado</b>, mas <b>nada nele abre no "
                "QGIS</b> como camada — é o caso da carta em PDF sem "
                "georreferencia. Dá para abrir a pasta e usá-lo fora do QGIS.")
        elif self.ja_em_disco:
            aviso = QLabel(
                "Este pacote <b>já está baixado</b>. Nada será transferido de "
                "novo — você pode adicionar as camadas ao projeto ou abrir a "
                "pasta.")
            aviso.setWordWrap(True)
            leiaute.addWidget(aviso)
        elif self.camada.tamanho_bytes > 200 * 2**20:
            aviso = QLabel(
                f"⚠ São <b>{self.camada.tamanho_legivel}</b>. O download roda "
                f"em segundo plano e pode ser cancelado na barra de progresso "
                f"do QGIS.")
            aviso.setWordWrap(True)
            leiaute.addWidget(aviso)

        self.marca_adicionar = QCheckBox(
            "Escolher as camadas para adicionar ao projeto quando terminar")
        self.marca_adicionar.setChecked(self.abriveis != 0)
        self.marca_adicionar.setEnabled(self.abriveis != 0)
        leiaute.addWidget(self.marca_adicionar)

        leiaute.addStretch()

        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        if self.ja_em_disco and self.abriveis == 0:
            # Sem nada que o QGIS abra, o botao principal mostra a pasta em vez
            # de aceitar o dialogo. ActionRole, e nao AcceptRole: com AcceptRole
            # o QDialogButtonBox aceitaria o dialogo por conta propria, e o
            # painel seguiria para a selecao de camadas que nao tem o que
            # oferecer — exatamente o que este dialogo passou a evitar.
            ok = botoes.addButton("Abrir pasta",
                                  QDialogButtonBox.ButtonRole.ActionRole)
            ok.clicked.connect(self._abrir_pasta)
            ok.clicked.connect(self.reject)
        else:
            ok = botoes.addButton("Adicionar ao projeto" if self.ja_em_disco
                                  else "Baixar",
                                  QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        if self.ja_em_disco:
            if self.abriveis != 0:
                # Quando nada abre, o proprio botao principal ja e o "Abrir
                # pasta"; dois botoes com o mesmo rotulo seriam so confusao.
                abrir = botoes.addButton("Abrir pasta",
                                         QDialogButtonBox.ButtonRole.ActionRole)
                abrir.clicked.connect(self._abrir_pasta)
            # Recupera pacote que ficou ruim numa versao anterior do plugin,
            # e serve quando o SGB republica o arquivo. Vale tambem para a
            # carta em PDF: um download truncado nao abre no leitor nenhum.
            de_novo = botoes.addButton("Baixar de novo",
                                       QDialogButtonBox.ButtonRole.ActionRole)
            de_novo.setToolTip("Apaga o que está na pasta e transfere de novo")
            de_novo.clicked.connect(self._rebaixar)
        botoes.accepted.connect(self._confirmar)
        botoes.rejected.connect(self.reject)
        leiaute.addWidget(botoes)

    def _texto_tamanho(self) -> str:
        if self.camada.tamanho_bytes <= 0:
            return "desconhecido"
        return self.camada.tamanho_legivel

    @staticmethod
    def _rotulo_elidido(texto: str) -> QLabel:
        rotulo = QLabel(texto)
        rotulo.setWordWrap(True)
        rotulo.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        return rotulo

    def _abrir_pasta(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.pasta_extraida)))

    def _rebaixar(self):
        self.rebaixar = True
        self._confirmar()

    def _confirmar(self):
        self.adicionar_depois = self.marca_adicionar.isChecked()
        self.accept()
