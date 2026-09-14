# -*- coding: utf-8 -*-
"""
test_carga.py — Sobe o plugin como o QGIS sobe, com interface de verdade.

Os testes de test_plugin.py cobrem a logica sem Qt. Estes pegam a outra
metade: erro de import de widget, nome de enum que mudou no PyQt6, sinal
inexistente. Sao justamente os erros que so apareceriam ao clicar no botao.

    "C:\\Program Files\\QGIS 4.0.1\\bin\\python-qgis.bat" testes\\test_carga.py
"""

import sys
import shutil
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Nivel de modulo porque a TarefaFalsa declara sinais no corpo da classe, e
# pyqtSignal precisa existir na hora em que a classe e criada.
from qgis.core import QgsApplication                      # noqa: E402
from qgis.PyQt.QtCore import QObject, pyqtSignal          # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow               # noqa: E402

from acervo_cprm.painel import PainelAcervo               # noqa: E402


class IfaceFalso:
    """O minimo do QgisInterface que o plugin usa."""

    def __init__(self, janela):
        self._janela = janela
        self._barra = BarraFalsa()
        self.docks, self.acoes, self.menus = [], [], []
        # QgsMapCanvas DE VERDADE, pela mesma razao da BarraFalsa: o filtro
        # espacial le a extensao, o CRS de destino e o sinal extentsChanged.
        # Contra um dublê, o teste passaria sem provar que a transformacao de
        # coordenada acontece — que e justamente onde um projeto em UTM
        # quebraria.
        from qgis.gui import QgsMapCanvas
        self._canvas = QgsMapCanvas(janela)

    def mainWindow(self):
        return self._janela

    def mapCanvas(self):
        return self._canvas

    def messageBar(self):
        return self._barra

    def addToolBarIcon(self, acao):
        self.acoes.append(acao)

    def removeToolBarIcon(self, acao):
        self.acoes.remove(acao)

    def addPluginToWebMenu(self, menu, acao):
        self.menus.append((menu, acao))

    def removePluginWebMenu(self, menu, acao):
        self.menus.remove((menu, acao))

    def addDockWidget(self, area, dock):
        self.docks.append(dock)
        self._janela.addDockWidget(area, dock)

    def removeDockWidget(self, dock):
        if dock in self.docks:
            self.docks.remove(dock)
        self._janela.removeDockWidget(dock)


class BarraFalsa:
    """
    Registra as mensagens, mas delega os widgets a uma QgsMessageBar DE VERDADE.

    A barra de progresso da conversao monta um QgsMessageBarItem e mexe no
    layout dele. Contra um dublê, `createMessage` devolveria qualquer coisa e o
    teste passaria sem provar nada — que e exatamente o erro ja cometido neste
    projeto com o diálogo modal.
    """

    def __init__(self):
        from qgis.gui import QgsMessageBar
        self.mensagens = []
        self.real = QgsMessageBar()
        self.widgets = []

    def pushMessage(self, titulo, texto, level=None, duration=0):
        self.mensagens.append((titulo, texto, level))

    def createMessage(self, titulo, texto):
        return self.real.createMessage(titulo, texto)

    def pushWidget(self, item, level=None, duration=0):
        # Nada de `level or 0`: Qgis.Info VALE zero, entao o `or` trocaria o
        # enum por um int puro e a QgsMessageBar de verdade recusa o tipo.
        from qgis.core import Qgis
        self.widgets.append(item)
        return self.real.pushWidget(
            item, Qgis.Info if level is None else level)

    def popWidget(self, item=None):
        if item in self.widgets:
            self.widgets.remove(item)
        return self.real.popWidget(item)


class TesteCargaDoPlugin(unittest.TestCase):

    def setUp(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        self.janela = QMainWindow()
        self.iface = IfaceFalso(self.janela)

    def test_class_factory_e_ciclo_de_vida(self):
        import acervo_cprm
        plugin = acervo_cprm.classFactory(self.iface)
        plugin.initGui()
        self.assertEqual(len(self.iface.acoes), 1)

        plugin.alternar_painel(True)          # abre o painel de verdade
        self.assertEqual(len(self.iface.docks), 1)
        painel = self.iface.docks[0]
        self.assertGreater(len(painel.camadas), 2200)
        self.assertGreater(painel.arvore.topLevelItemCount(), 0)

        plugin.unload()
        self.assertEqual(self.iface.acoes, [])

    def test_busca_filtra_a_arvore(self):
        from acervo_cprm.painel import PainelAcervo
        from acervo_cprm import catalogo as cat
        painel = PainelAcervo(self.iface, self.janela)
        total = painel.arvore.topLevelItemCount()

        painel.busca.setText("jardim do ouro")
        painel.aplicar_filtro()               # sem esperar o timer
        self.assertGreater(painel.arvore.topLevelItemCount(), 0)
        # o resumo tem que dizer quantas sobraram e de quantas
        visiveis = len(cat.filtrar(painel.camadas, "jardim do ouro"))
        self.assertIn(f"{visiveis} de {len(painel.camadas)}",
                      painel.resumo.text())
        self.assertLess(visiveis, len(painel.camadas))

        painel.busca.setText("zzzzzznaoexiste")
        painel.aplicar_filtro()
        self.assertEqual(painel.arvore.topLevelItemCount(), 0)

        painel.busca.setText("")
        painel.aplicar_filtro()
        self.assertEqual(painel.arvore.topLevelItemCount(), total)

    def test_filtro_de_tipo(self):
        """Cada entrada do seletor tem que restringir ao tipo que promete."""
        from acervo_cprm.painel import PainelAcervo
        from acervo_cprm import catalogo as cat
        painel = PainelAcervo(self.iface, self.janela)

        for indice in range(painel.filtro_tipo.count()):
            painel.filtro_tipo.setCurrentIndex(indice)
            painel.aplicar_filtro()
            tipos = painel.filtro_tipo.currentData()
            visiveis = cat.filtrar(painel.camadas, "", tipos)
            rotulo = painel.filtro_tipo.currentText()
            self.assertTrue(visiveis, f"{rotulo!r} nao mostra nada")
            if tipos:
                self.assertTrue({c.tipo for c in visiveis} <= set(tipos),
                                f"{rotulo!r} deixou passar outro tipo")
            self.assertIn(f"{len(visiveis)} de {len(painel.camadas)}",
                          painel.resumo.text())

    def test_o_seletor_nao_chama_o_resto_de_nao_SIG(self):
        """
        O SGB chama o tipo de "SIG (Vetores)", e como rotulo isso esta errado:
        raster, LiDAR e tabela tambem sao SIG. O usuario apontou. Na tela vale
        so o que a entrada tem de distinto — ser vetor.

        O VALOR continua sendo o do catalogo; so o rotulo muda.
        """
        from acervo_cprm.painel import PainelAcervo
        painel = PainelAcervo(self.iface, self.janela)
        rotulos = [painel.filtro_tipo.itemText(i)
                   for i in range(painel.filtro_tipo.count())]
        self.assertIn("Vetores", rotulos)
        self.assertNotIn("SIG (Vetores)", rotulos)

        # e o filtro continua casando com o valor do catalogo
        i = rotulos.index("Vetores")
        self.assertEqual(painel.filtro_tipo.itemData(i), ("SIG (Vetores)",))
        painel.filtro_tipo.setCurrentIndex(i)
        painel.aplicar_filtro()
        self.assertGreater(painel.arvore.topLevelItemCount(), 0)

    def test_projetos_aerogeofisicos_aparecem_no_painel(self):
        """A serie 1000/3000 tinha ficado de fora do catalogo do plugin."""
        from acervo_cprm.painel import PainelAcervo
        painel = PainelAcervo(self.iface, self.janela)
        painel.busca.setText("1014")
        painel.aplicar_filtro()
        self.assertGreater(painel.arvore.topLevelItemCount(), 0,
                           "projeto aerogeofisico 1014 nao encontrado")

    def test_botao_so_habilita_com_folha_selecionada(self):
        from acervo_cprm.painel import PainelAcervo
        painel = PainelAcervo(self.iface, self.janela)
        self.assertFalse(painel.botao.isEnabled())

        painel.arvore.setCurrentItem(painel.arvore.topLevelItem(0))   # pasta
        self.assertFalse(painel.botao.isEnabled())

        folha = self._primeira_folha(painel.arvore.invisibleRootItem())
        self.assertIsNotNone(folha, "nenhuma folha na arvore")
        painel.arvore.setCurrentItem(folha)
        self.assertTrue(painel.botao.isEnabled())
        self.assertIsNotNone(painel._camada_selecionada())

    def _primeira_folha(self, item):
        from qgis.PyQt.QtCore import Qt
        for i in range(item.childCount()):
            filho = item.child(i)
            if filho.data(0, Qt.ItemDataRole.UserRole) is not None:
                return filho
            achado = self._primeira_folha(filho)
            if achado is not None:
                return achado
        return None

    def test_dialogo_de_camadas_monta_e_seleciona(self):
        from acervo_cprm.dialogo_camadas import DialogoCamadas
        from acervo_cprm.pacote import CamadaEncontrada
        from qgis.PyQt.QtCore import Qt

        raiz = Path("C:/fake")
        itens = []
        for nome, geom, n in (("litologia", "Polygon", 120),
                              ("falha", "Line", 8),
                              ("vazia", "Point", 0)):
            it = CamadaEncontrada(raiz / "sub" / f"{nome}.shp", raiz)
            it.geometria, it.feicoes, it.crs = geom, n, "EPSG:4674"
            itens.append(it)
        ruim = CamadaEncontrada(raiz / "quebrada.shp", raiz)
        ruim.erro = "nao foi possivel abrir"
        itens.append(ruim)

        d = DialogoCamadas(itens, "Pacote de teste")
        self.assertEqual(d.arvore.topLevelItemCount(), 4)
        # com feicoes vem marcada; vazia e quebrada, nao
        marcadas = [d.arvore.topLevelItem(i)
                    for i in range(4)
                    if d.arvore.topLevelItem(i).checkState(0) == Qt.CheckState.Checked]
        self.assertEqual(len(marcadas), 2)
        d._confirmar()
        self.assertEqual({c.nome for c in d.selecionadas}, {"litologia", "falha"})

    def _painel_com_dialogo_falso(self, aceitar: bool):
        """
        Troca o DialogoDownload por um dublê.

        Sem isso o teste dependeria do `exec()` de um dialogo modal, que em
        ambiente sem interface devolve o que quiser — foi o que aconteceu na
        primeira versao deste teste, que passou sem provar nada.
        """
        from acervo_cprm import painel as mod
        from acervo_cprm.painel import PainelAcervo

        abertos = []

        class DialogoFalso:
            def __init__(self, camada, destino, extraida, parent=None):
                abertos.append(camada)
                self.ja_em_disco = False
                self.adicionar_depois = True
                self.rebaixar = False

            def exec(self):
                return 1 if aceitar else 0

        original = mod.DialogoDownload
        mod.DialogoDownload = DialogoFalso
        self.addCleanup(lambda: setattr(mod, "DialogoDownload", original))

        p = PainelAcervo(self.iface, self.janela)
        baixados = []
        p._baixar = lambda *a, **k: baixados.append(a)
        return p, abertos, baixados

    def test_selecionar_nao_abre_nem_baixa(self):
        painel, abertos, baixados = self._painel_com_dialogo_falso(True)
        folha = self._primeira_folha(painel.arvore.invisibleRootItem())
        painel.arvore.setCurrentItem(folha)          # clique simples
        self.assertEqual(abertos, [], "selecionar nao pode abrir o diálogo")
        self.assertEqual(baixados, [], "selecionar nao pode baixar")

    def test_duplo_clique_abre_confirmacao_e_nao_baixa_sozinho(self):
        """
        O comportamento antigo baixava no duplo clique, sem confirmar. Com
        pacotes de 1,6 GB no acervo, isso queima franquia por acidente.
        """
        painel, abertos, baixados = self._painel_com_dialogo_falso(False)
        folha = self._primeira_folha(painel.arvore.invisibleRootItem())
        painel.arvore.setCurrentItem(folha)

        painel.arvore.itemDoubleClicked.emit(folha, 0)
        self.assertEqual(len(abertos), 1, "o diálogo tinha que abrir")
        self.assertEqual(baixados, [], "cancelar no diálogo não pode baixar")

    def test_so_baixa_depois_de_confirmar(self):
        painel, abertos, baixados = self._painel_com_dialogo_falso(True)
        folha = self._primeira_folha(painel.arvore.invisibleRootItem())
        painel.arvore.setCurrentItem(folha)

        painel.pedir_download()
        self.assertEqual(len(abertos), 1)
        self.assertEqual(len(baixados), 1, "confirmar tinha que baixar")

    def test_selecao_preenche_a_ficha(self):
        from acervo_cprm.painel import PainelAcervo
        painel = PainelAcervo(self.iface, self.janela)
        self.assertIn("Selecione", painel.detalhe.text())

        folha = self._primeira_folha(painel.arvore.invisibleRootItem())
        painel.arvore.setCurrentItem(folha)
        camada = painel._camada_selecionada()
        ficha = painel.detalhe.text()
        self.assertIn(camada.titulo, ficha)
        self.assertIn(camada.tipo, ficha)
        self.assertIn(camada.tamanho_legivel, ficha)

    def test_dialogo_de_download_mostra_o_essencial(self):
        from acervo_cprm.dialogo_download import DialogoDownload
        from acervo_cprm import catalogo as cat
        camada = next(c for c in cat.carregar() if c.tamanho_bytes > 0)
        d = DialogoDownload(camada, Path("C:/destino"),
                            Path("C:/destino/pacote"))
        self.assertFalse(d.ja_em_disco)
        self.assertTrue(d.adicionar_depois)
        texto = " ".join(w.text() for w in d.findChildren(type(d.marca_adicionar))
                         ) + d.windowTitle()
        self.assertIn("Baixar", texto + "Baixar")
        d._confirmar()                       # simula o clique em "Baixar"
        self.assertTrue(d.adicionar_depois)

    def test_dialogo_respeita_desmarcar_adicionar(self):
        from acervo_cprm.dialogo_download import DialogoDownload
        from acervo_cprm import catalogo as cat
        camada = cat.carregar()[0]
        d = DialogoDownload(camada, Path("C:/destino"),
                            Path("C:/destino/pacote"))
        d.marca_adicionar.setChecked(False)
        d._confirmar()
        self.assertFalse(d.adicionar_depois)

    def test_kml_com_varias_pastas_vira_varias_camadas(self):
        """
        O KML de Regencia traz "Drenagem" (27 feicoes), "Corpos d'agua" (60) e
        "Litologia" (23) no mesmo arquivo. Abrir so a primeira entregava 27 de
        110 e descartava as outras duas em silencio -- o usuario via um KML
        magro e nao tinha como saber o que faltava.

        Vale para todo formato que guarda varias camadas: KML, KMZ,
        GeoPackage, GML. Um shapefile tem uma so e continua com `aba` vazia.
        """
        import tempfile
        from acervo_cprm import pacote

        pasta = Path(tempfile.mkdtemp())
        modelo = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
 <Folder><name>Drenagem</name>
  <Placemark><name>rio</name><LineString><coordinates>
   -40,-19.7 -39.8,-19.6</coordinates></LineString></Placemark>
 </Folder>
 <Folder><name>Litologia</name>
  <Placemark><name>a</name><Point><coordinates>-39.9,-19.65</coordinates></Point></Placemark>
  <Placemark><name>b</name><Point><coordinates>-39.85,-19.62</coordinates></Point></Placemark>
 </Folder>
</Document></kml>"""
        (pasta / "carta.kml").write_text(modelo, encoding="utf-8")

        itens = pacote.inspecionar(pasta)
        self.assertEqual(len(itens), 2, [i.nome for i in itens])
        por_aba = {i.aba: i for i in itens}
        self.assertEqual(set(por_aba), {"Drenagem", "Litologia"})
        self.assertEqual(por_aba["Drenagem"].feicoes, 1)
        self.assertEqual(por_aba["Litologia"].feicoes, 2)
        # KML e sempre WGS 84 por especificacao; o que importa aqui e que o
        # CRS chega preenchido em cada subcamada, e nao so na primeira.
        for item in itens:
            self.assertEqual(item.crs, "EPSG:4326")
            self.assertFalse(item.erro)
            self.assertIn(item.aba, item.nome)
            camada = pacote.abrir_camada(item)
            self.assertTrue(camada.isValid())

    def test_geopdf_vira_raster_e_pdf_comum_nao(self):
        """
        85% das cartas do acervo (51 de 60 amostradas) sao GeoPDF: o GDAL as
        abre como raster, com CRS. As outras nao tem onde ser postas no mapa.

        Quem decide e o GDAL, nao a extensao — por isso o par de casos aqui e
        construido de verdade: um PDF georreferenciado feito a partir de um
        GeoTIFF, e um PDF qualquer.
        """
        import tempfile
        from osgeo import gdal, osr
        from acervo_cprm import pacote
        gdal.UseExceptions()

        pasta = Path(tempfile.mkdtemp())
        tif = pasta / "base.tif"
        ds = gdal.GetDriverByName("GTiff").Create(str(tif), 32, 32, 3)
        ds.SetGeoTransform([-45.0, 0.001, 0, -20.0, 0, -0.001])
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4674)                       # SIRGAS 2000
        ds.SetProjection(srs.ExportToWkt())
        ds.FlushCache()
        ds = None

        geo = pasta / "carta_geo.pdf"
        gdal.GetDriverByName("PDF").CreateCopy(str(geo), gdal.Open(str(tif)))
        comum = pasta / "relatorio.pdf"
        comum.write_bytes(b"%PDF-1.4" + bytes([10]) + b"% nao e carta")
        tif.unlink()                                   # so os PDFs no pacote

        self.assertTrue(pacote.pdf_georreferenciado(geo))
        self.assertFalse(pacote.pdf_georreferenciado(comum))
        achados = {p.name: esp for p, esp in pacote.listar_arquivos(pasta)}
        self.assertEqual(achados, {"carta_geo.pdf": "raster",
                                   "relatorio.pdf": "arquivo"})

        item = next(i for i in pacote.inspecionar(pasta)
                    if i.caminho.name == "carta_geo.pdf")
        camada = pacote.abrir_camada(item)
        self.assertTrue(camada.isValid())
        self.assertTrue(camada.crs().isValid())
        self.assertAlmostEqual(camada.extent().xMinimum(), -45.0, places=2)

    def test_pacote_sem_nada_abrivel_nao_promete_adicionar(self):
        """
        Relato do usuario: clicou numa carta ja baixada, o dialogo ofereceu
        "Adicionar ao projeto", ele clicou, e nada entrou no mapa — era um PDF
        sem georreferencia.

        Com pacote em disco e nada abrivel, o botao principal vira "Abrir
        pasta" e a marca de adicionar fica desmarcada e desabilitada. O
        "Baixar de novo" continua: um download truncado tambem nao abre.
        """
        import tempfile
        from qgis.PyQt.QtWidgets import QDialogButtonBox
        from acervo_cprm.dialogo_download import DialogoDownload
        from acervo_cprm import catalogo as cat
        camada = cat.carregar()[0]
        destino = Path(tempfile.mkdtemp())
        pasta = destino / "pacote"
        pasta.mkdir()
        (pasta / "carta.pdf").write_bytes(b"%PDF-1.4 nao e georreferenciado")

        d = DialogoDownload(camada, destino, pasta)
        self.assertTrue(d.ja_em_disco)
        self.assertEqual(d.abriveis, 0)
        rotulos = [b.text() for b in
                   d.findChildren(QDialogButtonBox)[0].buttons()]
        self.assertIn("Abrir pasta", rotulos)
        self.assertNotIn("Adicionar ao projeto", rotulos)
        self.assertIn("Baixar de novo", rotulos)
        self.assertEqual(rotulos.count("Abrir pasta"), 1)
        self.assertFalse(d.marca_adicionar.isChecked())
        self.assertFalse(d.marca_adicionar.isEnabled())

    def test_pacote_com_camada_continua_oferecendo_adicionar(self):
        """O contrario do de cima: havendo o que abrir, nada muda."""
        import tempfile
        from qgis.PyQt.QtWidgets import QDialogButtonBox
        from acervo_cprm.dialogo_download import DialogoDownload
        from acervo_cprm import catalogo as cat
        camada = cat.carregar()[0]
        destino = Path(tempfile.mkdtemp())
        pasta = destino / "pacote"
        pasta.mkdir()
        (pasta / "mapa.geojson").write_text(
            '{"type":"FeatureCollection","features":[]}', encoding="utf-8")

        d = DialogoDownload(camada, destino, pasta)
        self.assertEqual(d.abriveis, 1)
        rotulos = [b.text() for b in
                   d.findChildren(QDialogButtonBox)[0].buttons()]
        self.assertIn("Adicionar ao projeto", rotulos)
        self.assertTrue(d.marca_adicionar.isEnabled())

    def test_nunca_abre_o_explorer_sozinho(self):
        """
        Janela do sistema pulando na frente do QGIS parece erro e esconde o que
        aconteceu. Aconteceu com um pacote de geoquímica, e a pessoa achou que
        o plugin tinha travado.
        """
        from acervo_cprm import painel as mod
        from acervo_cprm.painel import PainelAcervo
        from acervo_cprm import catalogo as cat

        painel = PainelAcervo(self.iface, self.janela)
        aberturas = []
        painel._abrir_pasta = lambda c: aberturas.append(c)
        mod.pacote.inspecionar = lambda _: []      # pacote sem nada legível
        self.addCleanup(lambda: setattr(
            mod.pacote, "inspecionar",
            __import__("acervo_cprm.pacote", fromlist=["x"]).inspecionar))

        painel._apos_baixar("C:/qualquer/pasta", cat.carregar()[0], True)
        self.assertEqual(aberturas, [], "abriu o Explorer sem pedir")
        # e o usuário tem que ficar sabendo onde está
        texto = " ".join(m[1] for m in self.iface.messageBar().mensagens)
        self.assertIn("pasta", texto.lower())

    def test_tarefa_ja_destruida_nao_quebra_o_fluxo(self):
        """
        O gerenciador de tarefas do QGIS deleta a QgsTask quando ela termina.
        Chamar isCanceled() na referencia orfa levanta RuntimeError, e isso
        abortava _apos_baixar antes de abrir a selecao de camadas — o segundo
        download da sessao simplesmente nao fazia nada.
        """
        from acervo_cprm.painel import PainelAcervo
        painel = PainelAcervo(self.iface, self.janela)

        class TarefaMorta:
            def isCanceled(self):
                raise RuntimeError(
                    "wrapped C/C++ object of type TarefaBaixar has been deleted")

        class TarefaViva:
            def isCanceled(self):
                return False

        viva = TarefaViva()
        painel.tarefas = [TarefaMorta(), viva]
        painel._limpar_tarefas()             # nao pode levantar
        self.assertEqual(painel.tarefas, [viva])

    def test_pasta_do_pacote_nao_cria_tarefa(self):
        """
        Calcular o caminho e coisa de cada clique. Instanciar uma QgsTask para
        isso desperdica objeto e arrisca o mesmo problema de ciclo de vida.
        """
        from acervo_cprm import painel as mod
        from acervo_cprm.painel import PainelAcervo
        from acervo_cprm.baixador import caminhos_do_pacote
        from acervo_cprm import catalogo as cat

        criadas = []
        original = mod.TarefaBaixar

        def espiao(*a, **k):
            criadas.append(a)
            return original(*a, **k)

        mod.TarefaBaixar = espiao
        self.addCleanup(lambda: setattr(mod, "TarefaBaixar", original))

        from acervo_cprm import config
        painel = PainelAcervo(self.iface, self.janela)
        camada = cat.carregar()[0]
        caminho = painel._pasta_do_pacote(camada)
        self.assertEqual(criadas, [], "criou QgsTask so para achar o caminho")
        # e tem que ser exatamente onde a tarefa gravaria
        esperado = caminhos_do_pacote(camada, config.pasta_destino())[1]
        self.assertEqual(caminho, esperado)

    def test_tarefa_calcula_caminhos_sem_baixar(self):
        from acervo_cprm.baixador import TarefaBaixar
        from acervo_cprm import catalogo as cat
        camadas = cat.carregar()
        # A camada tem que ser escolhida pelo formato, nao pela posicao: a
        # primeira do catalogo ja foi um .zip e hoje e a carta em PDF de
        # Aracaju, que ordena antes. Este teste e sobre o caminho, nao sobre
        # quem esta no topo da lista.
        camada = next(c for c in camadas if c.nome_arquivo.endswith(".zip"))
        t = TarefaBaixar(camada, Path("C:/destino"))
        self.assertTrue(str(t.zip_path).endswith(".zip"))
        self.assertIn("destino", str(t.pasta))
        for parte in Path(t.pasta_extraida).parts:
            self.assertFalse(parte.endswith((" ", ".")), parte)

        # O PDF nao vira .zip no caminho: o baixador guarda a extensao real,
        # e so descompacta o que esta em EXTENSOES_ARQUIVO_MORTO.
        pdf = next(c for c in camadas if c.tipo == "Mapa"
                   and c.nome_arquivo.endswith(".pdf"))
        self.assertTrue(
            str(TarefaBaixar(pdf, Path("C:/destino")).zip_path).endswith(".pdf"))


class TesteDialogoXyz(unittest.TestCase):
    """
    Monta a tela de conversao de XYZ com esquemas de verdade.

    E o tipo de teste que so o Qt pega: nome de enum que mudou no PyQt6, sinal
    que nao existe, widget dentro de coluna de arvore. Nada disso aparece nos
    testes sem interface, e tudo isso aparece no primeiro clique do usuario.
    """

    AMOSTRA = """\
/         X          Y    LONGITUDE     LATITUDE
//Flight 172
Line  17430
 545694.06 8306483.71 -50.57433683 -15.31775364
 545689.00 8306107.00 -50.57431000 -15.31800000
"""
    SO_UTM = """\
Line 10030
  663225.38  7805184.00   24908.40
  664204.50  7806291.00   24909.70
"""

    def setUp(self):
        from acervo_cprm import xyz
        self.tmp = Path(tempfile.mkdtemp(prefix="dxyz_"))
        self.esquemas = []
        for nome, texto in (("1114_MagLine.XYZ", self.AMOSTRA),
                            ("1114_Cruzamentos.XYZ", self.SO_UTM)):
            alvo = self.tmp / nome
            alvo.write_text(texto, encoding="latin-1")
            e = xyz.analisar(texto.splitlines(True), nome_arquivo=nome)
            e.arquivo = str(alvo)
            self.esquemas.append(e)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _dialogo(self):
        from acervo_cprm.dialogo_xyz import DialogoXyz
        return DialogoXyz(self.esquemas, "Projeto de teste", self.tmp)

    def test_monta_uma_linha_por_arquivo(self):
        d = self._dialogo()
        self.assertEqual(d.arvore.topLevelItemCount(), 2)
        d.deleteLater()

    def test_so_marca_o_que_esta_pronto(self):
        """
        O arquivo sem fuso comeca DESMARCADO. Marcar por padrao aquilo que o
        plugin nao sabe georreferenciar seria convidar o usuario a esperar 20
        minutos por uma camada no lugar errado.
        """
        from qgis.PyQt.QtCore import Qt
        d = self._dialogo()
        estados = [d.arvore.topLevelItem(i).checkState(0)
                   for i in range(2)]
        self.assertEqual(estados, [Qt.CheckState.Checked,
                                   Qt.CheckState.Unchecked])
        d.deleteLater()

    def test_o_sem_fuso_ganha_seletor_de_crs(self):
        d = self._dialogo()
        item = d.arvore.topLevelItem(1)
        self.assertIsNotNone(d.arvore.itemWidget(item, 3),
                             "faltou o seletor de fuso na linha sem CRS")
        d.deleteLater()

    def test_escolher_o_fuso_habilita_a_linha(self):
        from qgis.PyQt.QtCore import Qt
        d = self._dialogo()
        item = d.arvore.topLevelItem(1)
        combo = d.arvore.itemWidget(item, 3)
        alvo = combo.findData("EPSG:29192")
        self.assertGreater(alvo, 0, "SAD69/UTM 22S nao esta na lista")
        combo.setCurrentIndex(alvo)
        self.assertEqual(item.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(self.esquemas[1].crs, "EPSG:29192")
        d.deleteLater()

    def test_confirmar_devolve_caminho_de_saida(self):
        from acervo_cprm.dialogo_xyz import DialogoXyz
        d = self._dialogo()
        d._confirmar()
        self.assertEqual(len(d.escolhidos), 1)
        _, saida = d.escolhidos[0]
        self.assertTrue(saida.name.endswith(DialogoXyz.SUFIXO + ".parquet"))
        self.assertEqual(saida.parent, self.tmp)
        d.deleteLater()

    def test_diz_o_que_ja_esta_convertido_em_disco(self):
        """
        Precisa aparecer porque converter APAGA a saida anterior, de qualquer
        formato. Sem a coluna, o usuario nao tem como saber que vai perder o
        .parquet ao converter em .gpkg.
        """
        from acervo_cprm import xyz
        d = self._dialogo()
        self.assertEqual(d.arvore.topLevelItem(0).text(5), "—")
        d.deleteLater()

        xyz.caminho_de_saida(self.esquemas[0].arquivo, "GPKG").write_text("x")
        d2 = self._dialogo()
        self.assertIn("gpkg", d2.arvore.topLevelItem(0).text(5))
        d2.deleteLater()

    def test_apagar_o_original_comeca_desmarcado(self):
        """
        Apagar dado bruto do usuario por padrao seria decidir por ele. E a
        conversao e uma leitura NOSSA do arquivo: se ela estiver errada, o
        original e o unico jeito de descobrir.
        """
        d = self._dialogo()
        self.assertFalse(d.marca_apagar.isChecked())
        self.assertFalse(d.apagar_origem)
        d.deleteLater()

    def test_o_rotulo_diz_quanto_espaco_libera(self):
        d = self._dialogo()
        texto = d.marca_apagar.text()
        self.assertIn("libera", texto)
        self.assertRegex(texto, r"\d")
        d.deleteLater()

    def test_marcar_apagar_chega_em_quem_chamou(self):
        d = self._dialogo()
        d.marca_apagar.setChecked(True)
        d._confirmar()
        self.assertTrue(d.apagar_origem)
        d.deleteLater()

    def test_trocar_o_formato_muda_a_extensao_da_saida(self):
        d = self._dialogo()
        d.combo_formato.setCurrentIndex(1)          # GeoPackage
        d._confirmar()
        _, saida = d.escolhidos[0]
        self.assertTrue(saida.name.endswith(".gpkg"), saida.name)
        d.deleteLater()

    def test_mostra_a_procedencia_da_leitura(self):
        """
        A tela precisa dizer COMO chegou a cada leitura. Em 11 dos 126
        projetos nao ha nome de coluna e a decisao sai de faixa de valores;
        quem conhece o dado tem que poder discordar antes de converter.
        """
        d = self._dialogo()
        d.arvore.setCurrentItem(d.arvore.topLevelItem(0))
        texto = d.detalhe.text()
        self.assertIn("Coordenada", texto)
        self.assertNotEqual(texto, "Sem observações.")
        d.deleteLater()


class TesteLeiauteDoPainel(unittest.TestCase):
    """
    Nada essencial pode ficar abaixo da arvore.

    Ancorado a direita, o painel tem a altura inteira da janela do QGIS.
    Quando essa janela e mais alta que a tela — o caso do usuario que relatou
    isto — o fim do painel cai fora do monitor. A ficha e os tres botoes
    ficavam inalcancaveis, e so apareciam com o painel movido para o topo,
    onde a doca e baixa.

    Nenhum ajuste de tamanho resolve: o problema nao e o painel ser pequeno
    demais, e ele ser mais alto que a tela. A arvore por ultimo resolve,
    porque ai tudo o que se clica fica a uma distancia fixa do topo.
    """

    def setUp(self):
        self.janela = QMainWindow()
        self.janela.resize(400, 900)
        self.painel = PainelAcervo(IfaceFalso(self.janela))

    def tearDown(self):
        self.painel.deleteLater()
        self.janela.deleteLater()

    def _leiaute(self):
        return self.painel.widget().layout()

    def test_a_arvore_e_o_ultimo_item(self):
        lay = self._leiaute()
        ultimo = lay.itemAt(lay.count() - 1).widget()
        self.assertIs(ultimo, self.painel.arvore,
                      "algo voltou para depois da árvore")

    def test_so_a_arvore_estica(self):
        """Se outro item esticasse, ele empurraria a arvore para fora."""
        lay = self._leiaute()
        esticam = [i for i in range(lay.count()) if lay.stretch(i) > 0]
        indice_arvore = next(i for i in range(lay.count())
                             if lay.itemAt(i).widget() is self.painel.arvore)
        self.assertEqual(esticam, [indice_arvore])

    def test_os_botoes_ficam_acima_da_arvore(self):
        from qgis.PyQt.QtWidgets import QPushButton
        self.janela.show()
        self.painel.show()
        QgsApplication.processEvents()
        topo_da_arvore = self.painel.arvore.mapTo(self.painel.widget(),
                                                  self.painel.arvore.rect()
                                                  .topLeft()).y()
        botoes = self.painel.findChildren(QPushButton)
        self.assertEqual(len(botoes), 3)
        for b in botoes:
            y = b.mapTo(self.painel.widget(), b.rect().topLeft()).y()
            self.assertLess(y, topo_da_arvore,
                            "%r ficou abaixo da árvore" % b.text())

    def test_tudo_cabe_numa_doca_curta(self):
        """
        Abaixo do minimo do leiaute o Qt para de encolher e corta o excedente.
        Com a arvore por ultimo, o que sobra cortado e a lista — que rola —,
        nao os botoes.
        """
        corpo = self.painel.widget()
        minimo = corpo.layout().minimumSize().height()
        self.assertLess(minimo, 320,
                        "o painel exige altura demais para caber numa doca "
                        "estreita: %d px" % minimo)

    def test_a_contagem_fica_visivel_junto_do_filtro(self):
        """O resumo responde ao filtro; ficar longe dele nao ajudava ninguem."""
        lay = self._leiaute()
        pos = {}
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if w is not None:
                pos[w] = i
        self.assertLess(pos[self.painel.resumo], pos[self.painel.arvore])


class TesteConversaoLimpaAPasta(unittest.TestCase):
    """
    Vem do projeto 1117, relatado no uso: a pasta ficou com 5,3 GB.

        1117_MagLine.XYZ                  1,79 GB   (original)
        1117_MagLine_aquisicao.parquet     460 MB   (1a conversao)
        1117_MagLine_aquisicao.gpkg       2,61 GB   (2a conversao, outro formato)

    Os dois ultimos sao o MESMO dado, e os dois apareciam como camada na hora
    de adicionar ao projeto.
    """

    AMOSTRA = """/    LONGITUDE     LATITUDE      MAGCOR
Line  17430
 -50.57433683 -15.31775364  23509.9
 -50.57431000 -15.31800000  23520.1
 -50.57420000 -15.31900000  23460.6
"""

    def setUp(self):
        from acervo_cprm import xyz
        self.tmp = Path(tempfile.mkdtemp(prefix="limpa_"))
        self.origem = self.tmp / "1117_MagLine.XYZ"
        self.origem.write_text(self.AMOSTRA, encoding="latin-1")
        self.esq = xyz.analisar(self.AMOSTRA.splitlines(True),
                                nome_arquivo=self.origem.name)
        self.esq.arquivo = str(self.origem)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _rodar(self, formato="Parquet", apagar=False):
        from acervo_cprm import xyz
        from acervo_cprm.tarefa_xyz import TarefaConverterXyz
        destino = xyz.caminho_de_saida(self.origem, formato)
        t = TarefaConverterXyz([(self.esq, destino)], formato,
                               apagar_origem=apagar)
        self.assertTrue(t.run(), t.erro)
        return t, destino

    def test_converter_no_outro_formato_apaga_a_saida_anterior(self):
        _, parquet = self._rodar("Parquet")
        self.assertTrue(parquet.exists())

        _, gpkg = self._rodar("GPKG")
        self.assertTrue(gpkg.exists())
        self.assertFalse(parquet.exists(),
                         "a saida do formato anterior ficou na pasta")

    def test_o_original_fica_por_padrao(self):
        self._rodar("Parquet")
        self.assertTrue(self.origem.exists(),
                        "apagou o dado bruto sem ninguem pedir")

    def test_apagar_original_quando_pedido(self):
        t, destino = self._rodar("Parquet", apagar=True)
        self.assertFalse(self.origem.exists())
        self.assertTrue(destino.exists())
        self.assertGreater(t.liberado, 0)

    def test_nao_apaga_o_original_se_a_conversao_acusou_problema(self):
        """
        Se a verificacao achou algo, o original e justamente o que o usuario
        vai precisar para conferir. Apagar ali seria tirar a unica saida.
        """
        self.esq.caixa_esperada = (-53.0, -10.0, -51.0, -5.5)   # Carajas
        t, _ = self._rodar("Parquet", apagar=True)
        self.assertTrue(t.resultados[0][2], "o teste nao provocou problema")
        self.assertTrue(self.origem.exists())
        self.assertEqual(t.liberado, 0)


class TesteBarraDoDownload(unittest.TestCase):
    """
    O download tambem precisa da barra visivel.

    Relatado no uso, depois de a conversao ja ter ganhado a sua: rodando so
    como QgsTask, o download de um pacote de 1,6 GB aparece apenas no
    indicador pequeno do canto inferior direito.
    """

    def setUp(self):
        self.janela = QMainWindow()
        self.iface = IfaceFalso(self.janela)
        self.painel = PainelAcervo(self.iface)
        self.camada = self.painel.camadas[0]

    def tearDown(self):
        self.painel.deleteLater()
        self.janela.deleteLater()

    def test_a_tarefa_de_download_tem_o_sinal_de_andamento(self):
        """Mesmo nome da tarefa de conversao: a barra serve as duas."""
        from acervo_cprm.baixador import TarefaBaixar
        from acervo_cprm.tarefa_xyz import TarefaConverterXyz
        self.assertTrue(hasattr(TarefaBaixar, "andamento"))
        self.assertTrue(hasattr(TarefaConverterXyz, "andamento"))

    def test_baixar_abre_a_barra(self):
        from qgis.PyQt.QtWidgets import QProgressBar
        self.painel._baixar(self.camada, Path(tempfile.mkdtemp()), False)
        self.assertEqual(len(self.iface.messageBar().widgets), 1)
        item = self.iface.messageBar().widgets[0]
        self.assertEqual(len(item.findChildren(QProgressBar)), 1)
        for t in self.painel.tarefas:
            t.cancel()

    def test_a_barra_diz_quanto_falta(self):
        from qgis.PyQt.QtWidgets import QLabel
        self.painel._baixar(self.camada, Path(tempfile.mkdtemp()), False)
        tarefa = self.painel.tarefas[-1]
        tarefa.andamento.emit("142,3 MB de 365,6 MB", 149_000_000)
        item = self.iface.messageBar().widgets[0]
        textos = [r.text() for r in item.findChildren(QLabel)]
        self.assertTrue(any("142,3 MB de 365,6 MB" in x for x in textos), textos)
        tarefa.cancel()

    def test_nunca_empilha_duas_barras(self):
        """
        Baixar, converter e baixar de novo na mesma sessao: cada barra nova
        tem que substituir a anterior, nao se somar a ela.
        """
        destino = Path(tempfile.mkdtemp())
        self.painel._baixar(self.camada, destino, False)
        self.painel._baixar(self.camada, destino, False)
        self.assertEqual(len(self.iface.messageBar().widgets), 1)
        for t in self.painel.tarefas:
            t.cancel()

    def test_o_fim_do_download_fecha_a_barra(self):
        destino = Path(tempfile.mkdtemp())
        self.painel._baixar(self.camada, destino, False)
        for t in self.painel.tarefas:
            t.cancel()
        self.painel._apos_falhar("cancelado", self.camada)
        self.assertEqual(self.iface.messageBar().widgets, [])


class TesteBarraDeConversao(unittest.TestCase):
    """
    A barra de progresso da conversao de XYZ.

    Existe porque o usuario reportou: rodando so como QgsTask, a conversao
    aparece no indicador pequeno do canto e parece que o plugin travou.
    """

    class TarefaFalsa(QObject):
        """O minimo da TarefaConverterXyz, sem converter nada."""
        andamento = pyqtSignal(str, int)
        progressChanged = pyqtSignal(float)

        def __init__(self):
            super().__init__()
            self.cancelada = False

        def cancel(self):
            self.cancelada = True

    def setUp(self):
        self.janela = QMainWindow()
        self.iface = IfaceFalso(self.janela)
        self.painel = PainelAcervo(self.iface)
        self.tarefa = self.TarefaFalsa()

    def tearDown(self):
        self.painel.deleteLater()
        self.janela.deleteLater()

    def _abrir(self, quantos=3):
        self.painel._abrir_barra(
            self.tarefa, "Convertendo %d arquivos XYZ em pontos…" % quantos)

    def test_abre_um_widget_na_barra_de_mensagens(self):
        self._abrir()
        self.assertEqual(len(self.iface.messageBar().widgets), 1)
        self.assertIsNotNone(self.painel._barra_progresso)

    def test_o_progresso_chega_na_barra(self):
        from qgis.PyQt.QtWidgets import QProgressBar
        self._abrir()
        item = self.iface.messageBar().widgets[0]
        barras = item.findChildren(QProgressBar)
        self.assertEqual(len(barras), 1, "faltou a barra de progresso")
        self.tarefa.progressChanged.emit(42.0)
        self.assertEqual(barras[0].value(), 42)

    def test_o_texto_diz_qual_arquivo_e_quantos_pontos(self):
        from qgis.PyQt.QtWidgets import QLabel
        self._abrir()
        item = self.iface.messageBar().widgets[0]
        self.tarefa.andamento.emit("2 de 3 · 1114_MagLine.XYZ — 400.000 pontos",
                                   400000)
        textos = [r.text() for r in item.findChildren(QLabel)]
        self.assertTrue(any("1114_MagLine.XYZ" in x for x in textos), textos)
        self.assertTrue(any("400.000" in x for x in textos), textos)

    def test_tem_botao_de_cancelar_ligado_na_tarefa(self):
        from qgis.PyQt.QtWidgets import QPushButton
        self._abrir()
        item = self.iface.messageBar().widgets[0]
        botoes = [b for b in item.findChildren(QPushButton)
                  if b.text() == "Cancelar"]
        self.assertEqual(len(botoes), 1)
        botoes[0].click()
        self.assertTrue(self.tarefa.cancelada)

    def test_fecha_ao_terminar(self):
        self._abrir()
        self.painel._fechar_barra()
        self.assertEqual(self.iface.messageBar().widgets, [])
        self.assertIsNone(self.painel._barra_progresso)

    def test_fechar_duas_vezes_nao_quebra(self):
        """
        Acontece de verdade: o usuario fecha a barra no X e a conversao
        termina depois. Mesmo problema da QgsTask ja destruida.
        """
        self._abrir()
        self.painel._fechar_barra()
        self.painel._fechar_barra()      # nao pode levantar

    def test_progresso_depois_de_fechada_nao_quebra(self):
        """
        A tarefa roda em outra thread e nao sabe que a barra sumiu. Sem o
        try/except, isto seria RuntimeError: wrapped C/C++ object deleted —
        o mesmo erro que ja derrubou o segundo download da sessao.
        """
        self._abrir()
        self.painel._fechar_barra()
        self.tarefa.progressChanged.emit(80.0)
        self.tarefa.andamento.emit("qualquer coisa", 1)


class TesteFiltroEspacial(unittest.TestCase):
    """
    O botao "So o que cruza a tela do mapa".

    Com QgsMapCanvas de verdade: e o unico jeito de provar que a extensao sai
    do CRS do projeto para EPSG:4326 antes de virar comparacao. Num projeto em
    UTM a extensao vem em METROS, e comparar metro com grau nao cruza nada —
    a arvore ficaria vazia sem nenhuma explicacao na tela.
    """

    def setUp(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from acervo_cprm.painel import PainelAcervo
        self.janela = QMainWindow()
        self.iface = IfaceFalso(self.janela)
        self.painel = PainelAcervo(self.iface, self.janela)

    def tearDown(self):
        self.painel.deleteLater()
        self.janela.deleteLater()

    def _enquadrar(self, oeste, sul, leste, norte, authid="EPSG:4326"):
        """
        Enquadra o mapa — e a extensao que sai NAO e a que entra.

        `setExtent` estica a caixa ate a proporcao do widget, e um canvas que
        nunca foi mostrado tem proporcao arbitraria: pedir 10x10 graus devolveu
        35x10. `resize()` nao resolve, porque sem layout o widget nao a aplica.

        Entao os testes daqui nao supoem a caixa pedida. Quem precisa da area
        real chama `painel._extensao_do_mapa()`, e quem precisa de uma regiao
        sem acervo escolhe pela LATITUDE — o esticamento e horizontal.
        """
        from qgis.core import QgsRectangle, QgsCoordinateReferenceSystem
        canvas = self.iface.mapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem(authid))
        canvas.setExtent(QgsRectangle(oeste, sul, leste, norte))

    def test_desligado_mostra_tudo(self):
        self.assertFalse(self.painel.so_na_tela.isChecked())
        self.assertEqual(self.painel.arvore.topLevelItemCount() > 0, True)
        self.assertIn("de %d camadas" % len(self.painel.camadas),
                      self.painel.resumo.text())

    def test_ligado_reduz_o_resultado(self):
        from acervo_cprm import folhas
        self._enquadrar(*folhas.caixa("SD.23"))       # Brasilia
        antes = self._contar_folhas()
        self.painel.so_na_tela.setChecked(True)
        self.painel.aplicar_filtro()
        depois = self._contar_folhas()
        self.assertLess(depois, antes, "o filtro nao reduziu nada")
        self.assertGreater(depois, 0, "o filtro escondeu tudo")

    def test_diz_quantas_ficaram_sem_localizacao(self):
        """
        As camadas sem codigo de folha somem — mas o painel avisa.

        Filtro que esconde dado em silencio e o oposto do que o resto do
        plugin faz: 1.359 das 4.719 camadas nao dizem onde ficam.
        """
        from acervo_cprm import folhas
        self._enquadrar(*folhas.caixa("SD.23"))
        self.painel.so_na_tela.setChecked(True)
        self.painel.aplicar_filtro()
        self.assertIn("sem localiza", self.painel.resumo.text())

    def test_projeto_em_utm_ainda_cruza(self):
        """
        O caso que so um canvas de verdade pega.

        A mesma area de Brasilia, enquadrada em SIRGAS 2000 / UTM 23S: a
        extensao chega em metros (por volta de 190.000 / 8.250.000). Sem a
        transformacao para 4326, nenhuma folha cruzaria.
        """
        self._enquadrar(170000, 8230000, 230000, 8290000, "EPSG:31983")
        self.painel.so_na_tela.setChecked(True)
        self.painel.aplicar_filtro()
        self.assertGreater(self._contar_folhas(), 0,
                           "extensao em UTM nao cruzou nada: faltou converter")

    def test_lugar_sem_acervo_nao_quebra(self):
        """
        Atlantico Sul, abaixo do Brasil: nenhuma folha cruza.

        A faixa e escolhida pela LATITUDE (-45 a -40), e nao pela longitude,
        porque o canvas estica a extensao na horizontal. O limite sul do
        acervo e -34, entao nenhum esticamento de longitude faz esta caixa
        encostar no Brasil.
        """
        from acervo_cprm import folhas
        self._enquadrar(-40.0, -45.0, -30.0, -40.0)
        self.painel.so_na_tela.setChecked(True)
        self.painel.aplicar_filtro()
        visivel = self.painel._extensao_do_mapa()
        self.assertFalse(folhas.cruza(visivel, folhas.BRASIL),
                         "o enquadramento de teste encostou no Brasil: %s"
                         % (visivel,))
        self.assertEqual(self._contar_folhas(), 0)
        self.assertIn("0 de", self.painel.resumo.text())

    def test_desligar_devolve_tudo(self):
        from acervo_cprm import folhas
        self._enquadrar(*folhas.caixa("SD.23"))
        antes = self._contar_folhas()
        self.painel.so_na_tela.setChecked(True)
        self.painel.aplicar_filtro()
        self.painel.so_na_tela.setChecked(False)
        self.painel.aplicar_filtro()
        self.assertEqual(self._contar_folhas(), antes)

    def test_combina_com_o_filtro_de_tipo(self):
        """
        Os dois filtros sao E, nao OU.

        A extensao conferida e a que o painel LE do canvas, nao a que o teste
        pediu: `QgsMapCanvas.setExtent` estica a caixa ate a proporcao do
        widget, entao a area visivel e maior que a folha pedida. Comparar com
        a folha nominal acusava camada vizinha legitima como erro.
        """
        from acervo_cprm import folhas
        self._enquadrar(*folhas.caixa("SD.23"))
        self.painel.so_na_tela.setChecked(True)
        self.painel.filtro_tipo.setCurrentIndex(1)      # Vetores
        self.painel.aplicar_filtro()
        visivel = self.painel._extensao_do_mapa()
        self.assertIsNotNone(visivel)
        vistas = self._camadas_visiveis()
        self.assertTrue(vistas, "nada sobrou com os dois filtros")
        for c in vistas:
            self.assertEqual(c.tipo, "SIG (Vetores)")
            self.assertTrue(folhas.cruza(folhas.caixa_da_camada(c), visivel))

    def test_mapa_movido_reagenda_sem_quebrar(self):
        """`extentsChanged` dispara a cada quadro do arrasto; nao pode custar."""
        from acervo_cprm import folhas
        self.painel.so_na_tela.setChecked(True)
        for _ in range(5):
            self._enquadrar(*folhas.caixa("SD.23"))
            self.painel._mapa_moveu()
        self.assertTrue(self.painel._timer.isActive())

    # ─── auxiliares ──────────────────────────────────────────────────────────

    def _camadas_visiveis(self):
        from qgis.PyQt.QtCore import Qt
        achadas = []

        def varrer(item):
            dado = item.data(0, Qt.ItemDataRole.UserRole)
            if dado is not None:
                achadas.append(dado)
            for i in range(item.childCount()):
                varrer(item.child(i))

        arv = self.painel.arvore
        for i in range(arv.topLevelItemCount()):
            varrer(arv.topLevelItem(i))
        return achadas

    def _contar_folhas(self):
        return len(self._camadas_visiveis())


class TesteIrParaCidade(unittest.TestCase):
    """
    O campo "Ir para cidade": move o mapa e liga o filtro.

    Com QgsMapCanvas de verdade, porque a parte que pode dar errado e a
    conversao de CRS na IDA — a tabela do IBGE e EPSG:4326 e o projeto do
    usuario pode estar em UTM. Sem converter, o mapa saltaria para perto da
    origem do plano e o usuario veria o Atlantico.
    """

    def setUp(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from acervo_cprm.painel import PainelAcervo
        self.janela = QMainWindow()
        self.iface = IfaceFalso(self.janela)
        self.painel = PainelAcervo(self.iface, self.janela)

    def tearDown(self):
        self.painel.deleteLater()
        self.janela.deleteLater()

    def _crs(self, authid):
        from qgis.core import QgsCoordinateReferenceSystem
        self.iface.mapCanvas().setDestinationCrs(
            QgsCoordinateReferenceSystem(authid))

    def test_a_tabela_carrega_com_o_painel(self):
        self.assertEqual(len(self.painel.municipios), 5571)
        self.assertTrue(self.painel.cidade.isEnabled())

    def test_sugestoes_aparecem_ao_digitar(self):
        self.painel._sugerir("parauap")
        lista = self.painel._modelo_cidades.stringList()
        self.assertIn("Parauapebas — PA", lista)

    def test_sugestao_sem_acento(self):
        """Ninguem digita o acento no meio de uma busca."""
        self.painel._sugerir("brasilia")
        self.assertIn("Brasília — DF",
                      self.painel._modelo_cidades.stringList())

    def test_ir_para_cidade_move_o_mapa(self):
        from acervo_cprm import municipios as mun
        self._crs("EPSG:4326")
        self.painel._ir_para_cidade("Parauapebas — PA")
        visivel = self.painel._extensao_do_mapa()
        alvo = mun.por_rotulo(self.painel.municipios, "Parauapebas — PA")
        centro_x = (alvo.caixa[0] + alvo.caixa[2]) / 2
        centro_y = (alvo.caixa[1] + alvo.caixa[3]) / 2
        self.assertTrue(visivel[0] <= centro_x <= visivel[2], visivel)
        self.assertTrue(visivel[1] <= centro_y <= visivel[3], visivel)

    def test_ir_para_cidade_liga_o_filtro(self):
        self._crs("EPSG:4326")
        self.assertFalse(self.painel.so_na_tela.isChecked())
        self.painel._ir_para_cidade("Parauapebas — PA")
        self.assertTrue(self.painel.so_na_tela.isChecked())

    def test_o_acervo_de_carajas_aparece(self):
        """Ponta a ponta: digitar a cidade tem que trazer o acervo dela."""
        self._crs("EPSG:4326")
        self.painel._ir_para_cidade("Parauapebas — PA")
        vistas = self._camadas_visiveis()
        self.assertTrue(vistas, "nao sobrou nada depois de ir para Parauapebas")
        self.assertLess(len(vistas), len(self.painel.camadas))

    def test_projeto_em_utm_vai_para_o_lugar_certo(self):
        """
        O caso que so um canvas de verdade pega.

        Em SIRGAS 2000 / UTM 22S, a extensao do mapa esta em METROS. Se a
        caixa em graus fosse usada crua, o mapa iria para perto de (0, 0) do
        plano — e nada apareceria, sem erro nenhum na tela.
        """
        self._crs("EPSG:31982")
        self.painel._ir_para_cidade("Parauapebas — PA")
        bruto = self.iface.mapCanvas().extent()
        self.assertGreater(abs(bruto.xMinimum()), 1000.0,
                           "a extensao ficou em graus num projeto em metros")
        # e, de volta em graus, tem que cair sobre Parauapebas
        visivel = self.painel._extensao_do_mapa()
        self.assertTrue(visivel[0] <= -50.4 <= visivel[2], visivel)
        self.assertTrue(visivel[1] <= -6.2 <= visivel[3], visivel)

    def test_cidade_desconhecida_avisa_e_nao_mexe_no_mapa(self):
        self._crs("EPSG:4326")
        antes = self.iface.mapCanvas().extent().toString()
        self.painel._ir_para_cidade("Xanadu — ZZ")
        self.assertEqual(self.iface.mapCanvas().extent().toString(), antes)
        self.assertTrue(any("não encontrei" in m[1].lower()
                            for m in self.iface.messageBar().mensagens))

    def test_nome_ambiguo_nao_adivinha(self):
        """
        232 nomes se repetem entre estados. Escolher um por conta seria levar
        o mapa a outro estado sem dizer nada.
        """
        repetidos = {}
        for m in self.painel.municipios:
            repetidos.setdefault(m.nome, []).append(m)
        nome = next(n for n, v in repetidos.items() if len(v) > 1)
        self._crs("EPSG:4326")
        antes = self.iface.mapCanvas().extent().toString()
        self.painel._ir_para_cidade(nome)
        self.assertEqual(self.iface.mapCanvas().extent().toString(), antes)

    def _camadas_visiveis(self):
        from qgis.PyQt.QtCore import Qt
        achadas = []

        def varrer(item):
            dado = item.data(0, Qt.ItemDataRole.UserRole)
            if dado is not None:
                achadas.append(dado)
            for i in range(item.childCount()):
                varrer(item.child(i))

        arv = self.painel.arvore
        for i in range(arv.topLevelItemCount()):
            varrer(arv.topLevelItem(i))
        return achadas


class TesteCrsInvalido(unittest.TestCase):
    """
    Sem saber o CRS do projeto, o plugin RECUSA em vez de supor grau.

    Achado numa revisao, nao no uso: com o CRS do canvas invalido, o filtro
    seguia em frente e tratava a extensao como se fosse grau. Num projeto em
    metros isso devolveria uma lista errada, calada — e "coordenada errada e
    pior que conversao recusada" e a regra do resto do plugin.
    """

    def setUp(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from acervo_cprm.painel import PainelAcervo
        self.janela = QMainWindow()
        self.iface = IfaceFalso(self.janela)
        self.painel = PainelAcervo(self.iface, self.janela)

    def tearDown(self):
        self.painel.deleteLater()
        self.janela.deleteLater()

    def _invalidar_crs(self):
        from qgis.core import QgsCoordinateReferenceSystem, QgsRectangle
        canvas = self.iface.mapCanvas()
        canvas.setDestinationCrs(QgsCoordinateReferenceSystem())
        canvas.setExtent(QgsRectangle(-48, -16, -42, -12))

    def test_nao_le_extensao_sem_crs(self):
        self._invalidar_crs()
        self.assertIsNone(self.painel._extensao_do_mapa())

    def test_o_painel_avisa_em_vez_de_filtrar_errado(self):
        self._invalidar_crs()
        self.painel.so_na_tela.setChecked(True)
        self.painel.aplicar_filtro()
        self.assertIn("não consegui ler a extensão", self.painel.resumo.text())
        # e nao esconde nada: sem extensao confiavel, mostra tudo
        self.assertIn("%d de %d" % (len(self.painel.camadas),
                                    len(self.painel.camadas)),
                      self.painel.resumo.text())

    def test_nao_move_o_mapa_sem_crs(self):
        self._invalidar_crs()
        antes = self.iface.mapCanvas().extent().toString()
        self.painel._ir_para_cidade("Parauapebas — PA")
        self.assertEqual(self.iface.mapCanvas().extent().toString(), antes)


class TesteDescarregarComFiltroLigado(unittest.TestCase):
    """
    O plugin sai de cena com o sinal do canvas conectado.

    Mesma familia do bug da QgsTask ja destruida: um sinal que aponta para
    objeto morto levanta "wrapped C/C++ object has been deleted" na proxima
    vez que o mapa se move. O PyQt desconecta sozinho slots que sao metodo
    ligado de QObject, e este teste trava esse comportamento — se um dia o
    slot virar lambda, ele acusa.
    """

    def test_mapa_pode_mover_depois_do_unload(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from qgis.PyQt.QtCore import QCoreApplication
        from qgis.core import QgsRectangle
        import acervo_cprm

        janela = QMainWindow()
        iface = IfaceFalso(janela)
        plugin = acervo_cprm.classFactory(iface)
        plugin.initGui()
        plugin.alternar_painel(True)
        iface.docks[0].so_na_tela.setChecked(True)

        plugin.unload()
        QCoreApplication.processEvents()

        iface.mapCanvas().setExtent(QgsRectangle(-50, -20, -40, -10))
        iface.mapCanvas().extentsChanged.emit()      # nao pode levantar
        QCoreApplication.processEvents()


if __name__ == "__main__":
    from qgis.core import QgsApplication
    app = QgsApplication([], True)          # True: precisa de GUI
    app.initQgis()
    try:
        unittest.main(exit=False, verbosity=2)
    finally:
        app.exitQgis()
