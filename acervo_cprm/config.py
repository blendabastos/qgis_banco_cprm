# -*- coding: utf-8 -*-
"""
config.py — Preferencias do plugin, guardadas no QgsSettings do usuario.

Tudo aqui tem valor padrao razoavel: o plugin precisa funcionar sem que
ninguem abra a tela de configuracao.
"""

from pathlib import Path

GRUPO = "acervo_cprm"

#: Colunas do catalogo enxuto. Mantido em sincronia com gerar_catalogo.py.
COLUNAS_CATALOGO = [
    "id", "titulo", "nivel_1", "nivel_2", "nivel_3", "nivel_4", "tipo",
    "nome_arquivo", "formato", "tamanho_bytes", "link_download", "origem",
]

#: Os tipos do acervo que o plugin oferece. Fonte unica: `gerar_catalogo.py`
#: filtra por esta lista e o painel monta o seletor de tipo a partir dela.
#:
#: Entra tambem o que o QGIS nao abre. O XYZ do Geosoft e baixavel ainda que
#: so o Oasis Montaj o leia, e "Mapa" e a carta geologica em PDF que acompanha
#: cada folha — ela cai no mesmo ramo da arvore que os vetores daquela folha,
#: entao quem esta olhando a folha acha a carta ali do lado.
#:
#: Fica de fora "Relatorio": 480 PDFs de texto, que nao pertencem a nenhuma
#: folha e so encompridariam a arvore.
TIPOS_INCLUIDOS = (
    "SIG (Vetores)",
    "KML",
    "Mapa",
    "Geofísica-Geotiff",
    "Geofísica-XYZ",
    "Nuvem de pontos (LiDAR)",
    "Ortofoto/raster",
    "Geoquímica-XLSX",
    "Geoquímica-CSV",
)

#: Destes o plugin baixa, mas nao ha o que adicionar ao projeto.
#:
#: "Mapa" saiu daqui: a carta georreferenciada abre como raster, entao ela
#: passa pelo dialogo de camadas como qualquer outro pacote. A carta sem
#: georreferencia aparece la listada e desabilitada, o que e a informacao que
#: o usuario precisa — melhor do que um dialogo que nao aparece.
TIPOS_SO_DOWNLOAD = ("Geofísica-XYZ",)

#: Destes o QGIS abre alguma coisa como camada.
TIPOS_ABRIVEIS = tuple(t for t in TIPOS_INCLUIDOS if t not in TIPOS_SO_DOWNLOAD)

#: Extensoes que o plugin adiciona como camada vetorial.
#:
#: `.parquet` esta aqui porque e o que o proprio plugin grava ao converter os
#: XYZ aerogeofisicos: no mesmo dado, 26,7 MB contra 95,1 MB do GeoPackage
#: indexado. O QGIS 4.0.1 abre GeoParquet nativamente — 315 mil feicoes em
#: 0,05 s, o mesmo tempo do GeoPackage.
EXTENSOES_VETORIAIS = {".shp", ".kml", ".kmz", ".gpkg", ".geojson", ".json",
                       ".gml", ".tab", ".mif", ".dxf", ".parquet"}

#: Planilhas e tabelas. O OGR do QGIS le .xlsx/.xls/.csv como camada sem
#: geometria, util para juntar com os pontos de amostragem. As 337 tabelas de
#: analise geoquimica do acervo caem aqui.
EXTENSOES_TABELA = {".xlsx", ".xls", ".csv", ".ods"}

#: Nomes de coluna que costumam carregar a coordenada nas tabelas do SGB.
COLUNAS_LATITUDE = ("latitude", "lat", "lat_dd", "y", "norte", "utm_n")
COLUNAS_LONGITUDE = ("longitude", "long", "lon", "long_dd", "x", "leste", "utm_e")

#: As unicas extensoes que o plugin descompacta.
#:
#: E uma lista de PERMISSAO, nao de negacao, e isso importa. Um .xlsx e um zip
#: com [Content_Types].xml, _rels/ e xl/ dentro; `zipfile.is_zipfile()` diz
#: "sim" e extrair a planilha explodia o OOXML na pasta — depois apagando o
#: original, tratado como "zip ja extraido".
#:
#: Negar uma lista de formatos-documento nao bastava: o SGB publica planilha
#: XLSX com o nome terminando em .xls (ARIM Serido, Folha Augusto Severo), e
#: nenhuma lista de negacao antecipa esse tipo de rotulo errado. Permitir
#: apenas .zip antecipa.
EXTENSOES_ARQUIVO_MORTO = {".zip"}

#: Sufixo dos GeoPackage que o proprio plugin gera ao espacializar uma tabela.
#: Sao ignorados ao listar o pacote: apareceriam como uma camada a mais, com a
#: mesma amostragem da aba que os originou.
SUFIXO_PONTOS = "_pontos.gpkg"

#: Extensoes de nuvem de pontos (QGIS 4 abre via PDAL).
EXTENSOES_NUVEM = {".las", ".laz", ".copc.laz"}

#: Formatos que ficam so como download: o QGIS nao os abre como camada.
#:
#: Os XYZ dos projetos aerogeofisicos (serie 1000/3000) sao formato Geosoft,
#: com blocos "LI n" e sem cabecalho delimitado. O provedor de texto delimitado
#: do QGIS nao da conta. Ficam extraidos na pasta, para abrir no Oasis Montaj
#: ou converter — e o dialogo diz isso em vez de ignorar o arquivo em silencio.
#: O .pdf esta aqui como FALLBACK. A carta em PDF do SGB costuma ser um
#: GeoPDF — o GDAL a abre como raster, com CRS e tudo, e e assim que ela entra
#: no projeto. Mas nem toda carta traz a georreferencia, e essas nao tem onde
#: ser colocadas no mapa. `pacote.listar_arquivos` pergunta ao GDAL, arquivo
#: por arquivo, e so as sem georreferencia caem aqui.
EXTENSOES_SO_DOWNLOAD = {".xyz", ".gdb", ".grd_geosoft", ".gxf", ".ers_geosoft",
                         ".pdf"}

#: Extensoes que o plugin adiciona como camada raster.
#:
#: Os pacotes "Base (Vetores, Kmz, Geotif, Grd e Flt)" de Levantamentos
#: Geofisicos sao majoritariamente raster: um deles traz 17 GeoTIFF (canal
#: total, torio, uranio, magnetometria, ternario) contra 4 shapefiles. Sem
#: isto o plugin descartava o conteudo principal do pacote em silencio.
EXTENSOES_RASTER = {".tif", ".tiff", ".grd", ".flt", ".ers", ".img", ".asc",
                    ".vrt", ".bil", ".dem", ".jp2"}

#: Como cada tipo aparece para quem usa.
#:
#: A CHAVE e o valor que o SGB publica e que esta gravado no catalogo — nao se
#: mexe nela, e por ela que o filtro casa. O VALOR e so rotulo de tela.
#:
#: "SIG (Vetores)" e o nome do SGB e esta errado como rotulo: raster tambem e
#: SIG. Na tela vale so o que a entrada tem de distinto, que e ser vetor.
ROTULO_TIPO = {
    "SIG (Vetores)": "Vetores",
    "Mapa": "Mapa (PDF)",
    "Geofísica-Geotiff": "Geofísica — Geotiff",
    "Geofísica-XYZ": "Geofísica — XYZ",
    "Nuvem de pontos (LiDAR)": "Nuvem de pontos (LiDAR)",
    "Ortofoto/raster": "Ortofoto e raster",
    "Geoquímica-XLSX": "Geoquímica — planilha",
    "Geoquímica-CSV": "Geoquímica — CSV",
}


def rotulo(tipo: str) -> str:
    """O nome do tipo como o usuario ve. Sem entrada no mapa, vale o proprio."""
    return ROTULO_TIPO.get(tipo, tipo)


#: O unico tipo do acervo cujos GeoTIFF ganham banda alfa automatica.
#:
#: A regra "branco que alcanca a moldura e fundo" foi medida nos 19 GeoTIFF
#: renderizados dos projetos 1017 e 1030, onde o branco e enquadramento. Fora
#: dessa populacao ela nao vale: num mapa geologico escaneado o branco e o
#: papel. Restringir pelo tipo mantem o acerto onde ele foi verificado.
TIPO_COM_MOLDURA_BRANCA = "Geofísica-Geotiff"


# Havia aqui uma EXTENSOES_IGNORADAS, com .dbf, .xml, .lyr e companhia.
# Nao era usada por ninguem: `listar_arquivos` funciona por PERMISSAO — so vira
# camada o que esta numa das listas acima. Uma lista de negacao parada ao lado
# e pior que inutil: convida quem for excluir uma extensao nova a acrescentar
# ali e nao entender por que nada muda.

PADROES = {
    "destino": "",             # vazio -> Documentos/Acervo CPRM
    "adicionar_ao_projeto": True,
    "manter_zip": False,       # apagar o .zip depois de extrair
    # O catalogo completo mora no proprio repositorio do plugin. Ja morou no
    # "download_banco_cprm", que e privado — e raw.githubusercontent nao serve
    # repositorio privado sem token, entao "Atualizar catalogo" respondia 404
    # para todo mundo, inclusive para quem tem acesso ao repositorio.
    #
    # Comprimido de proposito: 472 KB contra 5,3 MB crus. `catalogo.py`
    # reconhece o gzip pelos bytes magicos, nao pela extensao da URL.
    "url_catalogo": ("https://raw.githubusercontent.com/blendabastos/"
                     "qgis_banco_cprm/main/catalogo.csv.gz"),
}


def _settings():
    from qgis.core import QgsSettings
    return QgsSettings()


def destino_padrao() -> Path:
    """Documentos/Acervo CPRM, seguindo a pasta de documentos do sistema."""
    from qgis.PyQt.QtCore import QStandardPaths
    docs = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation)
    # Vazio em perfil sem pasta de documentos configurada; ai o palpite serve.
    return Path(docs or Path.home() / "Documents") / "Acervo CPRM"


def ler(chave: str):
    padrao = PADROES[chave]
    try:
        valor = _settings().value(f"{GRUPO}/{chave}", padrao)
    except Exception:
        return padrao
    if isinstance(padrao, bool):
        # QgsSettings devolve a string "false" no Windows; bool("false") e True.
        if isinstance(valor, str):
            return valor.strip().lower() not in ("false", "0", "")
        return bool(valor)
    return valor


def gravar(chave: str, valor):
    _settings().setValue(f"{GRUPO}/{chave}", valor)


def pasta_destino() -> Path:
    escolhido = (ler("destino") or "").strip()
    return Path(escolhido) if escolhido else destino_padrao()


def pasta_catalogo_atualizado() -> Path:
    """Onde fica a copia baixada do catalogo, se o usuario atualizou."""
    from qgis.PyQt.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation)
    destino = Path(base) / GRUPO if base else destino_padrao() / ".catalogo"
    destino.mkdir(parents=True, exist_ok=True)
    return destino / "catalogo_sig.csv"
