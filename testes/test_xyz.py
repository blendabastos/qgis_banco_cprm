# -*- coding: utf-8 -*-
"""
test_xyz.py — O leitor de XYZ aerogeofisico do Geosoft.

Quase todo teste aqui trava um defeito que existiu de verdade durante o
desenvolvimento, ou uma peculiaridade medida nos 126 projetos do acervo. Os
casos de exemplo sao recortes reais dos arquivos do SGB, nao invencao.

    "C:\\Program Files\\QGIS 4.0.1\\bin\\python-qgis.bat" testes\\test_xyz.py
"""

import sys
import shutil
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acervo_cprm import xyz                         # noqa: E402


# ─── Recortes reais dos arquivos do acervo ───────────────────────────────────

#: Projeto 1114, Sudeste do Mato Grosso. Cabecalho moderno completo.
MODERNO = """\
/ ------------------------------------------------------------------------
/ XYZ EXPORT [07/31/2012]
/ DATABASE   [.\\Disco\\GDB\\1114_Mag.gdb]
/ ------------------------------------------------------------------------
/
/         X          Y FIDUCIAL     MAGCOR    LONGITUDE     LATITUDE
/========== ========== ======== ========== ============ ============
/
//Flight 172
//Date 2012/05/18
Line  17430
 545694.06 8306483.71   6497.1  23509.921 -50.57433683 -15.31775364
 545689.00 8306107.00   6498.1  23520.125 -50.57431000 -15.31800000
Tie  9010
 545646.00 8301132.00   6499.1  23460.661 -50.57420000 -15.31900000
"""

#: Projeto 1045, Palmeiropolis, 1979. Titulo ANTES da linha de nomes — pegar a
#: primeira linha "/" em vez da ultima devolvia o titulo, e 35 projetos
#: ficavam "sem nomes de coluna" quando na verdade os tinham.
ANTIGO = """\
/PROJETO AEROGEOFISICO PALMEIROPOLIS      CODIGO NA BASE AERO= 1045
/COORDENADAS UTM  ELIPSOIDE INTERNACIONAL DE HAYFORD (1910) MC= -51
/LINE-  50 A 690 (65 PERFIS)
/  UTME      UTMN    LONGITUDE    LATITUDE    MAGC
LINE    50.
  787207.  8540867. -48.350480  -13.185057  24908.40
  787208.  8540901. -48.350474  -13.184749  24908.70
"""

#: Projeto 1014, Serra da Mesa. Sem cabecalho, sem lat/long: Mercator
#: Equatorial sobre esfera Clarke 1880, documentado so num .doc do Word.
SAMMP = """\

LI 1
  -5.454484E+06 -1.374175E+06  2.525000E+04  2.525317E+04
  -5.454624E+06 -1.374032E+06  2.528000E+04  2.528317E+04

LI 2
  -5.452930E+06 -1.374179E+06  2.525000E+04  2.525519E+04
"""

#: Projeto 1009, Convenio Brasil-Alemanha. Grau.minuto.segundo separado por
#: ponto, e a LATITUDE vem primeiro.
GMS = """\
Line  1
   -15.27.08.20   -44.59.58.96      32.50     950.00
   -15.27.06.96   -44.59.24.03      32.50     950.00
Line  1.1
   -15.06.20.91   -44.28.00.72       6.50     950.00
"""

#: Projeto 3065, Gama.XYZ. Sem cabecalho. A coluna 1 tem valores entre 0,06 e
#: 0,18 — que passam como "latitude plausivel" e ficam dentro do Brasil, perto
#: do equador. A latitude de verdade e a coluna 3, A DIREITA da longitude.
VIZINHA_ENGANOSA = """\
//Flight 5
Line  10030
  608315.57   0.064  -49.997044  -13.999463
  610785.00   0.179  -49.974200  -13.999100
  609295.06   0.112  -49.985000  -13.999800
"""


def linhas(texto):
    return texto.splitlines(True)


class TesteLeituraDeValor(unittest.TestCase):

    def test_notacao_cientifica_do_geosoft(self):
        self.assertAlmostEqual(xyz.ler_numero("-5.454484E+06"), -5454484.0)

    def test_nulo_asterisco(self):
        """Aparece 244.506 vezes so no Gama.XYZ do projeto 3065."""
        self.assertIsNone(xyz.ler_numero("*"))

    def test_gms(self):
        self.assertAlmostEqual(xyz.ler_gms("-15.27.08.20"),
                               -(15 + 27 / 60 + 8.20 / 3600), places=9)

    def test_nan_e_inf_sao_tratados_como_ausentes(self):
        """
        O float() do Python aceita "nan" e "inf" de bom grado. Um NaN na coluna
        de coordenada viraria geometria em NaN, e a extensao da camada inteira
        iria junto — inclusive a verificacao que existe para pegar coordenada
        errada. Ausente e mais honesto que NaN.
        """
        for texto in ("nan", "NaN", "inf", "-inf", "1e400"):
            self.assertIsNone(xyz.ler_numero(texto), texto)

    def test_minuto_e_segundo_fora_da_faixa_sao_recusados(self):
        """
        O padrao casa dois digitos, entao "-15.99.99" passava e virava
        -16,6775: numero plausivel, dentro do Brasil, a uns 75 km do lugar
        certo. E o tipo de erro que ninguem percebe olhando o mapa.
        """
        self.assertIsNone(xyz.ler_gms("-15.99.99"))
        self.assertIsNone(xyz.ler_gms("-15.60.00"))
        self.assertIsNone(xyz.ler_gms("-15.00.60"))
        # o limite legitimo continua passando
        self.assertAlmostEqual(xyz.ler_gms("-15.59.59.9"),
                               -(15 + 59 / 60 + 59.9 / 3600), places=9)

    def test_gms_nao_engole_grau_decimal(self):
        """
        "-15.27" e longitude decimal legitima em 108 projetos. Se o padrao de
        grau-minuto-segundo casasse por prefixo, viraria -15o27'00" — erro de
        27 minutos de arco, uns 50 km, sem nada indicar que houve erro.
        """
        self.assertIsNone(xyz.ler_gms("-15.27"))
        self.assertAlmostEqual(xyz.ler_numero("-15.27"), -15.27)


class TesteCabecalho(unittest.TestCase):

    def test_pega_a_ultima_linha_de_comentario(self):
        """
        A convencao do Geosoft. Os projetos dos anos 80 abrem com um titulo em
        caixa alta e so depois vem os nomes; pegar a primeira linha "/" dava o
        titulo, e 35 projetos apareciam como "sem nomes de coluna".
        """
        nomes = xyz.nomes_do_cabecalho(linhas(ANTIGO))
        self.assertEqual(nomes, ["UTME", "UTMN", "LONGITUDE", "LATITUDE",
                                 "MAGC"])

    def test_descarta_a_regua_de_iguais(self):
        nomes = xyz.nomes_do_cabecalho(linhas(MODERNO))
        self.assertEqual(nomes[0], "X")
        self.assertIn("LATITUDE", nomes)

    def test_sem_cabecalho_devolve_none(self):
        self.assertIsNone(xyz.nomes_do_cabecalho(linhas(SAMMP)))


class TesteCoordenada(unittest.TestCase):

    def test_grau_por_nome_ganha_do_utm(self):
        """
        67 projetos trazem UTM e grau na mesma linha. O grau e melhor: dispensa
        saber o fuso e o datum da projecao.
        """
        e = xyz.analisar(linhas(MODERNO))
        self.assertEqual(e.forma, "grau")
        self.assertEqual((e.ix, e.iy), (4, 5))
        self.assertEqual(e.crs, "EPSG:4326")

    def test_fuso_deduzido_de_utm_e_longitude_juntos(self):
        """Sem documento nenhum: a longitude diz o fuso, o este confirma."""
        e = xyz.analisar(linhas(MODERNO))
        self.assertEqual(e.zona_observada, 22)

    def test_latitude_e_o_vizinho_da_DIREITA(self):
        """
        O defeito mais perigoso que apareceu neste modulo.

        No Gama.XYZ do 3065 ha uma coluna a esquerda da longitude com valores
        entre 0,06 e 0,18. Ela passa em qualquer teste de "isto parece uma
        latitude do Brasil" e fica perto do equador, dentro do pais — entao a
        verificacao de extensao NAO pegaria. A camada abriria, desenharia e
        estaria errada.

        A convencao do Geosoft e longitude, depois latitude. E ela que desempata.
        """
        e = xyz.analisar(linhas(VIZINHA_ENGANOSA))
        self.assertEqual((e.ix, e.iy), (2, 3),
                         "pegou a coluna enganosa a esquerda da longitude")

    def test_mercator_equatorial_por_faixa_de_valor(self):
        e = xyz.analisar(linhas(SAMMP))
        self.assertEqual(e.forma, "mercator_em")
        self.assertEqual((e.ix, e.iy), (0, 1))
        self.assertIn("6378249.145", e.crs)
        self.assertNotIn("EPSG", e.crs)

    def test_mercator_equatorial_cai_onde_deve(self):
        """Serra da Mesa fica em Goias, perto de -48,5 / -13,9."""
        e = xyz.analisar(linhas(SAMMP))
        lon, lat = xyz.para_lonlat(e, -5454484.0, -1374175.0)
        self.assertAlmostEqual(lon, -49.0, delta=0.6)
        self.assertAlmostEqual(lat, -12.4, delta=1.2)

    def test_gms_com_latitude_primeiro(self):
        e = xyz.analisar(linhas(GMS))
        self.assertEqual(e.forma, "gms")
        self.assertEqual((e.ix, e.iy), (1, 0), "latitude vem primeiro no 1009")
        lon, lat = xyz.para_lonlat(e, xyz.ler_gms("-44.59.58.96"),
                                  xyz.ler_gms("-15.27.08.20"))
        self.assertAlmostEqual(lon, -44.9997, places=3)
        self.assertAlmostEqual(lat, -15.4523, places=3)

    def test_rotulo_de_linha_em_tres_grafias(self):
        for texto, esperado in ((MODERNO, "Line"), (ANTIGO, "LINE"),
                                (SAMMP, "LI")):
            m = xyz.RE_ROTULO.match(
                [l for l in linhas(texto)
                 if xyz.RE_ROTULO.match(l.strip())][0].strip())
            self.assertEqual(m.group(1), esperado)


class TesteCrs(unittest.TestCase):

    def test_meridiano_central_vira_fuso(self):
        self.assertEqual(xyz.zona_do_meridiano(-51), 22)
        self.assertEqual(xyz.zona_do_meridiano(-39), 24)
        self.assertEqual(xyz.zona_do_meridiano(-63), 20)

    def test_hayford_e_corrego_alegre(self):
        """Como o SGB escrevia nos anos 80: "ELIPSOIDE INTERNACIONAL"."""
        self.assertEqual(
            xyz.epsg_utm(22, "ELIPSOIDE INTERNACIONAL HAYFORD 1910"),
            "EPSG:22522")

    def test_sem_datum_declarado_assume_sad69(self):
        self.assertEqual(xyz.epsg_utm(22, ""), "EPSG:29192")

    def test_sirgas_e_wgs_quando_declarados(self):
        self.assertEqual(xyz.epsg_utm(23, "SIRGAS 2000"), "EPSG:31983")
        self.assertEqual(xyz.epsg_utm(23, "WGS 84"), "EPSG:32723")

    def test_mc_do_proprio_arquivo(self):
        e = xyz.analisar(linhas(ANTIGO))
        # Este arquivo tem lat/long, entao vence o grau; o MC fica de reserva.
        self.assertEqual(e.forma, "grau")
        self.assertEqual(xyz.zona_do_meridiano(
            xyz.RE_MC.search(ANTIGO).group(1)), 22)

    def test_folha_do_ibge_no_nome_do_arquivo(self):
        """
        SB22XC2G.XYZ: o "22" e o fuso. A primeira versao exigia \\b depois dos
        digitos, e em "SB22XC2G" o "2" e o "X" sao ambos caracteres de palavra
        — nao ha fronteira ali, e o padrao nunca casava.
        """
        self.assertEqual(xyz.zona_do_nome("gama/SB22XC2G.XYZ"), 22)
        self.assertEqual(xyz.zona_do_nome("SD.22-Z-A-1.xyz"), 22)
        self.assertIsNone(xyz.zona_do_nome("1114_MagLine.XYZ"))

    def test_caixa_de_coordenadas_em_prosa(self):
        """Do carajas1.txt, que veio dentro do pacote do projeto 1047."""
        texto = ("01 - Limites aproximados :\n"
                 "  Latitudes (min/max) : - 10\xb000'/ -05\xb030'   "
                 "Longitudes (min/max) : -53\xb000' / -51\xb000'")
        self.assertEqual(xyz.caixa_do_texto(texto), (-53.0, -10.0, -51.0, -5.5))

    def test_fuso_vindo_do_leiame(self):
        """Do LEIAME.TXT do projeto 1054: "Datum SAD 29 - UTM zona 23S"."""
        texto = "Datum SAD 29 - UTM zona 23S"
        e = xyz.analisar(linhas(SEM_NOME_UTM), texto_auxiliar=texto)
        self.assertEqual(e.forma, "utm")
        self.assertEqual(e.crs, "EPSG:29193")

    def test_utm_sem_fuso_recusa_em_vez_de_chutar(self):
        e = xyz.analisar(linhas(SEM_NOME_UTM))
        self.assertEqual(e.forma, "utm")
        self.assertFalse(e.tem_coordenada)
        self.assertTrue(any("fuso" in a for a in e.avisos))


#: UTM nas colunas 0 e 1, sem nome de coluna e sem declaracao de fuso.
SEM_NOME_UTM = """\
Line  10030
  663225.38  7805184.00   24908.40
  664204.50  7806291.00   24909.70
  663800.00  7805900.00   24910.10
"""


class TesteVerificacao(unittest.TestCase):

    def test_extensao_fora_do_brasil_e_recusada(self):
        """
        Errar o CRS produz um arquivo que abre, desenha e esta errado.
        Aconteceu comigo durante o estudo: adivinhei as colunas de um arquivo
        sem cabecalho e a camada saiu com latitude 283.
        """
        e = xyz.analisar(linhas(MODERNO))
        problemas = xyz.verificar(e, (-50.5, 227.2, -49.5, 844.8))
        self.assertTrue(problemas)
        self.assertIn("fora do Brasil", problemas[0])

    def test_extensao_boa_passa(self):
        e = xyz.analisar(linhas(MODERNO))
        self.assertEqual(xyz.verificar(e, (-50.6, -15.4, -50.5, -15.3)), [])

    def test_verifica_sozinho_na_amostra(self):
        """Antes de converter 12 GB, nao depois."""
        e = xyz.analisar(linhas(MODERNO))
        self.assertIsNotNone(e.extensao_amostra)
        self.assertEqual(e.problemas, [])

    def test_gabarito_do_leiame_pega_area_errada(self):
        e = xyz.analisar(linhas(MODERNO))
        e.caixa_esperada = (-53.0, -10.0, -51.0, -5.5)      # Carajas
        problemas = xyz.verificar(e, (-50.6, -15.4, -50.5, -15.3))
        self.assertTrue(problemas)
        self.assertIn("leiame", problemas[0])


class TesteIrmaos(unittest.TestCase):

    def test_fuso_emprestado_entre_arquivos_do_pacote(self):
        """
        O 1114_Cruzamentos.XYZ tem X e Y e nenhum fuso; o 1114_MagLine.XYZ, no
        mesmo ZIP, tem X, Y, LONGITUDE e LATITUDE. Um resolve o outro.
        """
        com_grau = xyz.analisar(linhas(MODERNO))
        so_utm = xyz.analisar(linhas(SEM_NOME_UTM))
        self.assertFalse(so_utm.tem_coordenada)

        n = xyz.completar_com_irmaos([com_grau, so_utm])
        self.assertEqual(n, 1)
        self.assertEqual(so_utm.crs, "EPSG:29192")
        self.assertTrue(so_utm.tem_coordenada)
        self.assertFalse([a for a in so_utm.avisos if "fuso nao" in a])

    def test_nao_empresta_quando_os_irmaos_discordam(self):
        a = xyz.analisar(linhas(MODERNO))
        b = xyz.analisar(linhas(MODERNO))
        b.zona_observada = 21
        so_utm = xyz.analisar(linhas(SEM_NOME_UTM))
        self.assertEqual(xyz.completar_com_irmaos([a, b, so_utm]), 0)
        self.assertFalse(so_utm.tem_coordenada)


class TesteEstimativa(unittest.TestCase):

    #: Medicao de referencia: o Mag.XYZ do projeto 3065.
    #: 570 MB, 3.153.422 pontos, 82 s para GeoParquet com o progresso ligado.
    #:
    #: O tempo e o do caminho que o usuario percorre de verdade, nao o do
    #: melhor caso. A primeira versao usava os 60 s da escrita em GeoPackage
    #: sem indice e prometia um terco a menos de espera.
    REF_BYTES = 570 * 2**20
    REF_PONTOS = 3_153_422
    REF_SEGUNDOS = 82.0

    def test_bate_com_a_medicao_real(self):
        """
        A estimativa nao precisa ser exata — precisa nao mentir na ordem de
        grandeza, porque e o que decide se o usuario espera ou desiste.
        """
        pontos, segundos = xyz.estimar(self.REF_BYTES)
        self.assertAlmostEqual(pontos / self.REF_PONTOS, 1.0, delta=0.25)
        self.assertAlmostEqual(segundos / self.REF_SEGUNDOS, 1.0, delta=0.25)

    def test_nao_promete_mais_rapido_do_que_o_medido(self):
        """
        Errar para menos e pior que errar para mais: o usuario que espera 10
        minutos por uma barra que prometia 5 conclui que travou — foi
        exatamente a reclamacao que originou a barra de progresso.
        """
        _, segundos = xyz.estimar(self.REF_BYTES)
        self.assertGreaterEqual(segundos, self.REF_SEGUNDOS * 0.95)


class TesteConversao(unittest.TestCase):
    """Grava de verdade, com o GDAL. Precisa do ambiente do QGIS."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="xyz_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _converter(self, texto, **kw):
        esq = xyz.analisar(linhas(texto), **kw)
        alvo = self.tmp / "saida.gpkg"
        r = xyz.converter(lambda: linhas(texto), esq, alvo, formato="GPKG",
                          tamanho_total=len(texto))
        return esq, alvo, r

    def test_grava_pontos_com_linha_e_voo(self):
        from osgeo import ogr
        esq, alvo, r = self._converter(MODERNO)
        self.assertEqual(r["n"], 3)
        self.assertEqual(r["problemas"], [])

        ds = ogr.Open(str(alvo))
        camada = ds.GetLayer(0)
        self.assertEqual(camada.GetFeatureCount(), 3)
        f = camada.GetNextFeature()
        self.assertEqual(f.GetField("linha"), "17430")
        self.assertEqual(f.GetField("tipo_linha"), "line")
        self.assertEqual(f.GetField("voo"), "172")
        self.assertEqual(f.GetField("data_voo"), "2012/05/18")
        self.assertAlmostEqual(f.GetGeometryRef().GetX(), -50.57433683,
                               places=6)
        ds = None

    def test_linhas_de_controle_vao_junto_marcadas(self):
        """
        Tie e Line sao o mesmo levantamento. Separar em duas camadas obrigaria
        a abrir as duas para ver um mapa so; misturar sem marcar esconderia
        que uma delas e linha de controle.
        """
        from osgeo import ogr
        _, alvo, _ = self._converter(MODERNO)
        ds = ogr.Open(str(alvo))
        tipos = sorted({f.GetField("tipo_linha") for f in ds.GetLayer(0)})
        ds = None
        self.assertEqual(tipos, ["line", "tie"])

    def test_gms_e_gravado_em_grau_decimal(self):
        """
        A coluna e texto no arquivo ("-15.27.08.20"). Guardar a string crua
        obrigaria quem usa a tabela a repetir a conversao.
        """
        from osgeo import ogr
        esq, alvo, r = self._converter(GMS)
        self.assertEqual(r["n"], 3)
        ds = ogr.Open(str(alvo))
        f = ds.GetLayer(0).GetNextFeature()
        self.assertAlmostEqual(f.GetGeometryRef().GetY(), -15.4523, places=3)
        self.assertAlmostEqual(f.GetField(esq.nomes[esq.iy]), -15.4523,
                               places=3)
        ds = None

    def test_crs_sem_epsg_e_gravado(self):
        """O Mercator da familia SAMMP so existe como proj-string."""
        from osgeo import ogr
        _, alvo, r = self._converter(SAMMP)
        self.assertEqual(r["n"], 3)
        ds = ogr.Open(str(alvo))
        wkt = ds.GetLayer(0).GetSpatialRef().ExportToProj4()
        ds = None
        self.assertIn("merc", wkt)
        self.assertIn("6378249", wkt)

    def test_recusa_converter_sem_coordenada(self):
        esq = xyz.analisar(linhas(SEM_NOME_UTM))
        with self.assertRaises(ValueError):
            xyz.converter(lambda: linhas(SEM_NOME_UTM), esq,
                          self.tmp / "nao.gpkg", formato="GPKG")

    def test_parquet_sai_menor_que_geopackage(self):
        """
        Medido no acervo: 26,7 MB contra 95,1 MB para os mesmos 315.339 pontos.
        Aqui a amostra e minuscula, entao o teste so garante que o driver
        existe e grava — a vantagem de tamanho esta medida no README.
        """
        from osgeo import ogr
        if ogr.GetDriverByName("Parquet") is None:
            self.skipTest("driver Parquet ausente nesta instalacao")
        esq = xyz.analisar(linhas(MODERNO))
        alvo = self.tmp / "saida.parquet"
        r = xyz.converter(lambda: linhas(MODERNO), esq, alvo,
                          formato="Parquet")
        self.assertEqual(r["n"], 3)
        self.assertTrue(alvo.exists())


class TesteProgressoECancelamento(unittest.TestCase):
    """
    O progresso precisa chegar com frequencia, e o cancelamento precisa
    responder rapido. Os dois vieram de reclamacao de uso: rodando so como
    QgsTask, a conversao parecia travada.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="xyzp_"))
        # Pontos suficientes para cruzar o passo de progresso varias vezes.
        n = xyz.PASSO_PROGRESSO * 3 + 10
        corpo = ["/    LONGITUDE     LATITUDE      MAGCOR", "Line 10"]
        for i in range(n):
            corpo.append(" -50.5743%04d -15.3177%04d  23509.9"
                         % (i % 10000, i % 10000))
        self.texto = "\n".join(corpo) + "\n"
        self.esperados = n

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_o_passo_de_progresso_e_menor_que_o_lote(self):
        """
        Se fossem iguais, a barra so andaria a cada transacao — cerca de 4
        segundos a 53 mil pontos/s, que e tempo de sobra para parecer travado.
        """
        self.assertLess(xyz.PASSO_PROGRESSO, xyz.LOTE)
        self.assertEqual(xyz.LOTE % xyz.PASSO_PROGRESSO, 0)

    def test_progresso_e_chamado_varias_vezes(self):
        chamadas = []
        esq = xyz.analisar(linhas(self.texto))
        xyz.converter(lambda: linhas(self.texto), esq,
                      self.tmp / "p.gpkg", formato="GPKG",
                      progresso=lambda f, n: chamadas.append((f, n)),
                      tamanho_total=len(self.texto))
        self.assertGreaterEqual(len(chamadas), 3,
                                "a barra andaria pouco demais")
        fracoes = [f for f, _ in chamadas]
        self.assertEqual(fracoes, sorted(fracoes), "progresso andou para tras")
        self.assertLessEqual(max(fracoes), 1.0)
        self.assertEqual([n for _, n in chamadas],
                         sorted(n for _, n in chamadas))

    def test_cancelar_para_e_devolve_o_que_ja_saiu(self):
        from osgeo import ogr
        esq = xyz.analisar(linhas(self.texto))
        estado = {"n": 0}

        def progresso(_f, n):
            estado["n"] = n

        alvo = self.tmp / "c.gpkg"
        r = xyz.converter(lambda: linhas(self.texto), esq, alvo,
                          formato="GPKG", progresso=progresso,
                          cancelado=lambda: estado["n"] >= xyz.PASSO_PROGRESSO,
                          tamanho_total=len(self.texto))
        self.assertTrue(r["cancelado"])
        self.assertLess(r["n"], self.esperados,
                        "cancelou mas converteu tudo mesmo assim")

        # A transacao tem que ter sido fechada uma vez so: fechar duas vezes
        # e erro no driver, e nao fechar perde o ultimo lote.
        ds = ogr.Open(str(alvo))
        self.assertIsNotNone(ds, "o arquivo cancelado nem abre")
        self.assertEqual(ds.GetLayer(0).GetFeatureCount(), r["n"])
        ds = None

    def test_sem_cancelar_converte_tudo(self):
        esq = xyz.analisar(linhas(self.texto))
        r = xyz.converter(lambda: linhas(self.texto), esq,
                          self.tmp / "t.gpkg", formato="GPKG",
                          tamanho_total=len(self.texto))
        self.assertEqual(r["n"], self.esperados)
        self.assertFalse(r["cancelado"])


class TesteNomeDeSaida(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="xyzn_"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nao_colide_com_o_sufixo_que_o_plugin_esconde(self):
        """
        `config.SUFIXO_PONTOS` ("_pontos.gpkg") e IGNORADO por
        `listar_arquivos`: e o nome que o plugin da ao espacializar uma
        planilha de geoquimica, escondido para nao virar camada repetida.
        A saida do XYZ e o produto principal e precisa aparecer.
        """
        from acervo_cprm import config
        nome = "1114_MagLine" + xyz.SUFIXO_AQUISICAO + ".gpkg"
        self.assertFalse(nome.endswith(config.SUFIXO_PONTOS))

    def test_um_nome_por_formato(self):
        origem = self.tmp / "1117_MagLine.XYZ"
        self.assertEqual(xyz.caminho_de_saida(origem, "Parquet").name,
                         "1117_MagLine_aquisicao.parquet")
        self.assertEqual(xyz.caminho_de_saida(origem, "GPKG").name,
                         "1117_MagLine_aquisicao.gpkg")

    def test_acha_saida_de_qualquer_formato(self):
        """
        O caso do 1117. Converter de novo escolhendo outro formato deixava a
        saida anterior na pasta: o .parquet de 460 MB E o .gpkg de 2,61 GB do
        mesmo arquivo, os dois oferecidos como camada. Para apagar a antiga, e
        preciso primeiro achá-la — em qualquer formato, nao so no atual.
        """
        origem = self.tmp / "1117_MagLine.XYZ"
        origem.write_text("x", encoding="ascii")
        self.assertEqual(xyz.saidas_existentes(origem), [])

        (self.tmp / "1117_MagLine_aquisicao.parquet").write_text("a")
        (self.tmp / "1117_MagLine_aquisicao.gpkg").write_text("b")
        nomes = sorted(p.name for p in xyz.saidas_existentes(origem))
        self.assertEqual(nomes, ["1117_MagLine_aquisicao.gpkg",
                                 "1117_MagLine_aquisicao.parquet"])

    def test_nao_confunde_a_saida_de_outro_arquivo(self):
        origem = self.tmp / "1117_MagLine.XYZ"
        origem.write_text("x")
        (self.tmp / "1117_MagTie_aquisicao.parquet").write_text("a")
        self.assertEqual(xyz.saidas_existentes(origem), [])

    def test_todo_formato_do_dialogo_tem_extensao(self):
        """As duas listas precisam andar juntas, ou o seletor gera nome vazio."""
        from acervo_cprm.dialogo_xyz import DialogoXyz
        do_dialogo = {f for _, f in DialogoXyz.FORMATOS}
        self.assertEqual(do_dialogo, set(xyz.FORMATOS_SAIDA))


if __name__ == "__main__":
    from qgis.core import QgsApplication
    app = QgsApplication([], False)
    app.initQgis()
    try:
        unittest.main(exit=False, verbosity=2)
    finally:
        app.exitQgis()
