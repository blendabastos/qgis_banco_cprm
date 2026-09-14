# -*- coding: utf-8 -*-
"""
painel.py — O painel ancoravel: arvore do acervo, busca e o botao de baixar.
"""

from pathlib import Path

from qgis.core import Qgis, QgsApplication
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QTreeWidget, QTreeWidgetItem, QPushButton, QLabel, QFileDialog, QMenu,
    QFrame, QCheckBox,
)

from . import catalogo as cat
from . import folhas
from . import municipios
from . import config, pacote
from .baixador import TarefaBaixar, caminhos_do_pacote, registrar
from .dialogo_camadas import DialogoCamadas
from .dialogo_download import DialogoDownload
from .dialogo_xyz import DialogoXyz
from .tarefa_xyz import TarefaConverterXyz

#: Acima disto, filtrar a cada tecla fica perceptivel; usamos um atraso.
ATRASO_BUSCA_MS = 180


class PainelAcervo(QDockWidget):

    def __init__(self, iface, parent=None):
        super().__init__("Acervo SIG — CPRM", parent)
        self.iface = iface
        self.setObjectName("PainelAcervoCPRM")
        self.camadas = []
        self.tarefas = []          # segura referencia: QgsTask morre sem isso
        self._barra_progresso = None   # widget de progresso na messageBar
        self._montar()
        self._preparar_cidades()
        self.carregar_catalogo()

    # ─── interface ───────────────────────────────────────────────────────────

    def _montar(self):
        corpo = QWidget()
        leiaute = QVBoxLayout(corpo)
        leiaute.setContentsMargins(6, 6, 6, 6)

        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar por folha, projeto ou palavra…")
        self.busca.setClearButtonEnabled(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(ATRASO_BUSCA_MS)
        self._timer.timeout.connect(self.aplicar_filtro)
        self.busca.textChanged.connect(lambda _: self._timer.start())
        leiaute.addWidget(self.busca)

        # A etiqueta "Tipo:" saiu daqui para abrir espaco na MESMA linha para a
        # caixa do filtro espacial. Nao faz falta: a primeira entrada do
        # seletor e "Todos os tipos", que ja diz do que a lista trata.
        #
        # E precisa ser na mesma linha. Uma linha a mais levava o minimo do
        # leiaute de 313 para 327 px, e ha teste exigindo menos de 320 —
        # ancorado a direita, o painel fica mais alto que a tela e o rodape
        # sai do monitor. Ver `test_tudo_cabe_numa_doca_curta`.
        linha = QHBoxLayout()
        self.filtro_tipo = QComboBox()
        # Os rotulos vem de `config.rotulo`; os valores, do catalogo. O nome
        # que o SGB usa nem sempre serve de rotulo: "SIG (Vetores)" sugere que
        # o resto nao e SIG, e raster tambem e.
        self.filtro_tipo.addItem("Todos os tipos", None)
        for tipo in ("SIG (Vetores)", "KML", "Geofísica-Geotiff",
                     "Geofísica-XYZ"):
            self.filtro_tipo.addItem(config.rotulo(tipo), (tipo,))
        self.filtro_tipo.addItem("LiDAR e ortofoto",
                                 ("Nuvem de pontos (LiDAR)", "Ortofoto/raster"))
        self.filtro_tipo.addItem("Geoquímica (tabelas)",
                                 ("Geoquímica-XLSX", "Geoquímica-CSV"))
        self.filtro_tipo.addItem("Só o que o QGIS abre", config.TIPOS_ABRIVEIS)
        self.filtro_tipo.currentIndexChanged.connect(self.aplicar_filtro)
        linha.addWidget(self.filtro_tipo, 1)

        # ─── ir para uma cidade ──────────────────────────────────────────────
        # 5.571 municipios do IBGE, com a caixa de coordenadas, EMBUTIDOS —
        # ver municipios.py. Nada de rede: escolher a cidade leva o mapa ate
        # ela e liga o filtro espacial, e isso funciona em campo, sem sinal.
        #
        # Na MESMA linha do seletor por causa da altura: uma linha a mais
        # custa 27 px e o minimo do leiaute ja esta em 301, com teto de 320.
        self.cidade = QLineEdit()
        self.cidade.setPlaceholderText("Ir para cidade…")
        self.cidade.setClearButtonEnabled(True)
        self.cidade.setToolTip(
            "Leva o mapa até o município e liga o filtro espacial.\n"
            "5.571 municípios do IBGE, embutidos: funciona sem internet.")
        linha.addWidget(self.cidade, 1)

        # ─── filtro espacial ─────────────────────────────────────────────────
        # A caixa e independente do campo de cidade, e as duas formas existem
        # porque sao gestos diferentes: quem ja esta com o mapa no lugar certo
        # so marca a caixa; quem esta longe digita a cidade, e o campo marca a
        # caixa sozinho.
        #
        # Nenhuma das duas geocodifica nada em tempo de execucao — a tabela do
        # IBGE vem embutida. O plugin so fala com o GEOSGB, e continua assim.
        self.so_na_tela = QCheckBox("Só nesta tela")
        self.so_na_tela.setToolTip(
            "Mostra apenas o que cruza a extensão visível do mapa.\n\n"
            "O acervo não publica geometria: a posição é deduzida do código de "
            "folha no título (SC.24, SB.21-Z-A-III…), que segue a malha do "
            "IBGE.\nAs camadas que não trazem código — XYZ, LiDAR e ortofoto, "
            "indexados por projeto — ficam de fora, e o painel diz quantas são.")
        self.so_na_tela.toggled.connect(self._alternar_filtro_espacial)
        linha.addWidget(self.so_na_tela)
        leiaute.addLayout(linha)

        # ─────────────────────────────────────────────────────────────────────
        # TUDO o que nao e a arvore vem ANTES dela, e a arvore leva o espaco
        # que sobra. A ordem parece estranha — ficha e botoes acima da lista —
        # mas e a unica que funciona sempre.
        #
        # Ancorado a direita, o painel fica com a altura inteira da janela do
        # QGIS. Quando essa janela e mais alta que a tela, o fim do painel cai
        # fora do monitor: a ficha e os tres botoes ficavam inalcancaveis, e so
        # apareciam quando o painel era movido para o topo, onde a doca e
        # baixa. Nenhum ajuste de tamanho resolve isso, porque o problema nao e
        # o painel ser pequeno demais — e ele ser mais alto que a tela.
        #
        # Com a arvore por ultimo, o que o usuario precisa alcancar fica a uma
        # distancia fixa do TOPO, e e a lista que cresce ou encolhe.
        # ─────────────────────────────────────────────────────────────────────

        self.resumo = QLabel()
        self.resumo.setWordWrap(True)
        self.resumo.setStyleSheet("color: palette(mid);")
        leiaute.addWidget(self.resumo)

        # Ficha da camada selecionada, para saber o que e antes de baixar.
        self.detalhe = QLabel()
        self.detalhe.setWordWrap(True)
        self.detalhe.setTextFormat(Qt.TextFormat.RichText)
        self.detalhe.setFrameShape(QFrame.Shape.StyledPanel)
        self.detalhe.setMargin(6)
        self.detalhe.setMinimumHeight(64)
        leiaute.addWidget(self.detalhe)

        self.botao = QPushButton("Baixar…")
        self.botao.setEnabled(False)
        self.botao.setToolTip("Mostra os detalhes e pede confirmação "
                              "antes de transferir")
        self.botao.clicked.connect(self.pedir_download)
        leiaute.addWidget(self.botao)

        rodape = QHBoxLayout()
        b_pasta = QPushButton("Pasta de destino…")
        b_pasta.clicked.connect(self.escolher_destino)
        rodape.addWidget(b_pasta)
        b_atualizar = QPushButton("Atualizar catálogo")
        b_atualizar.setToolTip("Baixa a versão mais recente do repositório")
        b_atualizar.clicked.connect(self.atualizar_catalogo)
        rodape.addWidget(b_atualizar)
        leiaute.addLayout(rodape)

        self.arvore = QTreeWidget()
        self.arvore.setHeaderLabels(["Camada", "Tamanho"])
        self.arvore.setColumnWidth(0, 300)
        self.arvore.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.arvore.customContextMenuRequested.connect(self._menu_contexto)
        # Duplo clique abre a confirmacao; NAO dispara o download. Baixar 1,6 GB
        # por um clique acidental e o tipo de coisa que queima franquia em campo.
        self.arvore.itemDoubleClicked.connect(lambda *_: self.pedir_download())
        self.arvore.itemSelectionChanged.connect(self._selecao_mudou)
        # Nao deixa a lista sumir quando a doca fica curta: abaixo disto ela
        # para de encolher e o Qt corta o que vem depois — mas ja nao ha nada
        # depois dela.
        self.arvore.setMinimumHeight(80)
        leiaute.addWidget(self.arvore, 1)

        self.setWidget(corpo)

    # ─── catalogo ────────────────────────────────────────────────────────────

    def carregar_catalogo(self):
        atualizado = config.pasta_catalogo_atualizado()
        origem = atualizado if atualizado.exists() else None
        try:
            self.camadas = cat.carregar(origem)
        except Exception as e:
            self.camadas = []
            self._aviso(f"Não foi possível ler o catálogo: {e}", Qgis.Critical)
            return
        self.aplicar_filtro()

    def aplicar_filtro(self):
        termo = self.busca.text()
        tipos = self.filtro_tipo.currentData()
        visiveis = cat.filtrar(self.camadas, termo, tipos)

        nota = ""
        if self.so_na_tela.isChecked():
            extensao = self._extensao_do_mapa()
            if extensao is None:
                nota = " · <b>não consegui ler a extensão do mapa</b>"
            else:
                visiveis, _fora, sem_caixa = folhas.separar_por_extensao(
                    visiveis, extensao)
                if sem_caixa:
                    # Dito em voz alta de proposito. Estas camadas nao estao
                    # fora da tela: e que o acervo nao diz onde elas ficam, e
                    # some-las sem avisar seria esconder dado em silencio.
                    nota = (f" · {len(sem_caixa)} sem localização no catálogo, "
                            f"ocultas")

        self._preencher(cat.montar_arvore(visiveis))

        total = sum(c.tamanho_bytes for c in visiveis)
        self.resumo.setText(
            f"{len(visiveis)} de {len(self.camadas)} camadas · "
            f"{total/2**30:.1f} GB{nota}")
        # Com busca ativa a arvore fica curta: expandir ajuda a ver o resultado.
        if termo.strip():
            self.arvore.expandAll()

    # ─── ir para uma cidade ──────────────────────────────────────────────────

    def _preparar_cidades(self):
        """
        Carrega os municipios e liga o completador.

        Silencioso quando a tabela falta: o campo some e o resto do painel
        segue inteiro. E um arquivo de conveniencia, nao o catalogo.
        """
        from qgis.PyQt.QtWidgets import QCompleter
        from qgis.PyQt.QtCore import QStringListModel

        self.municipios = municipios.carregar()
        if not self.municipios:
            self.cidade.setVisible(False)
            return

        self._modelo_cidades = QStringListModel(self)
        completador = QCompleter(self._modelo_cidades, self)
        completador.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        # `UnfilteredPopupCompletion`: quem filtra somos nos, em `_sugerir`.
        # O filtro do Qt compara prefixo com acento e caixa, entao "sao
        # gabriel" nao acharia "São Gabriel" — e e assim que se digita.
        completador.setCompletionMode(
            QCompleter.CompletionMode.UnfilteredPopupCompletion)
        completador.activated.connect(self._ir_para_cidade)
        self.cidade.setCompleter(completador)
        self.cidade.textEdited.connect(self._sugerir)
        self.cidade.returnPressed.connect(
            lambda: self._ir_para_cidade(self.cidade.text()))

    def _sugerir(self, termo: str):
        """Reabastece a lista do completador a cada tecla."""
        achados = municipios.procurar(self.municipios, termo)
        self._modelo_cidades.setStringList([m.rotulo for m in achados])

    def _ir_para_cidade(self, rotulo: str):
        """
        Leva o mapa ate o municipio e liga o filtro espacial.

        Mexer no enquadramento do usuario e uma acao forte, entao so acontece
        por escolha explicita — clicar na sugestao ou apertar Enter —, nunca
        enquanto se digita.
        """
        m = municipios.por_rotulo(self.municipios, rotulo)
        if m is None:
            self._aviso("Não encontrei esse município.", Qgis.Warning)
            return
        if not self._enquadrar(municipios.com_folga(m.caixa)):
            self._aviso("Não consegui mover o mapa.", Qgis.Warning)
            return
        self.cidade.setText(m.rotulo)
        if not self.so_na_tela.isChecked():
            self.so_na_tela.setChecked(True)      # ja dispara o filtro
        else:
            self.aplicar_filtro()

    def _enquadrar(self, caixa) -> bool:
        """
        Poe a caixa (em grau) na tela, convertida para o CRS do projeto.

        A conversao e a ida da que `_extensao_do_mapa` faz na volta: a tabela
        do IBGE e EPSG:4326 e o projeto do usuario pode estar em qualquer
        coisa. Sem converter, um projeto em UTM receberia graus onde espera
        metros e o mapa saltaria para perto da origem do plano.
        """
        from qgis.core import (QgsCoordinateReferenceSystem,
                               QgsCoordinateTransform, QgsProject,
                               QgsRectangle)
        try:
            canvas = self.iface.mapCanvas()
            destino = canvas.mapSettings().destinationCrs()
        except (AttributeError, RuntimeError):
            return False

        retangulo = QgsRectangle(caixa[0], caixa[1], caixa[2], caixa[3])
        origem = QgsCoordinateReferenceSystem("EPSG:4326")
        if destino.isValid() and destino != origem:
            try:
                tr = QgsCoordinateTransform(origem, destino,
                                            QgsProject.instance())
                retangulo = tr.transformBoundingBox(retangulo)
            except Exception:                            # noqa: BLE001
                return False
        try:
            canvas.setExtent(retangulo)
            canvas.refresh()
        except (AttributeError, RuntimeError):
            return False
        return True

    # ─── filtro espacial ─────────────────────────────────────────────────────

    def _alternar_filtro_espacial(self, ligado: bool):
        """
        Liga o filtro e passa a acompanhar o mapa enquanto ele estiver ligado.

        A conexao so existe com o filtro ligado: recalcular a arvore a cada
        arrasto do mapa com o filtro desligado seria trabalho jogado fora, e
        `extentsChanged` dispara muito.
        """
        canvas = getattr(self.iface, "mapCanvas", None)
        canvas = canvas() if callable(canvas) else None
        if canvas is not None:
            try:
                if ligado:
                    canvas.extentsChanged.connect(self._mapa_moveu)
                else:
                    canvas.extentsChanged.disconnect(self._mapa_moveu)
            except (TypeError, RuntimeError):
                pass          # ja conectado, ja desconectado, ou canvas dublê
        self.aplicar_filtro()

    def _mapa_moveu(self):
        """
        O mapa mudou: refiltra, mas pelo mesmo temporizador da busca.

        `extentsChanged` dispara a cada quadro de um arrasto. Sem o atraso, a
        arvore seria remontada dezenas de vezes por segundo.
        """
        if self.so_na_tela.isChecked():
            self._timer.start()

    def _extensao_do_mapa(self):
        """
        A extensao visivel do mapa em grau decimal, ou None.

        Converte do CRS do projeto para EPSG:4326, que e onde a malha da CIM
        e definida. Sem isso, um projeto em UTM daria uma extensao em metros
        comparada com graus — e nada cruzaria, sem explicacao.
        """
        from qgis.core import (QgsCoordinateReferenceSystem,
                               QgsCoordinateTransform, QgsProject)
        try:
            canvas = self.iface.mapCanvas()
            ext = canvas.extent()
            origem = canvas.mapSettings().destinationCrs()
        except (AttributeError, RuntimeError):
            return None
        if ext is None or ext.isEmpty():
            return None

        destino = QgsCoordinateReferenceSystem("EPSG:4326")
        if origem.isValid() and origem != destino:
            try:
                tr = QgsCoordinateTransform(origem, destino,
                                            QgsProject.instance())
                ext = tr.transformBoundingBox(ext)
            except Exception:                        # noqa: BLE001
                return None
        return (ext.xMinimum(), ext.yMinimum(),
                ext.xMaximum(), ext.yMaximum())

    def _preencher(self, raiz):
        self.arvore.setUpdatesEnabled(False)
        self.arvore.clear()
        for filho in raiz.filhos:
            self.arvore.addTopLevelItem(self._item(filho))
        self.arvore.setUpdatesEnabled(True)
        self._selecao_mudou()

    def _item(self, no) -> QTreeWidgetItem:
        if no.eh_folha:
            item = QTreeWidgetItem([no.nome, no.camada.tamanho_legivel])
            item.setData(0, Qt.ItemDataRole.UserRole, no.camada)
            item.setToolTip(0, f"{no.camada.titulo}\n"
                               f"{' > '.join(no.camada.pastas)}\n"
                               f"ID {no.camada.id} · {config.rotulo(no.camada.tipo)}")
        else:
            item = QTreeWidgetItem([f"{no.nome}  ({no.contar()})", ""])
            for filho in no.filhos:
                item.addChild(self._item(filho))
        return item

    def _camada_selecionada(self):
        itens = self.arvore.selectedItems()
        if not itens:
            return None
        return itens[0].data(0, Qt.ItemDataRole.UserRole)

    def _selecao_mudou(self):
        """Clique simples so informa: mostra a ficha e habilita o botao."""
        camada = self._camada_selecionada()
        self.botao.setEnabled(camada is not None)
        if camada is None:
            self.detalhe.setText(
                "<i>Selecione uma camada para ver os detalhes.</i>")
            return

        destino = self._pasta_do_pacote(camada)
        baixado = self._ja_baixado(destino)
        self.detalhe.setText(
            f"<b>{camada.titulo}</b><br>"
            f"{config.rotulo(camada.tipo)} · {camada.tamanho_legivel}"
            + (" · <b>já baixado</b>" if baixado else "")
            + f"<br><span style='color:gray'>{' › '.join(camada.pastas)}</span>")

    def _pasta_do_pacote(self, camada) -> Path:
        """Onde o pacote fica depois de extraido."""
        return caminhos_do_pacote(camada, config.pasta_destino())[1]

    @staticmethod
    def _ja_baixado(pasta_extraida: Path) -> bool:
        try:
            p = Path(pacote.caminho_longo(pasta_extraida))
            return p.is_dir() and any(p.iterdir())
        except OSError:
            return False

    def _limpar_tarefas(self):
        """
        Descarta as referencias a tarefas que o QGIS ja destruiu.

        O gerenciador de tarefas e dono da QgsTask e a deleta quando termina.
        Chamar qualquer metodo na referencia orfa levanta
        "wrapped C/C++ object has been deleted" — foi o que quebrava o segundo
        download da sessao, abortando o metodo antes de abrir a selecao de
        camadas.
        """
        vivas = []
        for t in self.tarefas:
            try:
                t.isCanceled()
            except RuntimeError:
                continue          # ja destruida pelo gerenciador
            vivas.append(t)
        self.tarefas = vivas

    # ─── acoes ───────────────────────────────────────────────────────────────

    def pedir_download(self):
        """
        Passo 1: mostra o que sera baixado e espera a confirmacao.

        Nada de rede acontece aqui. Se o pacote ja estiver em disco, o dialogo
        avisa e o "Baixar" vira "Adicionar ao projeto".
        """
        camada = self._camada_selecionada()
        if camada is None:
            return

        destino = config.pasta_destino()
        extraida = self._pasta_do_pacote(camada)
        dialogo = DialogoDownload(camada, destino, extraida, self)
        if not dialogo.exec():
            return

        if dialogo.ja_em_disco and not dialogo.rebaixar:
            # Nada a transferir: vai direto para a selecao de camadas.
            #
            # Ja passou pela tarefa aqui, para dar a banda alfa a pacotes
            # baixados antes de ela existir. Nao vale: e um caminho permanente
            # no codigo para resolver uma migracao de uma vez so. Quem tiver um
            # pacote antigo usa o "Baixar de novo" do proprio dialogo.
            if dialogo.adicionar_depois:
                self._apos_baixar(str(extraida), camada)
            return

        self._baixar(camada, destino, dialogo.adicionar_depois,
                     forcar=dialogo.rebaixar)

    def _baixar(self, camada, destino: Path, adicionar_depois: bool,
                forcar: bool = False):
        """Passo 2: transfere de fato, ja confirmado."""
        try:
            pacote.criar_pasta(destino)
        except OSError as e:
            self._aviso(f"Não consigo escrever em {destino}: {e}", Qgis.Critical)
            return

        tarefa = TarefaBaixar(camada, destino, forcar=forcar)
        self._abrir_barra(tarefa, f"Baixando {camada.titulo[:70]}",
                          f"conectando… · {camada.tamanho_legivel}")
        tarefa.concluido.connect(
            lambda pasta, c=camada, add=adicionar_depois:
                self._apos_baixar(pasta, c, add))
        tarefa.falhou.connect(
            lambda msg, c=camada: self._apos_falhar(msg, c))
        self.tarefas.append(tarefa)
        QgsApplication.taskManager().addTask(tarefa)

    def _apos_baixar(self, pasta: str, camada, adicionar_depois: bool = True):
        """Passo 3: o pacote esta em disco; confirmar o que entra no projeto."""
        # Antes de qualquer dialogo: barra de download parada atras de uma
        # janela modal parece que o download travou.
        self._fechar_barra()
        self._limpar_tarefas()
        self._selecao_mudou()          # a ficha agora diz "ja baixado"
        if not adicionar_depois:
            self._aviso(f"Pacote salvo em {pasta}", Qgis.Success)
            return
        if self._oferecer_conversao_xyz(pasta, camada):
            return          # a conversao continua a partir de _apos_converter
        self._escolher_camadas(pasta, camada)

    def _oferecer_conversao_xyz(self, pasta: str, camada) -> bool:
        """
        Passo 3a: o pacote tem XYZ aerogeofisico? Entao ha o que converter.

        O QGIS nao abre o XYZ do Geosoft, e ate a versao 0.9 o plugin apenas
        deixava o arquivo em disco. Sao 126 projetos, 248 GB de XYZ — o maior
        acervo de dados de aquisicao que o SGB publica. Convertidos, viram
        tabela de pontos com a linha de voo, a data e todos os canais.

        Devolve True quando assumiu o fluxo (o usuario mandou converter).
        """
        from . import xyz
        try:
            esquemas = xyz.analisar_pacote(Path(pasta))
        except Exception as e:                       # noqa: BLE001
            registrar(f"Não consegui analisar os XYZ: {e}", Qgis.Warning)
            return False
        if not esquemas:
            return False

        dialogo = DialogoXyz(esquemas, camada.titulo, Path(pasta), self)
        if not dialogo.exec() or not dialogo.escolhidos:
            return False

        tarefa = TarefaConverterXyz(dialogo.escolhidos, dialogo.formato,
                                    apagar_origem=dialogo.apagar_origem)
        self._abrir_barra(
            tarefa, "Convertendo %d arquivo%s XYZ em pontos…"
            % (len(dialogo.escolhidos),
               "s" if len(dialogo.escolhidos) != 1 else ""))
        tarefa.concluido.connect(
            lambda r, p=pasta, c=camada, t=tarefa:
                self._apos_converter(r, p, c, liberado=t.liberado))
        tarefa.falhou.connect(
            lambda m, p=pasta, c=camada: self._apos_converter([], p, c, m))
        self.tarefas.append(tarefa)
        QgsApplication.taskManager().addTask(tarefa)
        return True

    def _abrir_barra(self, tarefa, titulo: str, inicial: str = "iniciando…"):
        """
        Barra de progresso no topo do mapa, enquanto a conversao roda.

        A `QgsTask` sozinha so aparece no indicador pequeno do canto inferior
        direito. Numa conversao de 20 minutos isso nao passa a sensacao de que
        algo esta acontecendo — parece plugin travado. Aqui a barra fica em
        cima do mapa, dizendo qual arquivo e quantos pontos ja sairam, com o
        botao de cancelar ao lado.
        """
        from qgis.PyQt.QtWidgets import QProgressBar, QSizePolicy

        self._fechar_barra()          # nunca duas empilhadas
        barra = self.iface.messageBar().createMessage("Acervo CPRM", titulo)

        rotulo = QLabel(inicial)
        rotulo.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Preferred)
        progresso = QProgressBar()
        progresso.setRange(0, 100)
        progresso.setMaximumWidth(220)
        progresso.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(tarefa.cancel)

        barra.layout().addWidget(rotulo)
        barra.layout().addWidget(progresso)
        barra.layout().addWidget(cancelar)
        # Nivel Info e duracao 0: so sai quando nos tirarmos. Uma barra que
        # some sozinha no meio da conversao seria pior que nenhuma.
        self.iface.messageBar().pushWidget(barra, Qgis.Info)
        self._barra_progresso = barra

        def andou(texto, _n):
            try:
                rotulo.setText(texto)
            except RuntimeError:
                pass          # a barra ja foi fechada

        def porcento(v):
            try:
                progresso.setValue(int(v))
            except RuntimeError:
                pass

        tarefa.andamento.connect(andou)
        tarefa.progressChanged.connect(porcento)

    def _fechar_barra(self):
        barra = getattr(self, "_barra_progresso", None)
        self._barra_progresso = None
        if barra is None:
            return
        try:
            self.iface.messageBar().popWidget(barra)
        except RuntimeError:
            pass          # o usuario ja fechou no X

    def _apos_converter(self, resultados, pasta: str, camada, erro: str = "",
                        liberado: int = 0):
        """Passo 3b: converteu; agora escolher o que entra no projeto."""
        self._fechar_barra()
        self._limpar_tarefas()
        if erro == "cancelado":
            self._aviso("Conversão cancelada")
            return
        if erro:
            self._aviso(f"Conversão falhou: {erro}", Qgis.Critical)
            return
        total = sum(n for _, n, _ in resultados)
        problemas = [p for _, _, ps in resultados for p in ps]
        partes = ["%d arquivo%s convertido%s"
                  % (len(resultados), "s" if len(resultados) != 1 else "",
                     "s" if len(resultados) != 1 else ""),
                  f"{total:,}".replace(",", ".") + " pontos"]
        if liberado:
            # Formatar PRIMEIRO, trocar o separador decimal depois: o replace
            # antes do % transformaria "%.1f" em "%,1f".
            partes.append(("%.1f" % (liberado / 2**30)).replace(".", ",")
                          + " GB liberados")
        if problemas:
            partes.append(f"{len(problemas)} com aviso")
        self._aviso(" · ".join(partes),
                    Qgis.Warning if problemas else Qgis.Success)
        for p in problemas:
            registrar(p, Qgis.Warning)
        self._escolher_camadas(pasta, camada)

    def _escolher_camadas(self, pasta: str, camada):
        """Passo 4: o dialogo de quais camadas do pacote entram no projeto."""
        try:
            itens = pacote.inspecionar(Path(pasta))
        except Exception as e:
            self._aviso(f"Baixou, mas não consegui ler o pacote: {e}",
                        Qgis.Warning)
            return
        if not itens:
            # Nao abrimos o Explorer sozinho: janela do sistema pulando na
            # frente do QGIS parece erro, e esconde o que de fato aconteceu.
            # A mensagem diz onde esta, e o dialogo tem o botao para ir la.
            self._aviso(f"Nenhum arquivo que o QGIS abra neste pacote. "
                        f"Conteúdo em {pasta}", Qgis.Warning)
            return

        dialogo = DialogoCamadas(itens, camada.titulo, Path(pasta), self)
        if not dialogo.exec() or not dialogo.selecionadas:
            self._aviso(f"Pacote salvo em {pasta}")
            return

        adicionadas, falhas = pacote.adicionar_ao_projeto(
            dialogo.selecionadas, camada.titulo[:60],
            em_pontos=dialogo.converter_em_pontos,
            crs_authid=dialogo.crs_escolhido)
        msg = f"{len(adicionadas)} camadas adicionadas"
        if dialogo.converter_em_pontos:
            msg += f" (tabelas espacializadas em {dialogo.crs_escolhido})"
        if falhas:
            msg += f", {len(falhas)} não abriram"
        self._aviso(msg, Qgis.Success if adicionadas else Qgis.Warning)

    def _apos_falhar(self, mensagem: str, camada):
        self._fechar_barra()
        self._limpar_tarefas()
        if mensagem == "cancelado":
            self._aviso("Download cancelado")
            return
        self._aviso(f"{camada.titulo[:50]}: {mensagem}", Qgis.Critical)

    def _abrir_pasta(self, caminho):
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(caminho)))

    def escolher_destino(self):
        atual = str(config.pasta_destino())
        novo = QFileDialog.getExistingDirectory(
            self, "Onde guardar os pacotes baixados", atual)
        if novo:
            config.gravar("destino", novo)
            self._aviso(f"Destino: {novo}")

    def atualizar_catalogo(self):
        """Baixa o catalogo completo do repositorio e reduz para a fatia SIG."""
        from qgis.core import QgsNetworkAccessManager
        from qgis.PyQt.QtCore import QUrl, QEventLoop
        from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply

        url = config.ler("url_catalogo")
        self._aviso("Baixando catálogo…")
        pedido = QNetworkRequest(QUrl(url))
        pedido.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        resposta = QgsNetworkAccessManager.instance().get(pedido)
        laco = QEventLoop()
        resposta.finished.connect(laco.quit)
        laco.exec()

        if resposta.error() != QNetworkReply.NetworkError.NoError:
            self._aviso(f"Não consegui baixar o catálogo: "
                        f"{resposta.errorString()}. Seguindo com o embutido.",
                        Qgis.Warning)
            return
        try:
            enxuto = cat.filtrar_sig_do_catalogo_completo(bytes(resposta.readAll()))
            alvo = config.pasta_catalogo_atualizado()
            alvo.write_bytes(enxuto)
        except Exception as e:
            self._aviso(f"O catálogo baixado não serviu ({e}). "
                        f"Seguindo com o embutido.", Qgis.Warning)
            return
        self.carregar_catalogo()
        self._aviso(f"Catálogo atualizado: {len(self.camadas)} camadas",
                    Qgis.Success)

    def _menu_contexto(self, ponto):
        camada = self._camada_selecionada()
        if camada is None:
            return
        menu = QMenu(self)
        menu.addAction("Baixar…", self.pedir_download)
        menu.addAction("Copiar link de download",
                       lambda: QgsApplication.clipboard().setText(camada.link))
        menu.addAction("Copiar ID do GEOSGB",
                       lambda: QgsApplication.clipboard().setText(camada.id))
        menu.exec(self.arvore.viewport().mapToGlobal(ponto))

    # ─── mensagens ───────────────────────────────────────────────────────────

    def _aviso(self, texto: str, nivel=Qgis.Info):
        self.iface.messageBar().pushMessage("Acervo CPRM", texto, level=nivel,
                                            duration=6)
        registrar(texto, nivel)
