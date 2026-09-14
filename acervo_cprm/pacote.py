# -*- coding: utf-8 -*-
"""
pacote.py — Descompactacao dos pacotes SIG e inspecao do que veio dentro.

Um "SIG (Vetores)" do GEOSGB nao e uma camada: e um ZIP com 7 a 16 shapefiles
em subpastas tematicas (Afloramento, Estrutura, Litologia...), mais .prj, .xml
e arquivos .lyr de estilo do ArcGIS. Os KML sao o caso simples: um .kml so.

Este modulo nao importa Qt. A parte que abre camadas usa qgis.core, isolada em
`inspecionar` e `caminho_de_camada`, para o resto rodar em teste puro.
"""

import os
import sys
import zipfile
from pathlib import Path

from .config import (EXTENSOES_VETORIAIS, EXTENSOES_RASTER, EXTENSOES_NUVEM,
                     EXTENSOES_TABELA, EXTENSOES_SO_DOWNLOAD,
                     COLUNAS_LATITUDE, COLUNAS_LONGITUDE,
                     SUFIXO_PONTOS)


# ─── Caminhos longos no Windows ──────────────────────────────────────────────

#: O prefixo de caminho estendido do Windows: quatro caracteres, \\?\ — a
#: contagem de barras e facil de errar, e errar aqui quebra a varredura
#: inteira em silencio. Ha teste cobrando.
PREFIXO_LONGO = "\\\\?\\"

#: A partir daqui o caminho precisa do prefixo. O limite e 260, mas shapefile
#: arrasta .dbf/.shx/.prj com o mesmo nome, entao ficamos com folga.
LIMITE_SEGURO = 240


def sem_prefixo(p) -> Path:
    r"""
    Devolve o caminho sem o prefixo, para guardar e exibir.

    O prefixo e detalhe de implementacao: gravado no projeto do QGIS deixaria
    o .qgz preso a esta maquina.
    """
    texto = str(p)
    if texto.startswith(PREFIXO_LONGO):
        texto = texto[len(PREFIXO_LONGO):]
    return Path(texto)


def caminho_para_abrir(p) -> str:
    r"""
    Caminho pronto para o GDAL, com o prefixo so quando faz falta.

    O GDAL aceita o prefixo — conferido no QGIS 4 com um shapefile de 285
    caracteres —, mas usa-lo em todo arquivo poluiria o projeto sem ganho.
    """
    texto = str(sem_prefixo(p))
    if sys.platform == "win32" and len(texto) >= LIMITE_SEGURO:
        return caminho_longo(texto)
    return texto


def caminho_longo(p) -> str:
    """
    Prefixo \\?\\ para escapar do limite de 260 caracteres.

    Faz falta aqui: a pasta de destino do usuario, mais a hierarquia do site
    (ate 4 niveis), mais a subpasta do ZIP, mais o nome do shapefile passam de
    260 com facilidade.
    """
    p = os.path.abspath(str(p))
    if sys.platform == "win32" and not p.startswith("\\\\?\\"):
        return "\\\\?\\" + p
    return p


# ─── Nomes dentro do ZIP ─────────────────────────────────────────────────────

def nome_corrigido(info: zipfile.ZipInfo) -> str:
    """
    Devolve o nome do membro com os acentos certos.

    Quando o ZIP nao marca a flag de UTF-8 (bit 0x800), o `zipfile` decodifica
    o nome como cp437 — e os pacotes do SGB nao marcam. Ha dois casos, e
    confundi-los corrompe nome que estava bom:

    - **cp437 de verdade.** O KML da folha Regencia guarda o byte 0xA2, que em
      cp437 e "o" com acento agudo. O `zipfile` ja acerta sozinho; nao ha o que
      fazer. Como 0xA2 solto nao e UTF-8 valido, a tentativa abaixo falha e o
      nome original prevalece.
    - **UTF-8 sem a flag**, comum em ZIP feito no Linux. Ai o cp437 produz
      mojibake ("Geol├│gica") e reconstruir os bytes resolve.

    Por isso so trocamos quando o UTF-8 decodifica: sucesso e evidencia forte
    de que os bytes eram UTF-8, ja que sequencia multibyte valida nao acontece
    por acaso. Qualquer outro palpite (cp1252, latin-1) sempre "funciona" e
    transformaria o primeiro caso em lixo.
    """
    nome = info.filename
    if info.flag_bits & 0x800 or nome.isascii():
        return nome
    try:
        bruto = nome.encode("cp437")
    except UnicodeEncodeError:
        return nome
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return nome


def _seguro(destino: Path, relativo: str) -> Path:
    """
    Impede que um membro do ZIP escreva fora da pasta de destino.

    Um ZIP malformado ou malicioso pode trazer "..\\..\\Windows\\System32\\x".
    Nunca vi isso no acervo do SGB, mas extrair arquivo baixado sem checar e
    exatamente como se cai nesse tipo de coisa.
    """
    limpo = relativo.replace("\\", "/")
    partes = [p for p in limpo.split("/")
              if p not in ("", ".", "..") and not p.endswith(":")]
    if not partes:
        return None
    alvo = destino.joinpath(*partes)
    try:
        alvo.resolve().relative_to(Path(destino).resolve())
    except ValueError:
        return None
    return alvo


def pasta_tem_conteudo(pasta) -> bool:
    """
    A pasta existe e tem alguma coisa dentro?

    E como o plugin responde "ja baixei isto?". Fonte unica: havia QUATRO
    copias desta mesma linha — na ficha do painel, no dialogo de download, na
    tarefa de baixar e numa funcao do baixador que ninguem chamava. Todas
    iguais hoje, e nenhuma garantia de que continuariam iguais amanha; a que
    esquecesse o prefixo de caminho longo responderia "nao baixei" para um
    pacote que esta em disco, e o usuario rebaixaria 1,6 GB.
    """
    try:
        p = Path(caminho_longo(pasta))
        return p.is_dir() and any(p.iterdir())
    except OSError:
        return False


def criar_pasta(caminho: Path):
    """
    mkdir -p, SEMPRE com o prefixo de caminho longo.

    Existe para nao haver mais de um jeito de criar pasta no plugin. O
    `Path.mkdir` cru falha acima de 260 caracteres no `qgis-bin.exe`, que e
    o que roda na maquina do usuario — e nao falha no `python-qgis.bat`,
    que e onde os testes rodam. Tudo que escreve em disco passa por aqui.
    """
    os.makedirs(caminho_longo(caminho), exist_ok=True)


def extrair(zip_path: Path, destino: Path, progresso=None) -> Path:
    """
    Extrai o pacote em `destino`, corrigindo os nomes. Devolve `destino`.

    `progresso` recebe (feitos, total) para alimentar a barra do QGIS.

    Toda escrita passa pelo prefixo de caminho longo, inclusive a criacao das
    pastas. Havia aqui um `mkdir` sem prefixo ao lado de um `open` COM prefixo:
    o arquivo seria gravado e a pasta que o abriga, nao. Nunca vi falhar em
    teste, e nao e prova de nada — `python-qgis.bat` entende caminho longo e o
    `qgis-bin.exe`, que e quem roda na maquina do usuario, nao entende. Foi
    assim que o bug do `rglob` passou despercebido antes.
    """
    destino = Path(destino)
    criar_pasta(destino)

    with zipfile.ZipFile(caminho_longo(zip_path)) as z:
        membros = [i for i in z.infolist() if not i.is_dir()]
        for n, info in enumerate(membros, 1):
            alvo = _seguro(destino, nome_corrigido(info))
            if alvo is None:
                continue
            criar_pasta(alvo.parent)
            with z.open(info) as origem, open(caminho_longo(alvo), "wb") as saida:
                while True:
                    bloco = origem.read(1 << 20)
                    if not bloco:
                        break
                    saida.write(bloco)
            if progresso:
                progresso(n, len(membros))
    return destino


# ─── Inspecao ────────────────────────────────────────────────────────────────

class CamadaEncontrada:
    """Uma camada achada dentro do pacote extraido — vetorial ou raster."""

    __slots__ = ("caminho", "nome", "subpasta", "especie", "geometria",
                 "feicoes", "dimensoes", "bandas", "crs", "codificacao",
                 "coordenadas", "aba", "erro")

    def __init__(self, caminho: Path, raiz: Path, especie: str = "vetor"):
        self.caminho = Path(caminho)
        self.nome = self.caminho.stem
        rel = self.caminho.parent.relative_to(raiz)
        self.subpasta = str(rel) if str(rel) != "." else ""
        self.especie = especie          # "vetor" ou "raster"
        self.geometria = ""
        self.feicoes = None
        self.dimensoes = ""
        self.bandas = None
        self.crs = ""
        self.codificacao = ""
        self.coordenadas = None      # (campo_lat, campo_lon), se a tabela tiver
        self.aba = None              # nome da aba, em planilha com varias
        self.erro = ""

    @property
    def valida(self) -> bool:
        return not self.erro

    @property
    def eh_camada(self) -> bool:
        """False para o que so pode ser baixado, nunca aberto no QGIS."""
        return self.especie != "arquivo"

    @property
    def descricao(self) -> str:
        """O que mostrar na coluna de tipo do dialogo."""
        if self.especie == "arquivo":
            return "somente download"
        if self.erro:
            return self.erro
        if self.especie == "raster":
            return f"Raster, {self.bandas} banda{'s' if self.bandas != 1 else ''}"
        if self.especie == "tabela":
            base = "Tabela"
            if self.coordenadas:
                base += f" ({self.coordenadas[0]}/{self.coordenadas[1]})"
            return base
        if self.especie == "nuvem":
            return "Nuvem de pontos"
        return self.geometria or "—"

    @property
    def tamanho_descrito(self) -> str:
        """Feicoes para vetor e nuvem, pixels para raster, bytes para o resto."""
        if self.especie in ("raster", "arquivo"):
            return self.dimensoes or "—"
        if self.feicoes is None:
            return "—"
        return f"{self.feicoes:,}".replace(",", ".")

    def __repr__(self):
        return (f"<CamadaEncontrada {self.especie} {self.nome!r} "
                f"{self.descricao}>")


def _tamanho_legivel(p: Path) -> str:
    try:
        n = os.path.getsize(caminho_longo(p))
    except OSError:
        return "—"
    for unidade, limite in (("GB", 2**30), ("MB", 2**20), ("KB", 2**10)):
        if n >= limite:
            return f"{n/limite:,.1f} {unidade}".replace(",", ".")
    return f"{n} B"


def _codificacao(shp: Path) -> str:
    """
    Codificacao da tabela de atributos.

    Se ha .cpg, ele manda. Sem .cpg, o QGIS assumiria UTF-8 — e os .dbf do SGB
    costumam ser latin-1, entao "Formação" viraria "Forma\\xc3\\xa7\\xc3\\xa3o".
    A busca e case-insensitive porque vi .CPG e .cpg no mesmo pacote.
    """
    for vizinho in Path(caminho_longo(shp.parent)).iterdir():
        if vizinho.stem.lower() == shp.stem.lower() \
                and vizinho.suffix.lower() == ".cpg":
            try:
                declarado = vizinho.read_text(encoding="ascii",
                                              errors="ignore").strip()
                if declarado:
                    return declarado
            except OSError:
                pass
            break
    return "ISO-8859-1"


def pdf_georreferenciado(caminho: Path) -> bool:
    """
    O PDF tem georreferencia que o GDAL saiba ler?

    Exige as DUAS coisas, geotransform e sistema de coordenadas. O driver PDF
    abre qualquer PDF como raster rasterizado pelo Poppler: sem esta pergunta,
    um relatorio de texto entraria no projeto como uma imagem sem lugar no
    mapa, e o QGIS a empilharia sobre a origem do plano.

    Devolve False se o GDAL nao estiver disponivel (teste fora do QGIS) ou se
    o arquivo estiver corrompido: nesses casos a carta ainda aparece na lista,
    so que como arquivo.
    """
    try:
        from osgeo import gdal
    except ImportError:
        return False
    try:
        gdal.PushErrorHandler("CPLQuietErrorHandler")
        try:
            ds = gdal.Open(caminho_longo(caminho))
            if ds is None:
                return False
            return (ds.GetGeoTransform(can_return_null=True) is not None
                    and bool(ds.GetProjection()))
        finally:
            gdal.PopErrorHandler()
    except Exception:
        return False


def listar_arquivos(raiz: Path) -> list:
    """
    Acha os arquivos que podem virar camada, varrendo recursivamente.

    Devolve pares (caminho, especie), com especie "vetor", "raster", "nuvem",
    "tabela" ou "arquivo".

    A regra e de PERMISSAO: so vira camada o que esta numa das listas de
    extensao do config. Um sidecar como "GEOLOGIA_PREDITIVO.tif.aux.xml"
    termina em .xml, nao esta em lista nenhuma, e por isso nao vira camada
    duplicada — nao e preciso enumerar o que ignorar.
    """
    # A varredura SEMPRE usa o prefixo: sem ele o Windows devolve uma lista
    # vazia, em silencio, para pasta com caminho acima de 260 caracteres. Foi
    # o que aconteceu com o pacote "ARIM - Faixas Marginais", cujos arquivos
    # chegam a 350 — enquanto o de Juazeirinho, com 245, funcionava.
    raiz_curta = sem_prefixo(raiz)
    achados = []
    for caminho in sorted(Path(caminho_longo(raiz_curta)).rglob("*")):
        if not caminho.is_file():
            continue
        caminho = sem_prefixo(caminho)
        ext = caminho.suffix.lower()
        if caminho.name.endswith(SUFIXO_PONTOS):
            # GeoPackage que o proprio plugin gerou de uma tabela. Listar de
            # novo mostraria a mesma amostragem duas vezes: a aba e os pontos
            # dela. A conversao e reofertada a partir da tabela.
            continue
        if ext == ".pdf":
            # A carta do SGB e quase sempre um GeoPDF; sem georreferencia ela
            # so pode ser listada. Quem decide e o GDAL, nao a extensao.
            achados.append((caminho, "raster" if pdf_georreferenciado(caminho)
                            else "arquivo"))
        elif ext in EXTENSOES_VETORIAIS:
            achados.append((caminho, "vetor"))
        elif ext in EXTENSOES_RASTER:
            achados.append((caminho, "raster"))
        elif ext in EXTENSOES_NUVEM:
            achados.append((caminho, "nuvem"))
        elif ext in EXTENSOES_TABELA:
            achados.append((caminho, "tabela"))
        elif ext in EXTENSOES_SO_DOWNLOAD:
            achados.append((caminho, "arquivo"))
    return achados


def abrir_camada(item: "CamadaEncontrada"):
    """
    Cria a camada do QGIS correspondente, sem adicionar ao projeto.

    Devolve None para o que o QGIS nao abre (especie "arquivo").
    """
    from qgis.core import QgsVectorLayer, QgsRasterLayer

    if item.especie == "arquivo":
        return None
    if item.especie == "raster":
        return QgsRasterLayer(caminho_para_abrir(item.caminho), item.nome,
                              "gdal")
    if item.especie == "nuvem":
        from qgis.core import QgsPointCloudLayer
        return QgsPointCloudLayer(caminho_para_abrir(item.caminho),
                                  item.nome, "pdal")
    uri = caminho_para_abrir(item.caminho)
    if item.aba:
        uri += f"|layername={item.aba}"
    camada = QgsVectorLayer(uri, item.nome, "ogr")
    if item.codificacao:
        camada.setProviderEncoding(item.codificacao)
    return camada


#: Datum padrao ao espacializar uma tabela.
#:
#: Nao e chute: o shapefile que o SGB entrega junto das mesmas analises declara
#: GEOGCS["GCS_SIRGAS"] no .prj — SIRGAS 2000, oficial no Brasil desde 2005.
#: Seguimos o que o proprio orgao faz com o mesmo dado.
CRS_PADRAO = "EPSG:4674"


def criar_pontos(item, crs_authid: str = CRS_PADRAO, sobrescrever: bool = True):
    """
    Espacializa uma tabela: grava <nome>_pontos.gpkg ao lado dela e devolve
    (caminho, gravadas, puladas).

    129 pacotes de geoquimica baixam como planilha solta, sem o shapefile que o
    SGB costuma anexar — para esses, a coordenada so existe nas colunas
    LATITUDE/LONGITUDE. Gravar um GeoPackage, em vez de uma camada de memoria,
    faz o resultado sobreviver ao fechar o projeto.

    Usa GDAL direto, nao QgsVectorLayer, de proposito: o provedor OGR do QGIS
    mantem um pool de conexoes e a planilha continuava aberta depois da
    conversao, com o Windows recusando mover ou apagar a pasta do pacote.
    Com `ogr`, `ds = None` fecha na hora.
    """
    from osgeo import ogr, osr

    if not item.coordenadas:
        raise ValueError("a tabela nao tem colunas de coordenada")

    aba = f"_{limpar_para_arquivo(item.aba)}" if item.aba else ""
    destino = item.caminho.with_name(item.caminho.stem + aba + SUFIXO_PONTOS)
    if os.path.exists(caminho_longo(destino)) and not sobrescrever:
        return destino, None, None

    campo_lat, campo_lon = item.coordenadas
    origem = saida = None
    gravadas = puladas = 0
    try:
        origem = _abrir_planilha(item.caminho)
        if origem is None:
            raise ValueError("nao foi possivel abrir a tabela")
        entrada = (origem.GetLayerByName(item.aba) if item.aba
                   else origem.GetLayer(0))
        if entrada is None:
            raise ValueError(f"aba '{item.aba}' nao encontrada")
        definicao = entrada.GetLayerDefn()

        driver = ogr.GetDriverByName("GPKG")
        if os.path.exists(caminho_longo(destino)):
            driver.DeleteDataSource(caminho_para_abrir(destino))
        saida = driver.CreateDataSource(caminho_para_abrir(destino))

        srs = osr.SpatialReference()
        srs.SetFromUserInput(crs_authid)
        camada = saida.CreateLayer(item.nome[:60] or "pontos", srs,
                                   ogr.wkbPoint, ["OVERWRITE=YES"])
        for i in range(definicao.GetFieldCount()):
            camada.CreateField(definicao.GetFieldDefn(i))

        nomes = [definicao.GetFieldDefn(i).GetName()
                 for i in range(definicao.GetFieldCount())]
        alvo = camada.GetLayerDefn()
        for feicao in entrada:
            par = coordenada_valida(feicao.GetField(campo_lat),
                                    feicao.GetField(campo_lon))
            if par is None:
                puladas += 1
                continue
            nova = ogr.Feature(alvo)
            for i, nome in enumerate(nomes):
                nova.SetField(i, feicao.GetField(nome))
            ponto = ogr.Geometry(ogr.wkbPoint)
            ponto.AddPoint_2D(par[0], par[1])       # x = longitude
            nova.SetGeometry(ponto)
            camada.CreateFeature(nova)
            nova = None
            gravadas += 1
    finally:
        saida = None            # fecha e grava o GeoPackage
        origem = None           # solta a planilha na hora

    if not gravadas:
        try:
            os.remove(caminho_longo(destino))
        except OSError:
            pass
        raise ValueError("nenhuma linha tinha coordenada utilizavel")
    return destino, gravadas, puladas


def limpar_para_arquivo(texto: str) -> str:
    """Nome de aba vira parte de nome de arquivo."""
    import re as _re
    return _re.sub(r"[^A-Za-z0-9_-]+", "_", (texto or "")).strip("_")[:40]


def coordenada_valida(lat, lon):
    """
    Converte o par em (x, y) para o ponto, ou None se nao servir.

    Planilha de campo tem celula vazia, texto no lugar de numero e virgula
    decimal. Zero/zero tambem cai aqui: e o Golfo da Guine, nao o Brasil.

    Funcao pura — testavel sem QGIS.
    """
    def numero(valor):
        if valor is None:
            return None
        if isinstance(valor, (int, float)):
            return float(valor)
        texto = str(valor).strip().replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return None

    lat = numero(lat)
    lon = numero(lon)
    if lat is None or lon is None:
        return None
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:
        return None
    return lon, lat


def _abrir_planilha(caminho: Path):
    """
    Abre a planilha com a primeira linha sempre tratada como cabecalho.

    Sem HEADERS=FORCE o OGR decide sozinho, e decide diferente conforme o
    conteudo: numa planilha em que tudo e texto ele lê o cabecalho como dado e
    batiza os campos de Field1, Field2... Aí LATITUDE/LONGITUDE somem e a
    tabela nao pode ser espacializada.
    """
    from osgeo import gdal, ogr
    # Sem UseExceptions(): e estado global do processo, e o QGIS carrega dezenas
    # de plugins que compartilham o mesmo GDAL. Conferimos o retorno.
    try:
        ds = gdal.OpenEx(caminho_para_abrir(caminho), gdal.OF_VECTOR,
                         open_options=["HEADERS=FORCE"])
        if ds is not None:
            return ds
    except (AttributeError, RuntimeError):
        pass        # binding antigo, ou driver que nao aceita a opcao
    return ogr.Open(caminho_para_abrir(caminho))


def _abas_da_planilha(caminho: Path, raiz: Path) -> list:
    """
    Uma camada por aba da planilha.

    As tabelas de geoquimica do SGB separam o dado por meio amostral: a do ARIM
    Serido tem "Contagem" (1 linha, so um resumo), "Mineralometria" (169) e
    "Sedimento de corrente" (197). Ler so a primeira aba entregava a linha de
    resumo e escondia as 366 amostras.
    """
    from osgeo import ogr        # noqa: F401  (usado pelo _abrir_planilha)

    itens = []
    ds = None
    try:
        ds = _abrir_planilha(caminho)
        if ds is None:
            item = CamadaEncontrada(caminho, raiz, "tabela")
            item.erro = "não foi possível abrir"
            return [item]

        varias = ds.GetLayerCount() > 1
        for i in range(ds.GetLayerCount()):
            camada = ds.GetLayer(i)
            definicao = camada.GetLayerDefn()
            item = CamadaEncontrada(caminho, raiz, "tabela")
            if varias:
                item.aba = camada.GetName()
                item.nome = f"{caminho.stem[:40]} — {camada.GetName()}"
            item.feicoes = camada.GetFeatureCount()
            item.coordenadas = _achar_coordenadas(
                definicao.GetFieldDefn(j).GetName()
                for j in range(definicao.GetFieldCount()))
            itens.append(item)
    except Exception as e:                          # noqa: BLE001
        item = CamadaEncontrada(caminho, raiz, "tabela")
        item.erro = f"não foi possível ler: {e}"
        itens = [item]
    finally:
        ds = None
    return itens


def _achar_coordenadas(campos) -> tuple:
    """
    Procura as colunas de coordenada numa tabela.

    As planilhas de geoquimica do SGB trazem LATITUDE e LONGITUDE — a tabela do
    Projeto Calcario Itaituba, por exemplo. Saber disso nao muda o que o plugin
    faz hoje (adiciona como tabela, sem geometria), mas e a informacao que diz
    ao usuario que aquela planilha pode virar pontos no mapa.
    """
    nomes = {c.lower().strip(): c for c in campos}
    lat = next((nomes[n] for n in COLUNAS_LATITUDE if n in nomes), None)
    lon = next((nomes[n] for n in COLUNAS_LONGITUDE if n in nomes), None)
    return (lat, lon) if lat and lon else None


def _subcamadas_vetoriais(caminho: Path) -> list:
    """
    Os nomes das camadas dentro de um arquivo vetorial.

    Um .shp tem uma so, mas KML, KMZ, GeoPackage e GML tem quantas quiserem. O
    KML de Regencia, por exemplo, traz "Drenagem" (27 feicoes), "Corpos
    d'agua" (60) e "Litologia" (23): abrir so a primeira entregava 27 de 110 e
    descartava o resto em silencio.

    Lista vazia quando nao da para perguntar (OGR ausente, arquivo ilegivel):
    o chamador segue pelo caminho de sempre, de uma camada so.
    """
    try:
        from osgeo import gdal
    except ImportError:
        return []
    try:
        gdal.PushErrorHandler("CPLQuietErrorHandler")
        try:
            ds = gdal.OpenEx(caminho_longo(caminho), gdal.OF_VECTOR)
            if ds is None:
                return []
            return [ds.GetLayer(i).GetName() for i in range(ds.GetLayerCount())]
        finally:
            gdal.PopErrorHandler()
    except Exception:
        return []


def _uma_por_subcamada(caminho: Path, raiz: Path, nomes: list) -> list:
    """Um item do dialogo para cada camada de dentro do arquivo."""
    from qgis.core import QgsWkbTypes

    itens = []
    for nome in nomes:
        item = CamadaEncontrada(caminho, raiz, "vetor")
        item.aba = nome
        item.nome = f"{caminho.stem[:40]} — {nome}"
        camada = abrir_camada(item)
        if camada is None or not camada.isValid():
            item.erro = "não foi possível abrir"
            itens.append(item)
            continue
        item.geometria = QgsWkbTypes.geometryDisplayString(
            camada.geometryType())
        item.feicoes = camada.featureCount()
        crs = camada.crs()
        item.crs = crs.authid() or (crs.description() if crs.isValid() else "")
        if not crs.isValid():
            item.erro = "sem sistema de coordenadas"
        itens.append(item)
    return itens


def inspecionar(raiz: Path) -> list:
    """
    Abre cada candidata e le o que descreve a camada: geometria e feicoes no
    caso vetorial, dimensoes e bandas no raster.

    Precisa do QGIS carregado. Uma camada que nao abre entra na lista mesmo
    assim, com `erro` preenchido: e melhor o usuario ver "nao abriu" do que o
    arquivo sumir sem explicacao.
    """
    from qgis.core import QgsWkbTypes

    resultado = []
    for caminho, especie in listar_arquivos(raiz):
        if especie == "tabela":
            resultado.extend(_abas_da_planilha(caminho, raiz))
            continue
        if especie == "vetor":
            nomes = _subcamadas_vetoriais(caminho)
            if len(nomes) > 1:
                resultado.extend(_uma_por_subcamada(caminho, raiz, nomes))
                continue

        item = CamadaEncontrada(caminho, raiz, especie)
        if caminho.suffix.lower() == ".shp":
            item.codificacao = _codificacao(caminho)

        if especie == "arquivo":
            # Nao e camada, mas o usuario precisa saber que veio no pacote.
            item.dimensoes = _tamanho_legivel(caminho)
            resultado.append(item)
            continue

        camada = abrir_camada(item)
        if camada is None or not camada.isValid():
            item.erro = "não foi possível abrir"
            resultado.append(item)
            continue

        if especie == "raster":
            item.bandas = camada.bandCount()
            item.dimensoes = f"{camada.width():,}×{camada.height():,}".replace(
                ",", ".")
        elif especie == "nuvem":
            item.feicoes = camada.pointCount()
        elif especie == "tabela":
            item.feicoes = camada.featureCount()
            item.coordenadas = _achar_coordenadas(
                f.name() for f in camada.fields())
            # Tabela nao tem CRS, e isso nao e defeito: sair aqui evita
            # marca-la como "sem sistema de coordenadas".
            resultado.append(item)
            continue
        else:
            item.geometria = QgsWkbTypes.geometryDisplayString(
                camada.geometryType())
            item.feicoes = camada.featureCount()

        crs = camada.crs()
        item.crs = crs.authid() or (crs.description() if crs.isValid() else "")
        if not crs.isValid():
            item.erro = "sem sistema de coordenadas"
        resultado.append(item)
    return resultado


def adicionar_ao_projeto(itens, nome_grupo: str, em_pontos: bool = False,
                         crs_authid: str = CRS_PADRAO):
    """
    Adiciona as camadas num grupo com o nome do pacote, recolhido.

    Devolve (adicionadas, falhas). O grupo entra no topo da arvore para nao se
    perder embaixo de tudo quando ja ha muita coisa no projeto.

    Vetores vao acima dos rasters: um GeoTIFF de geofisica adicionado por cima
    esconderia os lineamentos e o limite da folha.
    """
    from qgis.core import QgsProject

    projeto = QgsProject.instance()
    grupo = projeto.layerTreeRoot().insertGroup(0, nome_grupo)
    grupo.setExpanded(False)

    ordem = {"vetor": 0, "nuvem": 1, "raster": 2, "tabela": 3}
    ordenados = sorted(itens, key=lambda i: (ordem.get(i.especie, 9),
                                             i.subpasta, i.nome))
    adicionadas, falhas = [], []
    for item in ordenados:
        if (em_pontos and item.especie == "tabela" and item.coordenadas):
            try:
                caminho, _gravadas, _puladas = criar_pontos(item, crs_authid)
                from qgis.core import QgsVectorLayer
                camada = QgsVectorLayer(str(caminho), item.nome, "ogr")
            except Exception:
                # Espacializar falhou: melhor a tabela crua do que nada.
                camada = abrir_camada(item)
        else:
            camada = abrir_camada(item)
        if camada is None or not camada.isValid():
            falhas.append(item)
            continue
        projeto.addMapLayer(camada, False)     # False: nao inserir na raiz
        grupo.addLayer(camada)
        adicionadas.append(camada)

    if not adicionadas:
        projeto.layerTreeRoot().removeChildNode(grupo)
    return adicionadas, falhas
