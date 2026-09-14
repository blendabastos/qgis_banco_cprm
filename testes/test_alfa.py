# -*- coding: utf-8 -*-
"""
test_alfa.py — A banda alfa que tira a moldura branca dos GeoTIFF.

    "C:\\Program Files\\QGIS 4.0.1\\bin\\python-qgis.bat" testes\\test_alfa.py
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np                                   # noqa: E402
from osgeo import gdal                               # noqa: E402

from acervo_cprm import alfa                         # noqa: E402


def gravar_rgb(caminho, dados, bandas_extras=0, nodata=None, tipo=None):
    """Grava um GeoTIFF com as bandas de `dados` (n, h, w)."""
    n, h, w = dados.shape
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(str(caminho), w, h, n + bandas_extras,
                    tipo or gdal.GDT_Byte)
    ds.SetGeoTransform((-50.0, 0.001, 0, -15.0, 0, -0.001))
    ds.SetProjection('GEOGCS["WGS 84",DATUM["WGS_1984",'
                     'SPHEROID["WGS 84",6378137,298.257223563]],'
                     'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]')
    for i in range(n):
        ds.GetRasterBand(i + 1).WriteArray(dados[i])
        if nodata is not None:
            ds.GetRasterBand(i + 1).SetNoDataValue(nodata)
    ds.FlushCache()
    ds = None
    return caminho


def mapa_com_moldura(h=40, w=30, buraco_branco=False):
    """
    Uma faixa de dado colorida dentro de uma moldura branca.

    Com `buraco_branco`, poe tambem um bloco branco NO MEIO do dado — que e o
    que acontece num ternario, onde branco significa K, Th e U altos ao mesmo
    tempo.
    """
    a = np.full((3, h, w), 255, dtype=np.uint8)
    a[0, 8:h - 8, 6:w - 6] = 30          # dado: vermelho baixo
    a[1, 8:h - 8, 6:w - 6] = 200
    a[2, 8:h - 8, 6:w - 6] = 90
    if buraco_branco:
        a[:, 18:22, 12:16] = 255
    return a


class TesteDeteccao(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="alfa_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reconhece_o_geotiff_da_geofisica(self):
        p = gravar_rgb(self.tmp / "a.tif", mapa_com_moldura())
        self.assertTrue(alfa.precisa_de_alfa(p))

    def test_ignora_quem_ja_tem_quatro_bandas(self):
        """Rodar duas vezes nao pode empilhar bandas."""
        p = gravar_rgb(self.tmp / "b.tif", mapa_com_moldura(), bandas_extras=1)
        self.assertFalse(alfa.precisa_de_alfa(p))

    def test_ignora_quem_ja_declara_nodata(self):
        """Se o arquivo ja diz qual e o fundo, nao somos nos que decidimos."""
        p = gravar_rgb(self.tmp / "c.tif", mapa_com_moldura(), nodata=255)
        self.assertFalse(alfa.precisa_de_alfa(p))

    def test_ignora_raster_sem_moldura_branca(self):
        a = mapa_com_moldura()
        a[:, 0, 0] = (10, 20, 30)
        p = gravar_rgb(self.tmp / "d.tif", a)
        self.assertFalse(alfa.precisa_de_alfa(p))

    def test_ignora_raster_que_nao_e_byte(self):
        """Grade cientifica de verdade nao e caso nosso."""
        a = mapa_com_moldura().astype(np.float32)
        p = gravar_rgb(self.tmp / "e.tif", a, tipo=gdal.GDT_Float32)
        self.assertFalse(alfa.precisa_de_alfa(p))

    def test_nao_quebra_com_arquivo_que_nao_abre(self):
        ruim = self.tmp / "f.tif"
        ruim.write_bytes(b"isto nao e um tiff")
        self.assertFalse(alfa.precisa_de_alfa(ruim))


class TestePreenchimento(unittest.TestCase):
    """O que separa fundo de dado: alcancar a moldura, nao ser branco."""

    def test_moldura_inteira_e_fundo(self):
        a = mapa_com_moldura()
        branco = (a[0] == 255) & (a[1] == 255) & (a[2] == 255)
        fundo = alfa.fundo_alcancavel(branco)
        self.assertTrue(fundo[0, 0])
        self.assertTrue(fundo[-1, -1])
        self.assertFalse(fundo[20, 15])          # dentro do dado

    def test_branco_cercado_por_dado_NAO_e_fundo(self):
        """
        O caso que decide o desenho inteiro.

        Nos 19 GeoTIFF medidos, 15 tem o branco todo encostado na moldura. Mas
        o 1017_TERNARIO tem 24 ilhas de branco cercadas por dado, somando 3.231
        pixels, e o 1030_TERNARIO_RGB tem 49. Ali branco significa K, Th e U
        altos ao mesmo tempo — e anomalia, nao fundo. Tratar cor como fundo
        furaria o mapa exatamente em cima do que interessa.
        """
        a = mapa_com_moldura(buraco_branco=True)
        branco = (a[0] == 255) & (a[1] == 255) & (a[2] == 255)
        fundo = alfa.fundo_alcancavel(branco)
        self.assertTrue(branco[20, 14], "o teste nao criou o buraco")
        self.assertFalse(fundo[20, 14],
                         "furou o dado: branco interno virou transparente")
        self.assertTrue(fundo[0, 0])

    def test_nao_vaza_por_encontro_diagonal(self):
        """
        Vizinhanca de 4, nao de 8: o fundo nao atravessa um toque diagonal de
        um pixel. Na duvida o pixel fica opaco — deixar um ponto branco a mais
        e visivel e corrigivel; furar o dado passa despercebido.
        """
        branco = np.zeros((9, 9), dtype=bool)
        branco[0, :] = True                  # moldura em cima
        branco[4:7, 4:7] = True              # bloco solto no meio
        branco[3, 3] = True                  # so encosta na diagonal
        fundo = alfa.fundo_alcancavel(branco)
        self.assertTrue(fundo[0, 0])
        self.assertFalse(fundo[5, 5], "vazou pela diagonal")

    def test_sem_branco_nenhum_nao_marca_nada(self):
        self.assertFalse(alfa.fundo_alcancavel(
            np.zeros((5, 5), dtype=bool)).any())


class TesteAplicacao(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="alfaap_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _aplicar(self, dados, nome="x.tif"):
        p = gravar_rgb(self.tmp / nome, dados)
        antes = gdal.Open(str(p)).ReadAsArray()
        mudou = alfa.aplicar(p)
        ds = gdal.Open(str(p))
        depois = ds.ReadAsArray()
        cor = ds.GetRasterBand(4).GetColorInterpretation() if ds.RasterCount > 3 else None
        ds = None
        return mudou, antes, depois, cor

    def test_acrescenta_a_quarta_banda_marcada_como_alfa(self):
        mudou, _, depois, cor = self._aplicar(mapa_com_moldura())
        self.assertTrue(mudou)
        self.assertEqual(depois.shape[0], 4)
        self.assertEqual(cor, gdal.GCI_AlphaBand)

    def test_o_rgb_sai_byte_a_byte_igual(self):
        """
        Mexer no arquivo do usuario so se justifica se o dado nao mudar. Aqui
        a unica diferenca e a banda que nao existia.
        """
        _, antes, depois, _ = self._aplicar(mapa_com_moldura())
        self.assertTrue(np.array_equal(antes, depois[:3]))

    def test_georreferencia_preservada(self):
        p = gravar_rgb(self.tmp / "g.tif", mapa_com_moldura())
        gt_antes = gdal.Open(str(p)).GetGeoTransform()
        pr_antes = gdal.Open(str(p)).GetProjection()
        alfa.aplicar(p)
        ds = gdal.Open(str(p))
        self.assertEqual(ds.GetGeoTransform(), gt_antes)
        self.assertEqual(ds.GetProjection(), pr_antes)
        ds = None

    def test_o_fundo_fica_transparente_e_o_dado_opaco(self):
        _, _, depois, _ = self._aplicar(mapa_com_moldura())
        self.assertEqual(depois[3][0, 0], 0)
        self.assertEqual(depois[3][20, 15], 255)

    def test_o_branco_interno_continua_opaco(self):
        _, _, depois, _ = self._aplicar(mapa_com_moldura(buraco_branco=True))
        self.assertEqual(depois[3][20, 14], 255,
                         "a anomalia do ternário virou buraco")

    def test_aplicar_duas_vezes_nao_muda_nada(self):
        """
        O download chama isto tambem em pacote que ja estava em disco. Uma
        segunda passada nao pode virar uma quinta banda.
        """
        p = gravar_rgb(self.tmp / "h.tif", mapa_com_moldura())
        self.assertTrue(alfa.aplicar(p))
        self.assertFalse(alfa.aplicar(p))
        self.assertEqual(gdal.Open(str(p)).RasterCount, 4)

    def test_nao_deixa_arquivo_temporario_para_tras(self):
        p = gravar_rgb(self.tmp / "i.tif", mapa_com_moldura())
        alfa.aplicar(p)
        sobrou = [x.name for x in self.tmp.iterdir() if ".tmp" in x.name]
        self.assertEqual(sobrou, [])

    def test_a_pasta_inteira_de_uma_vez(self):
        for i in range(3):
            gravar_rgb(self.tmp / ("m%d.tif" % i), mapa_com_moldura())
        (self.tmp / "leiame.txt").write_text("nao sou raster")
        self.assertEqual(alfa.aplicar_na_pasta(self.tmp), 3)
        self.assertEqual(alfa.aplicar_na_pasta(self.tmp), 0)

    def test_um_arquivo_ruim_nao_derruba_os_outros(self):
        """
        Dezesseis GeoTIFF bons nao podem ficar inutilizaveis por causa de um
        estranho no meio do pacote.
        """
        gravar_rgb(self.tmp / "bom.tif", mapa_com_moldura())
        (self.tmp / "quebrado.tif").write_bytes(b"nada a ver")
        self.assertEqual(alfa.aplicar_na_pasta(self.tmp), 1)


class TesteNoQgis(unittest.TestCase):
    """O QGIS tem que usar o alfa sozinho, sem ninguem configurar nada."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="alfaq_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_o_fundo_some_na_renderizacao(self):
        from qgis.core import (QgsRasterLayer, QgsMapSettings,
                               QgsMapRendererParallelJob)
        from qgis.PyQt.QtCore import QSize
        from qgis.PyQt.QtGui import QColor

        p = gravar_rgb(self.tmp / "r.tif", mapa_com_moldura())
        alfa.aplicar(p)
        camada = QgsRasterLayer(str(p), "r")
        self.assertTrue(camada.isValid())
        self.assertEqual(camada.bandCount(), 4)

        cfg = QgsMapSettings()
        cfg.setLayers([camada])
        cfg.setExtent(camada.extent())
        cfg.setOutputSize(QSize(60, 80))
        cfg.setDestinationCrs(camada.crs())
        cfg.setBackgroundColor(QColor(255, 0, 255))   # magenta atras
        j = QgsMapRendererParallelJob(cfg)
        j.start()
        j.waitForFinished()
        img = j.renderedImage()

        canto = QColor(img.pixel(1, 1))
        self.assertGreater(canto.red(), 200)
        self.assertLess(canto.green(), 60)
        self.assertGreater(canto.blue(), 200)        # magenta: passou direto
        meio = QColor(img.pixel(30, 40))
        self.assertLess(meio.red(), 120, "o dado virou transparente também")


if __name__ == "__main__":
    from qgis.core import QgsApplication
    app = QgsApplication([], False)
    app.initQgis()
    try:
        unittest.main(exit=False, verbosity=2)
    finally:
        app.exitQgis()
