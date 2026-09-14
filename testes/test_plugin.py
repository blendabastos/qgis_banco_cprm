# -*- coding: utf-8 -*-
"""
Testes do plugin. Rodam headless contra o QGIS de verdade:

    "C:\\Program Files\\QGIS 4.0.1\\bin\\python-qgis.bat" testes\\test_plugin.py

Os que tocam a rede sao marcados e podem ser pulados:

    ... testes\\test_plugin.py --sem-rede
"""

import io
import csv
import os
import sys
import zipfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acervo_cprm import catalogo as cat          # noqa: E402
from acervo_cprm import pacote                    # noqa: E402
from acervo_cprm import config                    # noqa: E402
from acervo_cprm.baixador import caminhos_do_pacote  # noqa: E402

#: O catalogo completo vive no projeto irmao "Banco CPRM"; quem clonar so o
#: plugin nao o tem, e o teste que depende dele se declara skip.
ORIGEM_COMPLETA = (Path(__file__).resolve().parent.parent.parent
                  / "Banco CPRM" / "catalogo.csv")

COM_REDE = "--sem-rede" not in sys.argv


# ─── catalogo ────────────────────────────────────────────────────────────────

class TesteCatalogo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.camadas = cat.carregar()

    def test_carrega_o_embutido(self):
        self.assertGreater(len(self.camadas), 2200)
        self.assertTrue(all(c.id and c.link for c in self.camadas))

    def test_todo_link_e_absoluto(self):
        ruins = [c for c in self.camadas if not c.link.startswith("https://")]
        self.assertEqual(ruins, [], "link relativo no catalogo")

    def test_so_tem_os_tipos_declarados(self):
        """
        A lista vem de config, que e a mesma fonte que o gerador do catalogo
        usa — se as duas divergirem, este teste acusa.

        "Mapa" entra (a carta da folha, em PDF); "Relatorio" nao.
        """
        from acervo_cprm.config import TIPOS_INCLUIDOS
        presentes = {c.tipo for c in self.camadas}
        self.assertTrue(presentes <= set(TIPOS_INCLUIDOS),
                        f"tipo inesperado: {presentes - set(TIPOS_INCLUIDOS)}")
        self.assertIn("Mapa", presentes)
        self.assertNotIn("Relatório", presentes)

    def test_os_tipos_so_download_sao_tipos_do_catalogo(self):
        """TIPOS_SO_DOWNLOAD nomeia tipos que existem; um erro de digitacao
        ali faria o painel abrir o dialogo de camadas para um PDF."""
        from acervo_cprm import config
        self.assertTrue(set(config.TIPOS_SO_DOWNLOAD)
                        <= set(config.TIPOS_INCLUIDOS))
        self.assertTrue(set(config.TIPOS_SO_DOWNLOAD)
                        <= {c.tipo for c in self.camadas})
        self.assertEqual(set(config.TIPOS_ABRIVEIS),
                         set(config.TIPOS_INCLUIDOS)
                         - set(config.TIPOS_SO_DOWNLOAD))

    def test_atualizar_pelo_repositorio_da_o_mesmo_catalogo(self):
        """
        Sao dois filtros para a mesma pergunta: gerar_catalogo.py monta o
        catalogo embutido, e filtrar_sig_do_catalogo_completo o refaz quando o
        usuario manda atualizar. Enquanto o segundo filtrava por `eh_sig`, a
        carta em PDF sumia ao atualizar — o usuario perdia 2.062 itens por
        clicar num botao que promete o contrario.
        """
        origem = ORIGEM_COMPLETA
        if not origem.exists():
            self.skipTest("catalogo.csv completo nao esta nesta maquina")
        reduzido = cat.filtrar_sig_do_catalogo_completo(origem.read_bytes())
        self.assertEqual(len(cat.ler_csv(reduzido)), len(self.camadas))

    def test_inclui_as_tabelas_de_geoquimica(self):
        tabelas = [c for c in self.camadas if c.tipo.startswith("Geoquímica")]
        self.assertGreater(len(tabelas), 300, "faltam as análises geoquímicas")

    def test_nem_tudo_e_zip(self):
        """
        112 arquivos do acervo sao .las/.jp2 soltos e 129 sao planilhas. Uma
        versao anterior renomeava tudo para .zip e a extracao morria.
        """
        from acervo_cprm.baixador import caminhos_do_pacote
        naozip = [c for c in self.camadas if c.formato != ".zip"]
        self.assertTrue(naozip)
        for c in naozip[:40]:
            arquivo, _ = caminhos_do_pacote(c, Path("C:/destino"))
            self.assertTrue(arquivo.name.lower().endswith(c.formato),
                            f"{c.nome_arquivo} virou {arquivo.name}")

    def test_nenhum_pacote_chega_perto_do_limite_do_windows(self):
        r"""
        O bug que mais voltou. `rglob` sem o prefixo \\?\ devolve lista VAZIA
        acima de 260 caracteres, em silencio — o plugin dizia "nenhum arquivo
        que o QGIS abra" com 13 arquivos na pasta.

        Espelhar a arvore do acervo deixava 267 dos 5.258 pacotes acima de 260
        antes mesmo de abrir o ZIP. Com dois niveis curtos — tipo e pacote — o
        pior caso cai para ~208.

        O limite de 230 aqui e folga deliberada: o caminho da PASTA e so metade
        da conta — ainda vem o nome interno do arquivo dentro do ZIP, que quem
        escolhe e o SGB.
        """
        destino = config.destino_padrao()
        piores = []
        for c in self.camadas:
            _, pasta = caminhos_do_pacote(c, destino)
            piores.append((len(str(pasta)), c.titulo, str(pasta)))
        piores.sort(reverse=True)
        n, titulo, caminho = piores[0]
        self.assertLess(
            n, 230,
            "caminho de %d caracteres: %s | %s" % (n, titulo, caminho))

    def test_o_pacote_fica_um_nivel_abaixo_do_destino(self):
        """
        destino / <pasta do pacote> / arquivo. Um nivel, nada mais.

        A pasta do pacote existe para isolar o conteudo de cada ZIP. Acima dela
        nao inventamos nada: nem a arvore de quatro niveis do acervo, que
        estourava os 260, nem uma pasta por tipo — agrupar e escolha de quem
        usa, e cada nivel a mais gasta caractere do orcamento do Windows.
        """
        destino = Path("C:/destino")
        for c in self.camadas[:200]:
            _, pasta = caminhos_do_pacote(c, destino)
            self.assertEqual(len(pasta.relative_to(destino).parts), 1,
                             f"{c.titulo}: {pasta}")

    def test_inclui_os_projetos_aerogeofisicos(self):
        """A serie 1000/3000 — XYZ e Geotiff — ficou de fora numa versao."""
        xyz = [c for c in self.camadas if c.tipo == "Geofísica-XYZ"]
        tif = [c for c in self.camadas if c.tipo == "Geofísica-Geotiff"]
        self.assertGreater(len(xyz), 100, "faltam os XYZ")
        self.assertGreater(len(tif), 200, "faltam os Geotiff")
        serie = [c for c in self.camadas
                 if any(p.startswith(("10", "30")) and "-" in p
                        for p in c.pastas)]
        self.assertTrue(serie, "nenhum projeto numerado no catalogo")

    def test_hierarquia_preenchida(self):
        sem_pasta = [c for c in self.camadas if not c.pastas]
        self.assertEqual(sem_pasta, [])

    def test_busca_ignora_acento_e_caixa(self):
        for termo in ("geologica", "GEOLÓGICA", "Geológica"):
            self.assertTrue(cat.filtrar(self.camadas, termo),
                            f"nada encontrado para {termo!r}")

    def test_busca_por_folha(self):
        achados = cat.filtrar(self.camadas, "jardim do ouro")
        self.assertTrue(achados)
        self.assertTrue(any("Jardim do Ouro" in c.titulo for c in achados))

    def test_filtro_por_tipo(self):
        so_kml = cat.filtrar(self.camadas, "", ("KML",))
        self.assertTrue(so_kml)
        self.assertEqual({c.tipo for c in so_kml}, {"KML"})

    def test_arvore_preserva_todas_as_camadas(self):
        raiz = cat.montar_arvore(self.camadas)
        self.assertEqual(raiz.contar(), len(self.camadas))

    def test_arvore_tem_as_raizes_do_site(self):
        raiz = cat.montar_arvore(self.camadas)
        nomes = {n.nome for n in raiz.filhos}
        self.assertIn("Cartografia Geológica", nomes)

    def test_tamanho_legivel(self):
        c = self.camadas[0]
        self.assertRegex(c.tamanho_legivel, r"^[\d.,]+ (KB|MB|GB)$|^\d+ B$|^\?$")


class TesteManifesto(unittest.TestCase):
    """
    O metadata.txt, que e o que o Gerenciador de Complementos mostra.

    Ja apareceu com a descricao codificada duas vezes — "ServiAo GeolA3gico" na
    tela — e com uma lista de tags que cobria menos da metade dos formatos que
    o plugin abre.
    """

    @classmethod
    def setUpClass(cls):
        import configparser
        cls.caminho = (Path(__file__).resolve().parent.parent
                       / "acervo_cprm" / "metadata.txt")
        cls.bruto = cls.caminho.read_bytes()
        c = configparser.ConfigParser()
        c.read_string(cls.bruto.decode("utf-8"))
        cls.geral = c["general"]

    def test_e_ascii_puro(self):
        """
        Sem acento nenhum — por escolha, nao por necessidade.

        O QGIS le o manifesto com `encoding="utf8"` explicito, nos dois lugares
        que o leem (pyplugin_installer/installer_data.py e qgis/utils.py), entao
        acento em UTF-8 valido funcionaria. O que nao funcionava era o arquivo
        gravado com os acentos codificados DUAS vezes, e foi isso que apareceu
        como "ServiAo GeolA3gico" no Gerenciador de Complementos.

        ASCII foi a preferencia de quem escreve o texto. O teste existe para o
        arquivo nao voltar a divergir dessa escolha sem ninguem notar — trocar
        e uma decisao, nao um acidente.
        """
        try:
            self.bruto.decode("ascii")
        except UnicodeDecodeError as e:
            trecho = self.bruto[max(0, e.start - 40):e.start + 20]
            self.fail("acento no manifesto, byte %d: ...%s..."
                      % (e.start, trecho.decode("utf-8", "replace")))

    def test_nao_tem_dupla_codificacao(self):
        """A marca do erro antigo: "Ã" ou "Â" seguido de outro byte alto."""
        import re
        texto = self.bruto.decode("utf-8")
        marca = re.compile("[ÃÂ][-¿]")
        self.assertIsNone(marca.search(texto),
                          "acento codificado duas vezes no manifesto")

    def test_a_descricao_e_uma_linha_so(self):
        """O Gerenciador mostra `description` como titulo; quebra vira lixo."""
        self.assertNotIn(chr(10), self.geral["description"])
        self.assertTrue(20 < len(self.geral["description"]) < 260,
                        len(self.geral["description"]))

    def test_as_tags_cobrem_os_formatos_que_o_plugin_abre(self):
        """
        Quem procura o plugin procura pelo formato que tem na mao. A lista
        antiga tinha 10 tags e deixava de fora GeoPackage, GeoJSON, DXF, JP2,
        LAS, XLSX e CSV — tudo coisa que o plugin abre.
        """
        from acervo_cprm import config
        tags = {t.strip().lower() for t in self.geral["tags"].split(",")}
        self.assertTrue(all(tags), "tag vazia na lista")

        extensoes = (config.EXTENSOES_VETORIAIS | config.EXTENSOES_RASTER
                     | config.EXTENSOES_NUVEM | config.EXTENSOES_TABELA
                     | config.EXTENSOES_SO_DOWNLOAD)
        # Formatos que um usuario procuraria pelo nome. Os sidecars e os
        # exoticos (.mif, .bil, .ers) ficam de fora de proposito.
        principais = {".shp": "shapefile", ".kml": "kml", ".gpkg": "geopackage",
                      ".geojson": "geojson", ".dxf": "dxf", ".tif": "geotiff",
                      ".jp2": "jp2", ".las": "las", ".xlsx": "xlsx",
                      ".csv": "csv", ".xyz": "xyz", ".parquet": "parquet"}
        for ext, tag in principais.items():
            self.assertIn(ext, extensoes, "%s saiu do config" % ext)
            self.assertIn(tag, tags, "falta a tag %r para %s" % (tag, ext))

    def test_os_numeros_do_manifesto_batem_com_o_catalogo(self):
        """
        O texto dizia "as 2.657 camadas do acervo GEOSGB", e isso sugeria que o
        acervo tem 2.657. O acervo publica 5.258 arquivos; 2.657 e o que sobra
        depois de tirar o PDF de mapa e de relatorio e os links quebrados.

        O usuario percebeu antes de mim. Aqui o numero fica amarrado ao
        catalogo embutido: se ele mudar e o texto nao, o teste acusa.
        """
        camadas = cat.carregar()
        n = "{:,}".format(len(camadas)).replace(",", ".")
        texto = self.geral["description"] + " " + self.geral["about"]
        self.assertIn(n, texto,
                      "o manifesto nao cita as %s camadas do catalogo" % n)

        gb = sum(c.tamanho_bytes for c in camadas) / 2**30
        self.assertIn("%d GB" % round(gb), texto,
                      "o manifesto nao cita os %d GB do catalogo" % round(gb))

    def test_a_versao_e_reconhecivel(self):
        import re
        self.assertRegex(self.geral["version"], r"^\d+\.\d+\.\d+$")

    def test_os_campos_obrigatorios_estao_la(self):
        for campo in ("name", "qgisMinimumVersion", "description", "version",
                      "author", "email", "repository"):
            self.assertTrue(self.geral.get(campo, "").strip(), campo)


class TesteNomes(unittest.TestCase):
    """As regras que causaram pastas indeletaveis no projeto anterior."""

    def test_nao_come_texto_apos_o_ponto(self):
        self.assertEqual(cat.limpar_nome("Mapa 1:250.000"), "Mapa 1-250.000")

    def test_nunca_termina_em_espaco_ou_ponto(self):
        longo = "Folha Rio Bacajá (PRONAGEO - UFPR) - SA.22-Y-D-VI " + "x" * 60
        for limite in range(10, 90):
            nome = cat.limpar_nome(longo, limite)
            self.assertFalse(nome.endswith((" ", ".")),
                             f"limite {limite} produziu {nome!r}")

    def test_remove_caracteres_invalidos(self):
        self.assertNotIn(":", cat.limpar_nome("a:b"))
        self.assertNotIn("/", cat.limpar_nome("a/b"))

    def test_nomes_reservados(self):
        self.assertTrue(cat.limpar_nome("CON").startswith("_"))

    def test_nunca_devolve_vazio(self):
        for entrada in ("", "   ", "...", "///"):
            self.assertTrue(cat.limpar_nome(entrada))


# ─── pacote ──────────────────────────────────────────────────────────────────

def _zip_de_teste(destino: Path, nomes, utf8=True) -> Path:
    """ZIP sintetico; com utf8=False grava o nome como o SGB faz (sem a flag)."""
    z = destino / "teste.zip"
    with zipfile.ZipFile(z, "w") as arq:
        for nome in nomes:
            if utf8:
                arq.writestr(nome, b"conteudo")
            else:
                info = zipfile.ZipInfo(nome.encode("utf-8").decode("cp437"))
                info.flag_bits &= ~0x800
                arq.writestr(info, b"conteudo")
    return z


class TestePacote(unittest.TestCase):

    @staticmethod
    def _membro(bytes_do_nome: bytes, flag_utf8: bool) -> zipfile.ZipInfo:
        """
        Forja um ZipInfo como o `zipfile` o entregaria ao ler.

        Nao da para produzir esse caso com `writestr`: o Python marca a flag
        UTF-8 sozinho sempre que o nome tem caractere nao-ASCII. Entao montamos
        o ZipInfo direto, que e exatamente o que `nome_corrigido` recebe.
        """
        info = zipfile.ZipInfo()
        info.flag_bits = 0x800 if flag_utf8 else 0
        info.filename = (bytes_do_nome.decode("utf-8") if flag_utf8
                         else bytes_do_nome.decode("cp437"))
        return info

    def test_cp437_de_verdade_fica_como_esta(self):
        """O caso real do acervo: o KML da folha Regência, byte 0xA2 = 'ó'."""
        info = self._membro(b"Carta_Geol\xa2gica_da_Folha_Regencia_(UFES).kml",
                            flag_utf8=False)
        self.assertEqual(pacote.nome_corrigido(info),
                         "Carta_Geológica_da_Folha_Regencia_(UFES).kml")

    def test_utf8_sem_flag_e_reconstruido(self):
        """ZIP feito no Linux: bytes UTF-8, flag ausente, cp437 vira mojibake."""
        info = self._membro("Formação Açu.shp".encode("utf-8"), flag_utf8=False)
        self.assertNotEqual(info.filename, "Formação Açu.shp")
        self.assertEqual(pacote.nome_corrigido(info), "Formação Açu.shp")

    def test_mantem_nome_quando_a_flag_utf8_esta_marcada(self):
        info = self._membro("acentuação.kml".encode("utf-8"), flag_utf8=True)
        self.assertEqual(pacote.nome_corrigido(info), "acentuação.kml")

    def test_nome_ascii_nao_e_tocado(self):
        info = self._membro(b"jdouro_litologia.shp", flag_utf8=False)
        self.assertEqual(pacote.nome_corrigido(info), "jdouro_litologia.shp")

    def test_extrai_preservando_subpastas(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            z = _zip_de_teste(tmp, ["Pacote/Estrutura/a.shp", "Pacote/b.kml"])
            saida = pacote.extrair(z, tmp / "saida")
            self.assertTrue((saida / "Pacote" / "Estrutura" / "a.shp").exists())
            self.assertTrue((saida / "Pacote" / "b.kml").exists())

    def test_recusa_caminho_para_fora(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            z = tmp / "mau.zip"
            with zipfile.ZipFile(z, "w") as arq:
                arq.writestr("../../fora.txt", b"x")
                arq.writestr("bom.txt", b"x")
            saida = pacote.extrair(z, tmp / "saida")
            self.assertTrue((saida / "bom.txt").exists())
            self.assertFalse((tmp.parent / "fora.txt").exists())

    def test_listar_ignora_arquivos_auxiliares(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for nome in ("a.shp", "a.dbf", "a.shx", "a.prj", "a.cpg",
                         "estilo.lyr", "leia-me.txt", "b.kml"):
                (tmp / nome).write_bytes(b"x")
            achados = {p.name for p, _ in pacote.listar_arquivos(tmp)}
            self.assertEqual(achados, {"a.shp", "b.kml"})

    def test_listar_acha_raster_da_geofisica(self):
        """
        Estrutura real de "Base (Vetores, Kmz, Geotif...)": os GeoTIFF sao o
        conteudo principal, e vinham sendo descartados em silencio.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "GEOTIFF").mkdir()
            (tmp / "SHAPEFILE").mkdir()
            (tmp / "LEGENDAS").mkdir()
            for nome in ("GEOTIFF/CMA_SIRGAS.tif",
                         "GEOTIFF/CMA_SIRGAS.tif.gi",      # indice Geosoft
                         "GEOTIFF/CMA_SIRGAS.tif.xml",     # metadado
                         "GEOTIFF/eTh_SIRGAS.tif",
                         "SHAPEFILE/EULER.shp",
                         "SHAPEFILE/EULER.qmd",            # metadado do QGIS
                         "LEGENDAS/CMA_LEGENDA.jpg",       # escala de cores
                         "LEIA-ME.pdf"):
                (tmp / nome).write_bytes(b"x")
            achados = {p.name: especie
                       for p, especie in pacote.listar_arquivos(tmp)}
            # O LEIA-ME.pdf entra como "arquivo", nao como camada: desde que
            # a carta em PDF passou a ser oferecida, todo .pdf e pesado pelo
            # GDAL. Este aqui e um "x" de um byte, entao nao tem
            # georreferencia — e um PDF de verdade sem georreferencia cairia
            # no mesmo lugar. Aparece listado e desabilitado, que e a regra da
            # casa: o arquivo nao some em silencio.
            self.assertEqual(
                achados,
                {"CMA_SIRGAS.tif": "raster", "eTh_SIRGAS.tif": "raster",
                 "EULER.shp": "vetor", "LEIA-ME.pdf": "arquivo"})

    def test_xyz_entra_como_somente_download(self):
        """
        O QGIS nao abre o XYZ do Geosoft (blocos "LI n", sem cabecalho
        delimitado). Ele nao pode sumir da lista: o usuario baixa para abrir
        no Oasis Montaj ou converter.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "1014_em.xyz").write_bytes(b"LI 1\n -5.4E+06 -1.3E+06\n")
            (tmp / "1014.doc").write_bytes(b"x")
            achados = pacote.listar_arquivos(tmp)
            self.assertEqual(len(achados), 1, "o .doc nao devia entrar")
            caminho, especie = achados[0]
            self.assertEqual(caminho.name, "1014_em.xyz")
            self.assertEqual(especie, "arquivo")

    def test_item_somente_download_nao_e_camada(self):
        item = pacote.CamadaEncontrada(Path("C:/x/1014_em.xyz"), Path("C:/x"),
                                       "arquivo")
        self.assertFalse(item.eh_camada)
        self.assertTrue(item.valida)          # nao e erro, e outra natureza
        self.assertEqual(item.descricao, "somente download")

    def test_planilha_entra_como_tabela(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for nome in ("geoquimica.xlsx", "antiga.xls", "dados.csv",
                         "leia-me.pdf"):
                (tmp / nome).write_bytes(b"x")
            achados = {p.name: esp for p, esp in pacote.listar_arquivos(tmp)}
            self.assertEqual(achados, {"geoquimica.xlsx": "tabela",
                                       "antiga.xls": "tabela",
                                       "dados.csv": "tabela",
                                       "leia-me.pdf": "arquivo"})

    def test_acha_colunas_de_coordenada(self):
        achar = pacote._achar_coordenadas
        self.assertEqual(achar(["PROJETO", "LATITUDE", "LONGITUDE", "Au_ppb"]),
                         ("LATITUDE", "LONGITUDE"))
        self.assertEqual(achar(["lat", "long", "Cu"]), ("lat", "long"))
        self.assertIsNone(achar(["AMOSTRA", "Au_ppb", "Cu_ppm"]))
        self.assertIsNone(achar(["LATITUDE"]))      # so metade nao serve

    def test_descricao_da_tabela_mostra_as_coordenadas(self):
        item = pacote.CamadaEncontrada(Path("C:/x/geoq.xlsx"), Path("C:/x"),
                                       "tabela")
        self.assertEqual(item.descricao, "Tabela")
        item.coordenadas = ("LATITUDE", "LONGITUDE")
        self.assertIn("LATITUDE", item.descricao)

    def test_sidecar_aux_xml_nao_vira_camada(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "GEOLOGIA.tif").write_bytes(b"x")
            (tmp / "GEOLOGIA.tif.aux.xml").write_bytes(b"x")
            achados = pacote.listar_arquivos(tmp)
            self.assertEqual(len(achados), 1)
            self.assertEqual(achados[0][0].name, "GEOLOGIA.tif")

    def test_codificacao_respeita_o_cpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "x.shp").write_bytes(b"x")
            (tmp / "x.CPG").write_text("UTF-8")     # caixa mista, como no acervo
            self.assertEqual(pacote._codificacao(tmp / "x.shp"), "UTF-8")

    def test_codificacao_sem_cpg_assume_latin1(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "x.shp").write_bytes(b"x")
            self.assertEqual(pacote._codificacao(tmp / "x.shp"), "ISO-8859-1")

    def test_caminho_longo_no_windows(self):
        p = pacote.caminho_longo("C:/tmp/x")
        if sys.platform == "win32":
            self.assertTrue(p.startswith("\\\\?\\"))


class TesteEspacializar(unittest.TestCase):
    """
    129 pacotes de geoquimica baixam como planilha solta, sem o shapefile que o
    SGB costuma anexar. Para esses, a coordenada so existe nas colunas.
    """

    @staticmethod
    def _pasta():
        """
        Pasta temporaria tolerante na limpeza.

        Os testes que conferem o resultado abrem o GeoPackage como
        QgsVectorLayer, e camada carregada segura o arquivo — isso e normal em
        qualquer SIG. Quem cobra a liberacao e `test_nao_trava_a_planilha`, que
        usa pasta estrita de proposito.
        """
        return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    @staticmethod
    def _planilha(tmp: Path, linhas) -> Path:
        """Grava um CSV — o OGR o le igual a um xlsx, e nao exige biblioteca."""
        alvo = tmp / "geoquimica.csv"
        with open(alvo, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["AMOSTRA", "LATITUDE", "LONGITUDE", "Au_ppb"])
            w.writerows(linhas)
        return alvo

    def test_converte_tabela_em_pontos(self):
        from qgis.core import QgsVectorLayer
        with self._pasta() as tmp:
            tmp = Path(tmp)
            self._planilha(tmp, [["A-1", -4.348736, -56.176478, 12],
                                 ["A-2", -4.345070, -56.187404, 40]])
            item = pacote.inspecionar(tmp)[0]
            self.assertEqual(item.especie, "tabela")
            self.assertEqual(item.coordenadas, ("LATITUDE", "LONGITUDE"))

            caminho, gravadas, puladas = pacote.criar_pontos(item)
            self.assertEqual((gravadas, puladas), (2, 0))

            camada = QgsVectorLayer(str(caminho), "p", "ogr")
            self.assertTrue(camada.isValid())
            self.assertEqual(camada.featureCount(), 2)
            self.assertEqual(camada.crs().authid(), "EPSG:4674")
            # longitude no X, latitude no Y — trocar poe o ponto na China
            ponto = next(camada.getFeatures()).geometry().asPoint()
            self.assertAlmostEqual(ponto.x(), -56.176478, places=5)
            self.assertAlmostEqual(ponto.y(), -4.348736, places=5)

    def test_preserva_os_atributos(self):
        from qgis.core import QgsVectorLayer
        with self._pasta() as tmp:
            tmp = Path(tmp)
            self._planilha(tmp, [["A-1", -4.3, -56.1, 12]])
            item = pacote.inspecionar(tmp)[0]
            caminho, _, _ = pacote.criar_pontos(item)
            camada = QgsVectorLayer(str(caminho), "p", "ogr")
            f = next(camada.getFeatures())
            self.assertEqual(f["AMOSTRA"], "A-1")
            self.assertIn("Au_ppb", [c.name() for c in camada.fields()])

    def test_pula_linhas_sem_coordenada_utilizavel(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._planilha(tmp, [
                ["boa", -4.3, -56.1, 1],
                ["vazia", "", "", 2],
                ["texto", "n/d", "n/d", 3],
                ["zero", 0, 0, 4],          # cai no Golfo da Guiné
                ["fora", -999, -56.1, 5],   # latitude impossível
            ])
            item = pacote.inspecionar(tmp)[0]
            caminho, gravadas, puladas = pacote.criar_pontos(item)
            self.assertEqual(gravadas, 1)
            self.assertEqual(puladas, 4)

    def test_recusa_quando_nenhuma_linha_serve(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._planilha(tmp, [["x", "", "", 1], ["y", 0, 0, 2]])
            item = pacote.inspecionar(tmp)[0]
            with self.assertRaises(ValueError):
                pacote.criar_pontos(item)
            # e nao deixa um GeoPackage vazio para tras
            self.assertFalse(list(tmp.glob("*_pontos.gpkg")))

    def test_recusa_tabela_sem_colunas_de_coordenada(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            alvo = tmp / "sem_coord.csv"
            with open(alvo, "w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerows([["AMOSTRA", "Au_ppb"], ["A-1", 12]])
            item = pacote.inspecionar(tmp)[0]
            self.assertIsNone(item.coordenadas)
            with self.assertRaises(ValueError):
                pacote.criar_pontos(item)

    def test_nao_trava_a_planilha(self):
        """
        O provedor OGR do QGIS mantinha a planilha aberta depois da conversão,
        e o Windows recusava apagar a pasta. Por isso a leitura usa GDAL direto.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            origem = self._planilha(tmp, [["A-1", -4.3, -56.1, 12]])
            item = pacote.inspecionar(tmp)[0]
            pacote.criar_pontos(item)
            os.remove(origem)          # levanta PermissionError se travada
            self.assertFalse(origem.exists())

    def test_respeita_o_crs_escolhido(self):
        from qgis.core import QgsVectorLayer
        with self._pasta() as tmp:
            tmp = Path(tmp)
            self._planilha(tmp, [["A-1", -4.3, -56.1, 12]])
            item = pacote.inspecionar(tmp)[0]
            caminho, _, _ = pacote.criar_pontos(item, "EPSG:4618")  # SAD-69
            camada = QgsVectorLayer(str(caminho), "p", "ogr")
            self.assertEqual(camada.crs().authid(), "EPSG:4618")


class TesteNaoExtrairDocumento(unittest.TestCase):
    """
    Um .xlsx E um zip. `is_zipfile()` diz sim, e extrair a planilha espalhava
    [Content_Types].xml, _rels/, docProps/ e xl/ na pasta — e depois apagava o
    .xlsx, tratado como "zip ja extraido". Aconteceu de verdade com o pacote
    ARIM Serido da Folha Augusto Severo.
    """

    class _CamadaFalsa:
        def __init__(self, nome):
            self.id = "999"
            self.titulo = "teste"
            self.nome_arquivo = nome
            self.tamanho_bytes = 0
            self.pastas = ("A",)

    def _tarefa(self, tmp, nome, conteudo):
        from acervo_cprm.baixador import TarefaBaixar
        t = TarefaBaixar(self._CamadaFalsa(nome), tmp)
        t.arquivo.parent.mkdir(parents=True, exist_ok=True)
        t.arquivo.write_bytes(conteudo)
        return t

    @staticmethod
    def _ooxml():
        """Um .xlsx minimo: zip com a cara de OOXML."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("_rels/.rels", "<Relationships/>")
            z.writestr("xl/workbook.xml", "<workbook/>")
        return buf.getvalue()

    def test_xlsx_nao_e_extraido(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = self._tarefa(Path(tmp), "geoquimica.xlsx", self._ooxml())
            self.assertTrue(zipfile.is_zipfile(t.arquivo),
                            "o teste precisa de um xlsx que seja zip")
            self.assertFalse(t._e_pacote_a_extrair(),
                             "ia explodir o OOXML na pasta")

    def test_kmz_e_docx_tambem_nao(self):
        with tempfile.TemporaryDirectory() as tmp:
            for nome in ("mapa.kmz", "nota.docx", "planilha.ods"):
                t = self._tarefa(Path(tmp), nome, self._ooxml())
                self.assertFalse(t._e_pacote_a_extrair(), nome)

    def test_xlsx_rotulado_como_xls(self):
        """
        O caso real que escapou da lista de negação: o SGB publica
        ARIM_Serido_Folha_Augusto_Severo_GEOQUIMICA_Xlsx.xls — conteúdo XLSX,
        nome .xls. Só a lista de permissão resolve.
        """
        with tempfile.TemporaryDirectory() as tmp:
            t = self._tarefa(Path(tmp), "planilha_que_e_xlsx.xls", self._ooxml())
            self.assertTrue(zipfile.is_zipfile(t.arquivo))
            self.assertFalse(t._e_pacote_a_extrair())

    def test_extensao_vazia_decide_pelo_conteudo(self):
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("a.shp", b"x")
            t = self._tarefa(Path(tmp), "sem_extensao", buf.getvalue())
            self.assertTrue(t._e_pacote_a_extrair())

    def test_zip_de_verdade_continua_sendo_extraido(self):
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("dados/mapa.shp", b"x")
            t = self._tarefa(Path(tmp), "pacote.zip", buf.getvalue())
            self.assertTrue(t._e_pacote_a_extrair())

    def test_las_nao_e_zip_e_nao_e_extraido(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = self._tarefa(Path(tmp), "nuvem.las", b"LASF" + bytes(100))
            self.assertFalse(t._e_pacote_a_extrair())


class TesteAbasDaPlanilha(unittest.TestCase):
    """
    As tabelas de geoquimica do SGB separam o dado por meio amostral. A do ARIM
    Serido tem "Contagem" (1 linha, so resumo), "Mineralometria" (169) e
    "Sedimento de corrente" (197). Ler so a primeira aba entregava a linha de
    resumo e escondia as 366 amostras.
    """

    @staticmethod
    def _planilha_com_abas(tmp: Path) -> Path:
        """
        Planilha de duas abas, escrita com openpyxl.

        Escrever com o proprio driver XLSX do GDAL nao serve de fixture: o
        arquivo que ele produz nao faz round-trip do cabecalho a partir da
        segunda aba, e o teste passaria a medir esse defeito em vez do plugin.
        Os arquivos reais do SGB leem certo — conferido no ARIM Serido.
        """
        import openpyxl
        alvo = tmp / "geoq.xlsx"
        livro = openpyxl.Workbook()
        livro.remove(livro.active)
        for aba, linhas in (("Contagem", 1), ("Sedimento", 3)):
            folha = livro.create_sheet(aba)
            folha.append(["AMOSTRA", "LATITUDE", "LONGITUDE"])
            for n in range(linhas):
                folha.append([f"A-{n}", -5.5 - n / 100, -37.2 - n / 100])
        livro.save(alvo)
        return alvo

    def test_cada_aba_vira_uma_camada(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._planilha_com_abas(tmp)
            itens = pacote.inspecionar(tmp)
            self.assertEqual(len(itens), 2, "faltou aba")
            abas = {i.aba: i.feicoes for i in itens}
            self.assertEqual(abas, {"Contagem": 1, "Sedimento": 3})

    def test_nome_identifica_a_aba(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._planilha_com_abas(tmp)
            nomes = [i.nome for i in pacote.inspecionar(tmp)]
            self.assertTrue(any("Sedimento" in n for n in nomes), nomes)

    def test_espacializa_a_aba_certa(self):
        from qgis.core import QgsVectorLayer
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            self._planilha_com_abas(tmp)
            alvo = max(pacote.inspecionar(tmp), key=lambda i: i.feicoes)
            caminho, gravadas, _ = pacote.criar_pontos(alvo)
            self.assertEqual(gravadas, 3, "espacializou a aba errada")
            self.assertIn("Sedimento", caminho.name)
            camada = QgsVectorLayer(str(caminho), "p", "ogr")
            self.assertEqual(camada.featureCount(), 3)

    def test_gpkg_gerado_nao_vira_camada_extra(self):
        """
        O GeoPackage da espacializacao fica ao lado da planilha. Listar de novo
        mostraria a mesma amostragem duas vezes: a aba e os pontos dela.
        """
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            self._planilha_com_abas(tmp)
            antes = len(pacote.inspecionar(tmp))

            alvo = max(pacote.inspecionar(tmp), key=lambda i: i.feicoes)
            caminho, _, _ = pacote.criar_pontos(alvo)
            self.assertTrue(caminho.exists(), "o gpkg tinha que existir")

            depois = pacote.inspecionar(tmp)
            self.assertEqual(len(depois), antes,
                             "o gpkg derivado entrou como camada extra")
            self.assertTrue(all(i.especie == "tabela" for i in depois))

    def test_planilha_de_uma_aba_so_nao_ganha_sufixo(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            alvo = tmp / "simples.csv"
            with open(alvo, "w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerows([["A", "LATITUDE", "LONGITUDE"],
                                         ["x", -5.5, -37.2]])
            item = pacote.inspecionar(tmp)[0]
            self.assertIsNone(item.aba)
            self.assertEqual(item.nome, "simples")


class TesteCaminhoLongo(unittest.TestCase):
    """
    O Windows corta em 260 caracteres, e `rglob` sem o prefixo devolve
    lista VAZIA — sem erro, sem aviso. Foi o que aconteceu com o pacote
    "ARIM - Faixas Marginais", cujos arquivos chegam a 350 caracteres,
    enquanto o de Juazeirinho, com 245, funcionava.
    """

    def _pasta_funda(self, base: Path, alvo_chars: int = 300) -> Path:
        """Cria uma pasta cujo caminho passa do limite do Windows."""
        pasta = base
        while len(str(pasta)) < alvo_chars - 60:
            pasta = pasta / ("nivel_" + "x" * 40)
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def test_varredura_acha_arquivo_em_caminho_longo(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            funda = self._pasta_funda(raiz)
            alvo = funda / ("amostras_" + "y" * 30 + ".shp")
            with open(pacote.caminho_longo(alvo), "wb") as f:
                f.write(b"x")
            self.assertGreater(len(str(alvo)), 260,
                               "o teste precisa de um caminho longo de verdade")

            achados = pacote.listar_arquivos(raiz)
            self.assertEqual(len(achados), 1,
                             "a varredura perdeu o arquivo longo")
            self.assertEqual(achados[0][0].name, alvo.name)

    def test_caminho_devolvido_nao_carrega_o_prefixo(self):
        """O prefixo e detalhe interno; nao pode vazar para o projeto."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "a.shp").write_bytes(b"x")
            caminho, _ = pacote.listar_arquivos(raiz)[0]
            self.assertFalse(str(caminho).startswith(pacote.PREFIXO_LONGO))

    def test_prefixo_so_entra_quando_o_caminho_e_longo(self):
        curto = Path("C:/dados/mapa.shp")
        self.assertEqual(pacote.caminho_para_abrir(curto), str(curto))

        longo = Path("C:/" + "d" * 250 + "/mapa.shp")
        pronto = pacote.caminho_para_abrir(longo)
        if sys.platform == "win32":
            self.assertTrue(pronto.startswith(pacote.PREFIXO_LONGO), pronto)

    def test_a_constante_do_prefixo_esta_certa(self):
        """
        Quatro caracteres: barra, barra, interrogacao, barra. Escrevi com o
        numero errado de escapes uma vez e a varredura parou de achar
        qualquer arquivo — sem erro, sem aviso.
        """
        self.assertEqual(len(pacote.PREFIXO_LONGO), 4)
        self.assertEqual(list(pacote.PREFIXO_LONGO), ["\\", "\\", "?", "\\"])

    def test_ninguem_cria_pasta_sem_o_prefixo(self):
        """
        Toda criacao de pasta passa por `pacote.criar_pasta`.

        Este teste le o CODIGO, nao o comportamento, e e de proposito: a falha
        so acontece no `qgis-bin.exe`, que nao entende caminho acima de 260
        caracteres. O `python-qgis.bat`, onde estes testes rodam, entende — e
        foi assim que o bug do `rglob` passou despercebido antes.

        Havia um `mkdir` cru ao lado de um `open` COM prefixo, na mesma funcao:
        o arquivo seria gravado e a pasta que o abriga, nao.
        """
        raiz = Path(__file__).resolve().parent.parent / "acervo_cprm"
        culpados = []
        for arquivo in sorted(raiz.glob("*.py")):
            if arquivo.name == "config.py":
                # A unica excecao: a pasta do catalogo atualizado fica no
                # AppData do usuario, sempre curto, e config nao pode importar
                # pacote — pacote e quem importa config.
                continue
            for n, linha in enumerate(
                    arquivo.read_text(encoding="utf-8").splitlines(), 1):
                if ".mkdir(" in linha or "os.makedirs(" in linha:
                    if "caminho_longo" not in linha:
                        culpados.append("%s:%d %s" % (arquivo.name, n,
                                                      linha.strip()))
        self.assertEqual(culpados, [],
                         "criacao de pasta sem o prefixo de caminho longo")

    def test_sem_prefixo_e_idempotente(self):
        p = Path("C:/dados/x.shp")
        self.assertEqual(pacote.sem_prefixo(p), p)
        self.assertEqual(pacote.sem_prefixo(pacote.caminho_longo(p)), p)


class TesteCoordenada(unittest.TestCase):
    """`coordenada_valida` e pura: roda sem QGIS."""

    def test_aceita_numero_e_texto(self):
        self.assertEqual(pacote.coordenada_valida(-4.3, -56.1), (-56.1, -4.3))
        self.assertEqual(pacote.coordenada_valida("-4.3", "-56.1"),
                         (-56.1, -4.3))
        self.assertEqual(pacote.coordenada_valida("-4,3", "-56,1"),
                         (-56.1, -4.3))     # virgula decimal

    def test_devolve_x_y_nao_lat_lon(self):
        """Trocar a ordem poe a amostra do Pará na China."""
        x, y = pacote.coordenada_valida(-4.3, -56.1)
        self.assertEqual((x, y), (-56.1, -4.3))

    def test_recusa_o_que_nao_serve(self):
        for lat, lon in ((None, None), ("", ""), ("n/d", "n/d"),
                         (0, 0), (-999, -56.1), (-4.3, 999)):
            self.assertIsNone(pacote.coordenada_valida(lat, lon),
                              f"aceitou {lat!r}/{lon!r}")


class TesteQgisDisponivel(unittest.TestCase):
    """Garante que estamos mesmo rodando dentro do QGIS."""

    def test_importa_qgis(self):
        from qgis.core import Qgis, QgsVectorLayer      # noqa: F401
        self.assertTrue(Qgis.QGIS_VERSION)

    def test_inspecionar_abre_um_geojson_real(self):
        from qgis.core import QgsVectorLayer            # noqa: F401
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "pontos.geojson").write_text(
                '{"type":"FeatureCollection","features":['
                '{"type":"Feature","properties":{"n":"Formação Açu"},'
                '"geometry":{"type":"Point","coordinates":[-43.9,-19.9]}}]}',
                encoding="utf-8")
            itens = pacote.inspecionar(tmp)
            self.assertEqual(len(itens), 1)
            self.assertTrue(itens[0].valida, itens[0].erro)
            self.assertEqual(itens[0].feicoes, 1)
            self.assertEqual(itens[0].geometria, "Point")


# ─── ponta a ponta, com rede ─────────────────────────────────────────────────

@unittest.skipUnless(COM_REDE, "rede desabilitada")
class TestePontaAPonta(unittest.TestCase):
    """
    Baixa o menor SIG real do acervo (60 KB) e vai ate as camadas.

    Usa urllib por simplicidade: o QgsNetworkAccessManager precisa de um laco
    de eventos Qt, que so existe com a aplicacao de fato rodando. O caminho de
    rede do plugin e exercitado no QGIS aberto, nao aqui.
    """

    def test_baixa_extrai_e_inspeciona(self):
        import urllib.request

        camadas = cat.carregar()
        menor = min((c for c in camadas if c.tipo == "SIG (Vetores)"
                     and c.tamanho_bytes > 0),
                    key=lambda c: c.tamanho_bytes)
        print(f"\n  menor SIG: {menor.titulo[:50]} "
              f"({menor.tamanho_legivel})", flush=True)

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            alvo = tmp / "pacote.zip"
            req = urllib.request.Request(
                menor.link, headers={"User-Agent": "QGIS Acervo CPRM"})
            with urllib.request.urlopen(req, timeout=120) as r:
                dados = r.read()
            alvo.write_bytes(dados)

            self.assertEqual(len(dados), menor.tamanho_bytes,
                             "tamanho diferente do catalogo")
            self.assertTrue(zipfile.is_zipfile(alvo), "nao veio um zip")

            saida = pacote.extrair(alvo, tmp / "extraido")
            itens = pacote.inspecionar(saida)
            print(f"  {len(itens)} camadas no pacote", flush=True)
            self.assertTrue(itens)
            validas = [i for i in itens if i.valida]
            self.assertTrue(validas, "nenhuma camada abriu")
            for i in validas[:4]:
                print(f"    {i.nome:<38} {i.geometria:<10} "
                      f"{i.feicoes:>6} feições  {i.crs}", flush=True)


if __name__ == "__main__":
    from qgis.core import QgsApplication
    app = QgsApplication([], False)
    app.initQgis()
    try:
        argv = [a for a in sys.argv if a != "--sem-rede"]
        unittest.main(argv=argv, exit=False, verbosity=2)
    finally:
        app.exitQgis()
