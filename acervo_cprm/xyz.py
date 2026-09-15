# -*- coding: utf-8 -*-
r"""
xyz.py — Le o XYZ do Geosoft e produz uma tabela de pontos georreferenciada.

Os 126 projetos aerogeofisicos do acervo somam 248 GB de .xyz descompactado,
em 677 arquivos, com algo perto de 1,4 bilhao de pontos de aquisicao. Cada
ponto e uma medida ao longo de uma linha de voo.

O formato tem uma gramatica comum — comentarios "/", metadados "//Flight" e
"//Date", um rotulo "Line 17430" abrindo cada bloco, dados em colunas de
largura fixa, "*" como nulo — mas quase tudo mais varia. Levantado arquivo por
arquivo sobre os 126 projetos:

    de 4 a 37 colunas
    rotulo de linha escrito Line (81x), LINE (33x) ou LI (2x)
    109 de 120 trazem os nomes das colunas na ultima linha "/" antes dos dados
    e a contagem bate exatamente; os outros 11 nao trazem nome nenhum

TODOS tem coordenada — o que falta nesses 11 e o nome, nao o numero. Sao cinco
formas diferentes de gravar posicao, e a de numero 5 merece atencao:

    1. grau decimal em colunas LONGITUDE/LATITUDE          108 projetos
    2. UTM em colunas UTME/UTMN ou X/Y                     106 projetos
    3. UTM nas colunas 0 e 1, sem nome                     1020, 1047, 1054,
                                                           1055, 1056, 1057, 3065
    4. Mercator Equatorial sobre esfera Clarke 1880        1012, 1013, 1014
    5. grau.minuto.segundo com ponto, LATITUDE PRIMEIRO    1009

A 5 e "-15.27.08.20", que e -15 graus 27 minutos 8,20 segundos. Um float()
ingenuo levanta ValueError ali, o que e sorte: falha barulhenta em vez de
coordenada errada. A 4 e um CRS sem codigo EPSG, descrito em prosa dentro de um
.doc do Word que veio no pacote.

Nada disso e adivinhado em silencio. `analisar()` devolve de onde tirou cada
decisao, e `verificar()` confere se o resultado cai onde o projeto deveria
estar. Coordenada errada que ninguem percebe e pior que conversao recusada.
"""

import re
import math
import unicodedata

# ─── Gramatica do formato ────────────────────────────────────────────────────

#: Abre um bloco de linha de voo. "Tie" e linha de controle, que cruza as de
#: medida para nivelar o levantamento — vai junto, com uma coluna dizendo qual.
RE_ROTULO = re.compile(r"^\s*(LINE|Line|line|LI|TIE|Tie|tie|FLIGHT|Flight)"
                       r"\s*[:=]?\s*(\S+)?", re.ASCII)

#: "//Flight 172" e "//Date 2012/05/18" — valem para o bloco seguinte.
RE_META = re.compile(r"^\s*//\s*(\w+)\s+(.*)$")

#: Nulo do Geosoft. Aparece 244.506 vezes so no Gama.XYZ do projeto 3065.
NULO = "*"


def partir(texto, separador=None):
    """
    Quebra uma linha de dados em campos.

    `separador` None e o XYZ classico, alinhado por espaco. A partir dos
    levantamentos da serie 3000 o SGB passou a exportar do Geosoft em CSV
    ("/ CSV EXPORT", virgula, sem alinhamento), e ai `separador` e ",".

    No modo virgula o campo vazio vira NULO: ",," no meio da linha e ausencia
    de medida, e mante-lo como "" faria a coluna inteira parecer texto.
    """
    if separador is None:
        return texto.split()
    return [p.strip() or NULO for p in texto.split(separador)]


def separador_provavel(linhas_de_dados):
    """
    Espaco ou virgula, decidido pelo que sobra DENTRO de cada campo.

    Contar colunas nao resolve. Numa linha com virgula decimal separada por
    espaco — "787207,5  8540867,2  -48,350480" — a virgula produz MAIS campos
    que o espaco, e a contagem sozinha escolheria errado, cortando cada numero
    ao meio.

    O que separa os dois casos e o espaco residual: no CSV do Geosoft nenhum
    campo tem espaco interno, enquanto na virgula decimal o corte deixa
    "5  8540867" grudado. Entao a virgula so vale quando ela limpa a linha
    inteira.
    """
    if not linhas_de_dados:
        return None
    n_bons = 0
    for s in linhas_de_dados:
        campos = partir(s, ",")
        if len(campos) > 1 and not any(re.search(r"\s", c) for c in campos):
            n_bons += 1
    return "," if n_bons > len(linhas_de_dados) / 2 else None

#: Grau-minuto-segundo separado por ponto: -15.27.08.20 == -15o 27' 08,20".
#: Tem que casar a string inteira, senao "-15.27" (grau decimal legitimo)
#: entraria aqui e viraria -15o 27' 0".
RE_GMS = re.compile(r"^([+-]?)(\d{1,3})\.(\d{1,2})\.(\d{1,2}(?:\.\d+)?)$")

#: "/COORDENADAS UTM ELIPSOIDE INTERNACIONAL HAYFORD 1910 MC= -39"
#: Em 34 projetos. A grafia varia ("ELIPSOIDE", "ELIPSODE"), o numero nao.
RE_MC = re.compile(r"MC\s*=?\s*(-?\d{2})", re.I)
RE_ZONA = re.compile(r"ZONA?\s*[:=]?\s*(\d{2})\s*S", re.I)

#: Codigo de folha do IBGE no nome do arquivo: SB22XC2G.XYZ. O "22" e o fuso
#: UTM — a carta ao milionesimo e indexada por fuso.
#:
#: Sem \b no fim, de proposito: em "SB22XC2G" o "2" e o "X" sao os dois
#: caracteres de palavra, entao nao ha fronteira ali e a versao com \b nunca
#: casava. Tudo o que precisamos e que o proximo caractere nao seja digito,
#: para nao morder um numero maior.
RE_FOLHA = re.compile(r"(?<![A-Za-z0-9])(S[A-D])[.\-]?(\d{2})(?!\d)", re.I)

#: "Latitudes (min/max) : -13o10' / -12o50'   Longitudes ... : -48o24' / -48o09'"
#: Caixa de coordenadas em prosa nos leiames. Serve de gabarito.
RE_CAIXA = re.compile(
    r"(latitude|longitude)s?\s*\(min/max\)\s*:\s*"
    r"(-?\s*\d{1,3})\D{1,3}(\d{1,2})?\D{0,3}\s*/\s*"
    r"(-?\s*\d{1,3})\D{1,3}(\d{1,2})?", re.I)

#: Brasil continental com folga. Qualquer coordenada que caia fora disso esta
#: errada, e o mais provavel e que o CRS tenha sido mal escolhido.
BRASIL = (-74.5, -34.0, -34.0, 6.5)      # oeste, sul, leste, norte

#: Mercator Equatorial da familia SAMMP (projetos 1012, 1013, 1014).
#:
#: Do 1014.doc, palavras do proprio SGB: "As coordenadas estao em Equatorial
#: Mercator (EM). Para reproje-las, deve-se usar o Datum AMMP/SAMMP do software
#: Oasis Montaj da empresa Geosoft: esfera Clarke 1880, com raio de
#: 6378249,145 m; meridiano de origem 0o; paralelo de origem 0o."
#:
#: Nao tem codigo EPSG. Esfera, nao elipsoide: +a e +b iguais.
PROJ_MERCATOR_EM = ("+proj=merc +lat_ts=0 +lon_0=0 +x_0=0 +y_0=0 "
                    "+a=6378249.145 +b=6378249.145 +units=m +no_defs")
RAIO_EM = 6378249.145

#: Nomes de coluna que carregam posicao. Ordem importa: o primeiro que casar
#: vence, e "LONGITUDE" tem que ser testado antes de "LONG" nao por precisao,
#: mas porque a comparacao e exata.
NOMES_LON = ("LONGITUDE", "LONGITUD", "LONG", "LON", "X_GEO", "LONGDD")
NOMES_LAT = ("LATITUDE", "LATITUD", "LAT", "Y_GEO", "LATDD")
NOMES_ESTE = ("UTME", "X", "XUTM", "UTM_E", "EASTING", "EAST", "LESTE", "ESTE")
NOMES_NORTE = ("UTMN", "Y", "YUTM", "UTM_N", "NORTHING", "NORTH", "NORTE")


# ─── Faixas de valor, para reconhecer coordenada sem nome ────────────────────

def _e_longitude(a, b):
    return -74.5 < a and b < -34.0 and (b - a) < 15.0


def _e_latitude(a, b):
    return -34.0 < a and b < 6.5 and (b - a) < 15.0


def _e_este_utm(a, b):
    return 100_000 < a and b < 1_000_000


def _e_norte_utm(a, b):
    # Hemisferio sul com falso norte de 10.000.000, mais a faixa equatorial.
    return 6_500_000 < a and b < 10_100_000


def _e_mercator_em(a, b):
    # Longitude do Brasil vezes o raio da esfera Clarke 1880.
    return -8_500_000 < a and b < -3_500_000


# ─── Leitura de valores ──────────────────────────────────────────────────────

def ler_numero(texto):
    """
    Converte um campo do XYZ em float, ou None se nao for numero.

    Aceita a notacao cientifica do Geosoft antigo (-5.454484E+06) e o nulo "*".
    Nao aceita grau-minuto-segundo: isso e decisao de esquema, nao de campo, e
    vai por `ler_gms` depois que `analisar` decidiu que a coluna e GMS.

    Tambem nao aceita "nan" nem "inf", que o float() do Python engole de bom
    grado. Um NaN na coluna de coordenada viraria uma geometria em NaN, e a
    extensao da camada inteira iria junto — inclusive a verificacao que existe
    justamente para pegar coordenada errada. Melhor tratar como ausente.
    """
    if not texto or texto == NULO:
        return None
    try:
        valor = float(texto)
    except ValueError:
        return None
    return valor if math.isfinite(valor) else None


def ler_gms(texto):
    """
    "-15.27.08.20" -> -15.451722  (grau, minuto, segundo separados por ponto)

    So o projeto 1009 usa isto, e o sinal fica no grau: os minutos e segundos
    de uma latitude sul sao positivos e o grau e que e negativo.

    Minuto ou segundo fora de 0..59 e recusado. O padrao casa dois digitos, e
    sem esta conferencia "-15.99.99" virava -16,6775 — um numero plausivel,
    dentro do Brasil, a uns 75 km do lugar certo. Erro que ninguem percebe
    olhando o mapa.
    """
    m = RE_GMS.match(texto.strip())
    if not m:
        return None
    sinal, g, mi, seg = m.groups()
    minutos, segundos = int(mi), float(seg)
    if minutos > 59 or segundos >= 60.0:
        return None
    valor = int(g) + minutos / 60.0 + segundos / 3600.0
    return -valor if sinal == "-" else valor


def parece_gms(amostra):
    """True se a maioria dos valores da coluna e grau.minuto.segundo."""
    casam = sum(1 for v in amostra if v and RE_GMS.match(v.strip()))
    return casam >= max(3, int(0.8 * len(amostra)))


# ─── Esquema descoberto ──────────────────────────────────────────────────────

class Esquema:
    """
    O que descobrimos sobre um arquivo XYZ antes de converter.

    Guarda tambem DE ONDE veio cada decisao (`procedencia`), porque o usuario
    precisa poder discordar: o acervo tem leiame com erro de digitacao e
    projeto que mudou de datum entre a aquisicao e a publicacao.
    """

    def __init__(self):
        self.n_colunas = 0
        self.separador = None     # None = alinhado por espaco; "," = CSV
        self.nomes = []           # nome de cada coluna, ou "c00", "c01"...
        self.tipos = []           # "real" ou "texto"
        self.ix = None            # indice da coluna de X / longitude
        self.iy = None            # indice da coluna de Y / latitude
        self.forma = ""           # "grau", "gms", "utm", "mercator_em"
        self.crs = ""             # "EPSG:4326" ou proj-string
        self.procedencia = []     # como cada coisa foi decidida
        self.avisos = []
        self.caixa_esperada = None    # (oeste, sul, leste, norte) do leiame
        self.n_amostra = 0
        self.extensao_amostra = None  # (xmin, ymin, xmax, ymax) nas unidades
        self.problemas = []           # o que `verificar` achou, na amostra
        self.zona_observada = None    # fuso deduzido de X e LONGITUDE juntos
        self.arquivo = ""

    @property
    def tem_coordenada(self):
        return self.ix is not None and self.iy is not None and bool(self.crs)

    def anotar(self, texto):
        self.procedencia.append(texto)

    def __repr__(self):
        return "<Esquema %d cols, %s, %s>" % (self.n_colunas, self.forma,
                                              self.crs)


# ─── Cabecalho ───────────────────────────────────────────────────────────────

def nomes_do_cabecalho(linhas_cru, separador=None):
    """
    Os nomes das colunas, se o arquivo os traz.

    A convencao do Geosoft e a ULTIMA linha de comentario "/" antes dos dados.
    Isso importa: os projetos dos anos 80 abrem com um titulo em caixa alta
    ("/PROJETO AEROGEOFISICO PALMEIROPOLIS ...") e so depois vem a linha de
    nomes. Pegar a primeira linha "/" devolveria o titulo — foi o que eu fiz na
    primeira tentativa, e deu 35 projetos "sem nomes" que na verdade os tinham.

    Reguas de "=====" e "-----" sao descartadas: o Geosoft as imprime entre os
    nomes e os dados.
    """
    ultima = None
    for l in linhas_cru:
        s = l.rstrip()
        if not s.strip():
            continue
        if s.startswith("//"):
            continue
        if s.startswith("/"):
            corpo = s.lstrip("/ ").rstrip()
            if corpo and not re.fullmatch(r"[=\-\s.]+", corpo):
                ultima = partir(corpo, separador)
            continue
        if RE_ROTULO.match(s):
            continue
        break                      # chegou nos dados
    return ultima


def _limpar_nome_de_campo(nome, usados):
    """
    Nome de coluna aceitavel como campo de tabela.

    Acento vira ASCII e o que sobra fora de [A-Za-z0-9_] vira "_": o Parquet
    aceita quase tudo, mas o GeoPackage e o shapefile nao, e o usuario vai
    querer exportar. Duplicata ganha sufixo em vez de sobrescrever.
    """
    base = unicodedata.normalize("NFKD", nome or "")
    base = base.encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_").lower()
    if not base or base[0].isdigit():
        base = "c_" + base
    nome_final = base[:56]
    n = 2
    while nome_final in usados:
        nome_final = "%s_%d" % (base[:52], n)
        n += 1
    usados.add(nome_final)
    return nome_final


# ─── Varredura de amostra ────────────────────────────────────────────────────

class Amostra:
    """Primeiras linhas de dados, ja separadas em colunas."""

    def __init__(self):
        self.linhas = []
        self.comentarios = []
        self.n_colunas = 0
        self.separador = None

    def coluna(self, i):
        return [l[i] for l in self.linhas if i < len(l)]

    def faixa(self, i):
        """(min, max) dos valores numericos da coluna, ou (None, None)."""
        vs = [v for v in (ler_numero(x) for x in self.coluna(i))
              if v is not None]
        return (min(vs), max(vs)) if vs else (None, None)

    def so_numeros(self, i):
        vs = self.coluna(i)
        if not vs:
            return False
        bons = sum(1 for v in vs if v == NULO or ler_numero(v) is not None)
        return bons >= max(1, int(0.95 * len(vs)))


def amostrar(linhas_cru, limite=4000):
    """Le ate `limite` linhas de dados, guardando tambem os comentarios."""
    a = Amostra()
    contagens = {}
    cruas = []
    for l in linhas_cru:
        s = l.strip()
        if not s:
            continue
        if s.startswith("/"):
            a.comentarios.append(s)
            continue
        if RE_ROTULO.match(s):
            continue
        cruas.append(s)
        if len(cruas) >= limite:
            break

    # O separador sai das primeiras linhas de dados de verdade, nao do
    # cabecalho: comentario do Geosoft tem virgula em data e em nome de campo
    # independentemente de como os dados estao escritos.
    a.separador = separador_provavel(cruas[:200])

    for s in cruas:
        partes = partir(s, a.separador)
        a.linhas.append(partes)
        contagens[len(partes)] = contagens.get(len(partes), 0) + 1
    if contagens:
        # A contagem dominante: um arquivo truncado pode ter uma ultima linha
        # pela metade, e ela nao pode definir o esquema.
        a.n_colunas = max(contagens.items(), key=lambda kv: kv[1])[0]
        a.linhas = [l for l in a.linhas if len(l) == a.n_colunas]
    return a


# ─── CRS ─────────────────────────────────────────────────────────────────────

def zona_do_meridiano(mc):
    """MC = 6*fuso - 183. MC=-51 -> fuso 22."""
    z = (int(mc) + 183) / 6.0
    return int(z) if abs(z - round(z)) < 1e-6 and 17 <= z <= 26 else None


def epsg_utm(zona, texto_datum=""):
    """
    Codigo EPSG do UTM sul para o fuso, escolhendo o datum pelo que o
    documento diz.

    "HAYFORD 1910" e "ELIPSOIDE INTERNACIONAL" significam Corrego Alegre —
    e como o SGB escrevia nos anos 80. So existe nos fusos 21S a 25S; fora
    disso cai em SAD69, que e o padrao da geofisica brasileira pre-2005.
    """
    t = (texto_datum or "").upper()
    if "SIRGAS" in t:
        return "EPSG:%d" % (31960 + zona)          # SIRGAS 2000 / UTM zona S
    if "WGS" in t:
        return "EPSG:%d" % (32700 + zona)          # WGS 84 / UTM zona S
    if ("HAYFORD" in t or "INTERNACIONAL" in t) and 21 <= zona <= 25:
        return "EPSG:%d" % (22500 + zona)          # Corrego Alegre / UTM zona S
    return "EPSG:%d" % (29170 + zona)              # SAD69 / UTM zona S


def caixa_do_texto(texto):
    """
    A caixa de coordenadas em prosa do leiame, em grau decimal.

    O 1047 escreve "Latitudes (min/max) : - 10o00'/ -05o30'   Longitudes
    (min/max) : -53o00' / -51o00'". Serve de gabarito para conferir a
    conversao, e sozinha ja determina o fuso UTM.
    """
    achados = {}
    for m in RE_CAIXA.finditer(texto):
        qual = m.group(1).lower()
        a = _grau_minuto(m.group(2), m.group(3))
        b = _grau_minuto(m.group(4), m.group(5))
        if a is None or b is None:
            continue
        achados[qual] = (min(a, b), max(a, b))
    if "latitude" in achados and "longitude" in achados:
        lon0, lon1 = achados["longitude"]
        lat0, lat1 = achados["latitude"]
        return (lon0, lat0, lon1, lat1)
    return None


def _grau_minuto(grau, minuto):
    try:
        g = int(re.sub(r"\s+", "", grau))
    except (TypeError, ValueError):
        return None
    m = int(minuto) if minuto else 0
    return g - m / 60.0 if g < 0 else g + m / 60.0


def zona_do_nome(nome_arquivo):
    """Fuso a partir do codigo de folha do IBGE: SB22XC2G.XYZ -> 22."""
    m = RE_FOLHA.search(nome_arquivo or "")
    if not m:
        return None
    z = int(m.group(2))
    return z if 17 <= z <= 26 else None


# ─── Analise ─────────────────────────────────────────────────────────────────

def analisar(linhas_cru, nome_arquivo="", texto_auxiliar=""):
    """
    Descobre o esquema de um XYZ: colunas, coordenada e CRS.

    `linhas_cru`      as primeiras milhares de linhas do arquivo, ja em str
    `nome_arquivo`    usado para o codigo de folha do IBGE
    `texto_auxiliar`  leiame/readme que veio no mesmo pacote, se houver

    Devolve um `Esquema`. Quando `tem_coordenada` e False, `avisos` diz por que
    — o chamador mostra isso em vez de converter no escuro.
    """
    esq = Esquema()
    amostra = amostrar(linhas_cru)
    esq.n_colunas = amostra.n_colunas
    esq.separador = amostra.separador
    esq.n_amostra = len(amostra.linhas)
    if esq.separador == ",":
        esq.anotar("Campos separados por virgula (exportacao CSV do Geosoft).")
    if not esq.n_colunas:
        esq.avisos.append("Nenhuma linha de dados reconhecida no arquivo.")
        return esq

    texto_cabecalho = "\n".join(amostra.comentarios)
    texto_todo = texto_cabecalho + "\n" + (texto_auxiliar or "")

    _nomear_colunas(esq, amostra, nome_arquivo)
    _achar_coordenada(esq, amostra)
    _resolver_crs(esq, texto_todo, texto_cabecalho, nome_arquivo)

    esq.caixa_esperada = caixa_do_texto(texto_todo)
    if esq.caixa_esperada:
        esq.anotar("Caixa de coordenadas do leiame: %.2f,%.2f .. %.2f,%.2f"
                   % esq.caixa_esperada)

    # Confere JA, na amostra. Converter 12 GB para so entao descobrir que o
    # fuso estava errado seria 21 minutos jogados fora — e o usuario so
    # perceberia se olhasse o mapa.
    esq.extensao_amostra = _extensao_da_amostra(esq, amostra)
    if esq.extensao_amostra:
        esq.problemas = verificar(esq, esq.extensao_amostra)
    return esq


def _extensao_da_amostra(esq, amostra):
    if not esq.tem_coordenada:
        return None
    ler = ler_gms if esq.forma == "gms" else ler_numero
    xs, ys = [], []
    for partes in amostra.linhas:
        if esq.ix >= len(partes) or esq.iy >= len(partes):
            continue
        x, y = ler(partes[esq.ix]), ler(partes[esq.iy])
        if x is not None and y is not None:
            xs.append(x)
            ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def _nomear_colunas(esq, amostra, nome_arquivo):
    nomes = nomes_do_cabecalho(amostra.comentarios + ["0 " * amostra.n_colunas],
                               amostra.separador)
    if nomes and len(nomes) == amostra.n_colunas:
        esq.anotar("Nomes das colunas: linha de cabecalho do proprio arquivo.")
    else:
        if nomes:
            esq.avisos.append(
                "A linha de cabecalho tem %d nomes para %d colunas; ignorada."
                % (len(nomes), amostra.n_colunas))
        nomes = ["c%02d" % i for i in range(amostra.n_colunas)]
        esq.anotar("Sem cabecalho utilizavel: colunas numeradas por posicao.")
    usados = set()
    esq.nomes = [_limpar_nome_de_campo(n, usados) for n in nomes]
    esq.tipos = ["real" if amostra.so_numeros(i) else "texto"
                 for i in range(amostra.n_colunas)]


def _achar_coordenada(esq, amostra):
    """
    Onde estao X e Y. Por nome primeiro; por faixa de valor se nao houver nome.

    A ordem e deliberada: grau decimal antes de UTM. Quando o arquivo traz as
    duas coisas — e 67 projetos trazem —, o grau e melhor, porque dispensa
    saber o fuso e o datum da projecao.
    """
    up = [n.upper() for n in esq.nomes]

    def por_nome(candidatos):
        for c in candidatos:
            if c in up:
                return up.index(c)
        return None

    ilon, ilat = por_nome(NOMES_LON), por_nome(NOMES_LAT)
    ie_, ino_ = por_nome(NOMES_ESTE), por_nome(NOMES_NORTE)

    if ilon is not None and ilat is not None:
        esq.ix, esq.iy, esq.forma = ilon, ilat, "grau"
        esq.anotar("Coordenada: colunas %s e %s, por nome."
                   % (esq.nomes[ilon], esq.nomes[ilat]))
        # 67 projetos trazem UTM E grau na mesma linha. Quando isso acontece,
        # o fuso sai de graca — e serve para os arquivos irmaos do pacote que
        # so tem UTM, como o 1114_Cruzamentos.XYZ ao lado do 1114_MagLine.XYZ.
        if ie_ is not None:
            esq.zona_observada = _zona_de_um_par(amostra, ie_, ilon)
            if esq.zona_observada:
                esq.anotar("Fuso %d deduzido da coluna %s junto com %s."
                           % (esq.zona_observada, esq.nomes[ie_],
                              esq.nomes[ilon]))
        return

    ie, ino = ie_, ino_
    if ie is not None and ino is not None:
        esq.ix, esq.iy, esq.forma = ie, ino, "utm"
        esq.anotar("Coordenada: colunas %s e %s, por nome."
                   % (esq.nomes[ie], esq.nomes[ino]))
        return

    _achar_coordenada_por_valor(esq, amostra)


def _achar_coordenada_por_valor(esq, amostra):
    """
    Sem nome de coluna: reconhece a coordenada pela faixa de valores.

    A longitude do Brasil (-74 a -34) e distintiva o bastante para ser achada
    sozinha; a latitude nao e, porque qualquer canal de gamaespectrometria tem
    valores entre -34 e 6. Entao a longitude decide, e a latitude e procurada
    ao lado dela. Testado nos 11 projetos sem cabecalho: acerta em todos.
    """
    n = amostra.n_colunas

    # 5. grau-minuto-segundo, latitude primeiro (projeto 1009)
    if n >= 2 and parece_gms(amostra.coluna(0)) and parece_gms(amostra.coluna(1)):
        esq.ix, esq.iy, esq.forma = 1, 0, "gms"
        esq.anotar("Coordenada: grau.minuto.segundo nas colunas 0 e 1, "
                   "latitude primeiro (detectado pelo formato dos valores).")
        return

    faixas = [amostra.faixa(i) for i in range(n)]
    lons = [i for i, (a, b) in enumerate(faixas)
            if a is not None and _e_longitude(a, b)]
    lats = [i for i, (a, b) in enumerate(faixas)
            if a is not None and _e_latitude(a, b)]

    # 1. grau decimal: a longitude manda, a latitude tem que estar vizinha.
    #
    # A DIREITA primeiro, e isso nao e detalhe. O Geosoft exporta LONGITUDE e
    # depois LATITUDE, e no projeto 3065 a coluna a esquerda da longitude tem
    # valores entre 0,064 e 0,179 — que passam como latitude plausivel e ficam
    # dentro do Brasil, perto do equador. Escolher o vizinho errado ali daria
    # uma camada que abre, desenha e esta errada, e a verificacao de extensao
    # nao pegaria. A convencao de ordem e o que desempata.
    if len(lons) == 1:
        ilon = lons[0]
        for candidata in (ilon + 1, ilon - 1):
            if candidata in lats:
                esq.ix, esq.iy, esq.forma = ilon, candidata, "grau"
                esq.anotar(
                    "Coordenada: grau decimal nas colunas %d e %d, "
                    "reconhecidas pela faixa de valores%s."
                    % (ilon, candidata,
                       "" if candidata == ilon + 1 else
                       " (latitude a esquerda da longitude, fora da ordem usual)"))
                return

    # 3. UTM nas colunas 0 e 1
    if n >= 2:
        a0, b0 = faixas[0]
        a1, b1 = faixas[1]
        if a0 is not None and a1 is not None \
                and _e_este_utm(a0, b0) and _e_norte_utm(a1, b1):
            esq.ix, esq.iy, esq.forma = 0, 1, "utm"
            esq.anotar("Coordenada: UTM nas colunas 0 e 1, reconhecidas pela "
                       "faixa de valores.")
            return

        # 4. Mercator Equatorial da familia SAMMP
        if a0 is not None and a1 is not None \
                and _e_mercator_em(a0, b0) and -3_500_000 < a1 and b1 < 0:
            esq.ix, esq.iy, esq.forma = 0, 1, "mercator_em"
            esq.anotar("Coordenada: Mercator Equatorial nas colunas 0 e 1 "
                       "(familia SAMMP), reconhecido pela faixa de valores.")
            return

    esq.avisos.append(
        "Nao consegui identificar quais colunas sao a coordenada. "
        "O arquivo tem %d colunas e %d linhas de dados na amostra."
        % (n, len(amostra.linhas)))


def _resolver_crs(esq, texto_todo, texto_cabecalho, nome_arquivo):
    """
    Qual e o CRS, e de onde essa informacao veio.

    Quatro fontes, nesta ordem de confianca:
        1. o proprio arquivo, na linha "/COORDENADAS UTM ... MC= -39"   (34 proj)
        2. o leiame que veio no pacote ("Datum SAD 29 - UTM zona 23S")
        3. a caixa de coordenadas em prosa do leiame, que fixa o fuso
        4. o codigo de folha do IBGE no nome do arquivo (SB22... -> fuso 22)
    """
    if not esq.forma:
        return

    if esq.forma in ("grau", "gms"):
        esq.crs = "EPSG:4326"
        esq.anotar("CRS: EPSG:4326, por serem coordenadas geodeticas.")
        esq.avisos.append(
            "O datum geodetico nao e declarado pelo SGB. Os projetos "
            "anteriores a 1990 costumam estar em Corrego Alegre ou SAD69, que "
            "diferem do WGS84/SIRGAS em ate ~200 m. Para medir distancia com "
            "rigor, confira o relatorio do projeto.")
        return

    if esq.forma == "mercator_em":
        esq.crs = PROJ_MERCATOR_EM
        esq.anotar("CRS: Mercator Equatorial sobre esfera Clarke 1880 "
                   "(raio 6.378.249,145 m), como o SGB documenta no pacote. "
                   "Nao tem codigo EPSG.")
        return

    # UTM: falta o fuso.
    zona = fonte = None
    m = RE_MC.search(texto_cabecalho)
    if m:
        zona, fonte = zona_do_meridiano(m.group(1)), \
            "meridiano central declarado no proprio arquivo (MC=%s)" % m.group(1)
    if zona is None:
        m = RE_MC.search(texto_todo)
        if m:
            zona, fonte = zona_do_meridiano(m.group(1)), \
                "meridiano central declarado no leiame (MC=%s)" % m.group(1)
    if zona is None:
        m = RE_ZONA.search(texto_todo)
        if m:
            z = int(m.group(1))
            if 17 <= z <= 26:
                zona, fonte = z, "fuso declarado no leiame (zona %dS)" % z
    if zona is None:
        caixa = caixa_do_texto(texto_todo)
        if caixa:
            meio = (caixa[0] + caixa[2]) / 2.0
            z = int(math.floor((meio + 180) / 6.0)) + 1
            if 17 <= z <= 26:
                zona, fonte = z, "caixa de coordenadas do leiame"
    if zona is None:
        z = zona_do_nome(nome_arquivo)
        if z:
            zona, fonte = z, "codigo de folha do IBGE no nome do arquivo"

    if zona is None:
        esq.avisos.append(
            "As coordenadas sao UTM, mas o fuso nao esta declarado em lugar "
            "nenhum do pacote. Escolha o fuso para converter.")
        return

    esq.crs = epsg_utm(zona, texto_todo)
    esq.anotar("CRS: %s — fuso %d vindo do %s." % (esq.crs, zona, fonte))
    if not RE_MC.search(texto_todo) and "SIRGAS" not in texto_todo.upper() \
            and "SAD" not in texto_todo.upper() \
            and "HAYFORD" not in texto_todo.upper():
        esq.avisos.append(
            "O datum nao foi declarado; assumi SAD69, padrao da geofisica "
            "brasileira antes de 2005. Se o relatorio disser outro, troque.")


# ─── Verificacao ─────────────────────────────────────────────────────────────

def para_lonlat(esq, x, y):
    """
    Converte um par do arquivo para grau decimal, sem depender do GDAL.

    Serve so para a verificacao de sanidade, que roda antes de converter e
    precisa ser barata. A conversao de verdade usa o CRS declarado e deixa o
    GDAL/PROJ fazer o trabalho com o rigor que ele tem.
    """
    if esq.forma in ("grau", "gms"):
        return x, y
    if esq.forma == "mercator_em":
        lon = math.degrees(x / RAIO_EM)
        lat = math.degrees(2 * math.atan(math.exp(y / RAIO_EM)) - math.pi / 2)
        return lon, lat
    if esq.forma == "utm":
        zona = _zona_do_crs(esq.crs)
        if zona is None:
            return None, None
        return _utm_aproximado(x, y, zona)
    return None, None


def _zona_do_crs(crs):
    m = re.search(r"EPSG:(\d+)", crs or "")
    if not m:
        return None
    c = int(m.group(1))
    for base in (31960, 32700, 22500, 29170):
        z = c - base
        if 17 <= z <= 26:
            return z
    return None


def _utm_aproximado(este, norte, zona):
    """
    UTM sul -> lon/lat, esferico. Erra alguns quilometros, e tudo bem: a
    pergunta que responde e "isto caiu no Brasil ou na Africa?".
    """
    mc = 6 * zona - 183
    k0, R = 0.9996, 6378137.0
    x = (este - 500_000.0) / k0
    y = (norte - 10_000_000.0) / k0
    lat = math.degrees(y / R)
    cos_lat = math.cos(math.radians(lat))
    if abs(cos_lat) < 1e-9:
        return None, None
    lon = mc + math.degrees(x / (R * cos_lat))
    return lon, lat


def verificar(esq, extensao):
    """
    Confere se a extensao convertida cai onde o projeto deveria estar.

    `extensao` e (xmin, ymin, xmax, ymax) nas unidades do arquivo.

    Existe porque errar o CRS produz um arquivo que abre, desenha e esta
    errado. Aconteceu comigo durante o estudo deste formato: adivinhei as
    colunas de um arquivo sem cabecalho e a camada saiu com latitude 283.

    Devolve lista de problemas — vazia quando esta tudo bem.
    """
    problemas = []
    if not esq.tem_coordenada:
        return ["Sem coordenada identificada."]

    cantos = [(extensao[0], extensao[1]), (extensao[2], extensao[3])]
    lonlat = [para_lonlat(esq, x, y) for x, y in cantos]
    if any(v is None for par in lonlat for v in par):
        return ["Nao consegui verificar a extensao para conferir o CRS."]

    lons = [p[0] for p in lonlat]
    lats = [p[1] for p in lonlat]
    o, l = min(lons), max(lons)
    s, n = min(lats), max(lats)

    if not (BRASIL[0] <= o and l <= BRASIL[2]
            and BRASIL[1] <= s and n <= BRASIL[3]):
        problemas.append(
            "A extensao convertida (%.2f,%.2f .. %.2f,%.2f) cai fora do "
            "Brasil. O CRS escolhido provavelmente esta errado." % (o, s, l, n))

    caixa = esq.caixa_esperada
    if caixa and not problemas:
        folga = 1.5       # grau; os leiames arredondam os limites
        if (l < caixa[0] - folga or o > caixa[2] + folga
                or n < caixa[1] - folga or s > caixa[3] + folga):
            problemas.append(
                "A extensao convertida (%.2f,%.2f .. %.2f,%.2f) nao encosta na "
                "area que o leiame declara (%.2f,%.2f .. %.2f,%.2f)."
                % (o, s, l, n, caixa[0], caixa[1], caixa[2], caixa[3]))
    return problemas


# ─── Conversao ───────────────────────────────────────────────────────────────

#: Quanto um ponto ocupa no arquivo de texto, medido no acervo: o Mag.XYZ do
#: projeto 3065 tem 570 MB para 3.153.422 pontos. Serve para estimar antes de
#: comecar, que e o que permite avisar "isto vai levar 21 minutos".
BYTES_POR_PONTO = 181

#: Pontos por segundo, medido convertendo esse mesmo arquivo com o GDAL do
#: QGIS 4.0.1.
#:
#: 52 mil/s para GeoPackage sem indice; 38,5 mil/s para GeoParquet com o
#: progresso ligado, que e o caminho que o usuario percorre de verdade. Fica o
#: numero menor: estimativa otimista faz o usuario achar que travou.
PONTOS_POR_SEGUNDO = 38_500

#: A cada quantos pontos a transacao e fechada. Transacao unica de 68 milhoes
#: de feicoes estoura a memoria; uma por feicao deixa a escrita lenta demais.
LOTE = 200_000

#: A cada quantos pontos o progresso e avisado.
#:
#: Separado do LOTE de proposito. A 53 mil pontos por segundo, avisar so a cada
#: transacao daria uma atualizacao a cada 4 segundos — e uma barra parada por 4
#: segundos passa a mesma impressao de travamento que ela existe para evitar.
#: Assim sao umas duas por segundo.
PASSO_PROGRESSO = 25_000


def estimar(bytes_do_arquivo):
    """(pontos, segundos) aproximados, para avisar antes de comecar."""
    pontos = max(1, int(bytes_do_arquivo / BYTES_POR_PONTO))
    return pontos, pontos / PONTOS_POR_SEGUNDO


def _campos_do_esquema(esq):
    """
    Nome e tipo de cada campo da tabela de saida.

    As colunas de coordenada viram reais mesmo quando no arquivo sao texto:
    no projeto 1009 elas sao "-15.27.08.20", e guardar a string crua obrigaria
    quem usa a tabela a repetir a conversao.
    """
    campos = []
    for i, nome in enumerate(esq.nomes):
        tipo = esq.tipos[i]
        if i in (esq.ix, esq.iy) and esq.forma == "gms":
            tipo = "real"
        campos.append((nome, tipo))
    return campos


def converter(abrir_texto, esq, destino, formato="Parquet",
              nome_camada="pontos", progresso=None, cancelado=None,
              tamanho_total=0):
    """
    Le o XYZ inteiro e grava uma tabela de pontos.

    `abrir_texto`   funcao sem argumentos que devolve um iteravel de linhas str
    `esq`           o Esquema devolvido por `analisar`
    `destino`       caminho do arquivo de saida
    `progresso`     funcao(fracao 0..1, pontos_gravados) — pode ser None
    `cancelado`     funcao() -> bool, consultada a cada lote

    As linhas de medida (Line) e as de controle (Tie) vao para a MESMA tabela,
    com a coluna `tipo_linha` dizendo qual e. Sao o mesmo levantamento; separa-
    las obrigaria a abrir duas camadas para ver um mapa so.

    O que NAO se junta e Mag com Gama. No projeto 3065 sao 3.153.422 contra
    315.339 pontos — exatamente 10:1, porque a amostragem e de 0,1 s contra
    1 s. Fundir produziria 90% de celulas vazias. Cada arquivo vira uma tabela.

    Devolve dict com n, extensao, cancelado e problemas.
    """
    from osgeo import ogr, osr

    if not esq.tem_coordenada:
        raise ValueError("esquema sem coordenada; nao ha o que converter")

    drv = ogr.GetDriverByName(formato)
    if drv is None:
        raise ValueError("driver %r indisponivel nesta instalacao" % formato)

    srs = osr.SpatialReference()
    if esq.crs.upper().startswith("EPSG:"):
        srs.ImportFromEPSG(int(esq.crs.split(":")[1]))
    else:
        srs.ImportFromProj4(esq.crs)

    ds = drv.CreateDataSource(str(destino))
    if ds is None:
        raise IOError("nao consegui criar %s" % destino)
    camada = ds.CreateLayer(nome_camada, srs, ogr.wkbPoint)

    for nome in ("linha", "tipo_linha", "voo", "data_voo"):
        camada.CreateField(ogr.FieldDefn(nome, ogr.OFTString))
    for nome, tipo in _campos_do_esquema(esq):
        camada.CreateField(ogr.FieldDefn(
            nome, ogr.OFTReal if tipo == "real" else ogr.OFTString))
    defn = camada.GetLayerDefn()
    base = 4                      # quantos campos vem antes das colunas

    ler_coord = ler_gms if esq.forma == "gms" else ler_numero
    n = 0
    bytes_lidos = 0
    linha_atual = tipo_atual = voo = data_voo = ""
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    foi_cancelado = False

    camada.StartTransaction()
    try:
        for bruto in abrir_texto():
            bytes_lidos += len(bruto)
            s = bruto.strip()
            if not s:
                continue
            if s.startswith("//"):
                m = RE_META.match(s)
                if m:
                    chave = m.group(1).lower()
                    if chave.startswith("flight"):
                        voo = m.group(2).strip()
                    elif chave.startswith("date"):
                        data_voo = m.group(2).strip()
                continue
            if s.startswith("/"):
                continue
            m = RE_ROTULO.match(s)
            if m:
                tipo_atual = m.group(1).lower()
                linha_atual = (m.group(2) or "").strip()
                continue

            partes = partir(s, esq.separador)
            if len(partes) != esq.n_colunas:
                continue          # linha truncada; nao inventamos valor
            x = ler_coord(partes[esq.ix])
            y = ler_coord(partes[esq.iy])
            if x is None or y is None:
                continue          # ponto sem posicao nao vira feicao

            f = ogr.Feature(defn)
            f.SetField(0, linha_atual)
            f.SetField(1, tipo_atual)
            f.SetField(2, voo)
            f.SetField(3, data_voo)
            for i, texto in enumerate(partes):
                if esq.tipos[i] == "real" or i in (esq.ix, esq.iy):
                    v = (x if i == esq.ix else
                         y if i == esq.iy else ler_numero(texto))
                    if v is not None:
                        f.SetField(base + i, v)
                elif texto != NULO:
                    f.SetField(base + i, texto)
            g = ogr.Geometry(ogr.wkbPoint)
            g.AddPoint_2D(x, y)
            f.SetGeometry(g)
            camada.CreateFeature(f)
            f = None

            n += 1
            if x < xmin:
                xmin = x
            if x > xmax:
                xmax = x
            if y < ymin:
                ymin = y
            if y > ymax:
                ymax = y

            if n % PASSO_PROGRESSO == 0:
                if progresso is not None:
                    fracao = (bytes_lidos / tamanho_total
                              if tamanho_total else 0.0)
                    progresso(min(fracao, 0.999), n)
                # Cancelar tambem e respondido aqui: esperar o fim da transacao
                # deixaria o botao levar ate 4 segundos para responder.
                if cancelado is not None and cancelado():
                    foi_cancelado = True
                    break
            if n % LOTE == 0:
                camada.CommitTransaction()
                camada.StartTransaction()
        # Uma unica saida, com ou sem cancelamento: fechar a transacao duas
        # vezes e erro no driver, e fechar zero vezes perde o ultimo lote.
        camada.CommitTransaction()
    finally:
        camada = None
        ds = None

    extensao = (xmin, ymin, xmax, ymax) if n else None
    return {"n": n,
            "extensao": extensao,
            "cancelado": foi_cancelado,
            "problemas": verificar(esq, extensao) if extensao else []}


# ─── Fuso deduzido, e o pacote como um todo ──────────────────────────────────

def _zona_de_um_par(amostra, i_este, i_lon):
    """
    O fuso UTM, a partir de uma linha que traz o este projetado e a longitude.

    Nao precisa de nenhum documento: a longitude diz o fuso, e o este confirma
    que a coluna e mesmo UTM. Confere em varias linhas e so aceita se todas
    concordarem — uma linha suja nao pode decidir o CRS do arquivo inteiro.
    """
    zonas = set()
    for partes in amostra.linhas[:200]:
        if i_este >= len(partes) or i_lon >= len(partes):
            continue
        este, lon = ler_numero(partes[i_este]), ler_numero(partes[i_lon])
        if este is None or lon is None:
            continue
        if not _e_este_utm(este, este) or not _e_longitude(lon, lon):
            continue
        z = int(math.floor((lon + 180) / 6.0)) + 1
        if 17 <= z <= 26:
            zonas.add(z)
    return zonas.pop() if len(zonas) == 1 else None


def completar_com_irmaos(esquemas):
    """
    Empresta o fuso entre arquivos do mesmo pacote.

    O 1114_Cruzamentos.XYZ tem X e Y e nenhuma declaracao de fuso; o
    1114_MagLine.XYZ, no mesmo ZIP, tem X, Y, LONGITUDE e LATITUDE. Um resolve
    o outro, e o pacote e a unidade certa para isso: sao o mesmo levantamento,
    voado no mesmo dia, processado junto.

    `esquemas` e uma lista de Esquema ja analisados. Altera no lugar e devolve
    quantos foram completados.
    """
    zonas = {e.zona_observada for e in esquemas if e.zona_observada}
    if len(zonas) != 1:
        return 0
    zona = zonas.pop()
    texto_datum = " ".join(" ".join(e.procedencia) for e in esquemas)
    n = 0
    for e in esquemas:
        if e.forma == "utm" and not e.crs:
            e.crs = epsg_utm(zona, texto_datum)
            e.anotar("CRS: %s — fuso %d emprestado de outro arquivo do mesmo "
                     "pacote, que traz UTM e longitude juntos." % (e.crs, zona))
            e.avisos = [a for a in e.avisos if "fuso nao esta declarado" not in a]
            if e.extensao_amostra:
                e.problemas = verificar(e, e.extensao_amostra)
            n += 1
    return n


# ─── O pacote inteiro ────────────────────────────────────────────────────────

#: Quantas linhas ler para decidir o esquema. O bastante para pegar a faixa de
#: valores de varias linhas de voo, barato o bastante para rodar em todos os
#: arquivos do pacote enquanto o usuario olha o dialogo.
LINHAS_DE_AMOSTRA = 4000

#: Leiames do SGB. O nome varia com a decada e com quem montou o pacote:
#: Readme.txt, readme.txt, LEIAME.TXT, Leia-me.pdf, pgbc.txt, carajas1.txt.
#: Ler todo .txt do pacote e mais simples e mais robusto que listar nomes.
LIMITE_AUXILIAR = 200_000


def texto_auxiliar_do_pacote(raiz):
    """Junta os .txt do pacote: e de onde saem o fuso e a caixa do leiame."""
    from .pacote import caminho_longo, sem_prefixo
    from pathlib import Path
    pedacos = []
    total = 0
    try:
        achados = sorted(Path(caminho_longo(sem_prefixo(raiz))).rglob("*"))
    except OSError:
        return ""
    for p in achados:
        if p.suffix.lower() != ".txt" or not p.is_file():
            continue
        try:
            bruto = p.open("rb").read(LIMITE_AUXILIAR)
        except OSError:
            continue
        # cp860 e o codepage DOS portugues, que e como o SGB gravou os leiames
        # dos anos 80; latin-1 nunca levanta e serve de rede.
        try:
            pedacos.append(bruto.decode("cp860"))
        except (UnicodeDecodeError, LookupError):
            pedacos.append(bruto.decode("latin-1", "replace"))
        total += len(bruto)
        if total > LIMITE_AUXILIAR:
            break
    return "\n".join(pedacos)


def arquivos_xyz(raiz):
    """Os .xyz do pacote, em ordem, com caminho seguro no Windows."""
    from .pacote import caminho_longo, sem_prefixo
    from pathlib import Path
    try:
        achados = sorted(Path(caminho_longo(sem_prefixo(raiz))).rglob("*"))
    except OSError:
        return []
    return [sem_prefixo(p) for p in achados
            if p.suffix.lower() == ".xyz" and p.is_file()]


def analisar_pacote(raiz):
    """
    Analisa todo .xyz de um pacote ja extraido.

    Devolve lista de Esquema, com `arquivo` preenchido e o fuso ja emprestado
    entre irmaos quando um deles sabe e o outro nao.
    """
    from .pacote import caminho_para_abrir
    auxiliar = texto_auxiliar_do_pacote(raiz)
    esquemas = []
    for caminho in arquivos_xyz(raiz):
        try:
            with open(caminho_para_abrir(caminho), "r",
                      encoding="latin-1") as fh:
                cabeca = [linha for _, linha in zip(range(LINHAS_DE_AMOSTRA), fh)]
        except OSError as e:
            esq = Esquema()
            esq.arquivo = str(caminho)
            esq.avisos.append("Nao consegui abrir o arquivo: %s" % e)
            esquemas.append(esq)
            continue
        esq = analisar(cabeca, nome_arquivo=caminho.name,
                       texto_auxiliar=auxiliar)
        esq.arquivo = str(caminho)
        esquemas.append(esq)
    completar_com_irmaos(esquemas)
    return esquemas


# ─── Nomes dos arquivos de saida ─────────────────────────────────────────────

#: Sufixo da tabela de pontos gerada a partir de um XYZ.
#:
#: Nao pode ser "_pontos.gpkg": esse e o `config.SUFIXO_PONTOS`, que
#: `listar_arquivos` IGNORA de proposito — e o nome que o plugin da ao
#: espacializar uma planilha de geoquimica, escondido para nao virar camada
#: repetida ao lado da tabela que o originou. Aqui a saida e o produto
#: principal e precisa aparecer.
SUFIXO_AQUISICAO = "_aquisicao"

#: Driver do OGR -> extensao. Fonte unica: o dialogo monta o seletor com isto,
#: e a tarefa limpa saidas antigas com isto.
FORMATOS_SAIDA = {"Parquet": ".parquet", "GPKG": ".gpkg"}


def caminho_de_saida(origem, formato="Parquet"):
    """Onde a tabela de pontos de `origem` e gravada, naquele formato."""
    from pathlib import Path
    origem = Path(origem)
    return origem.with_name(origem.stem + SUFIXO_AQUISICAO
                            + FORMATOS_SAIDA[formato])


def saidas_existentes(origem):
    """
    Toda saida ja gravada a partir de `origem`, em qualquer formato.

    Converter de novo escolhendo outro formato deixava a saida anterior na
    pasta: o projeto 1117 acabou com 1117_MagLine.XYZ (1,79 GB), o .parquet
    (460 MB) E o .gpkg (2,61 GB) — 5,3 GB, com os dois ultimos sendo o mesmo
    dado e aparecendo os dois como camada na hora de adicionar ao projeto.
    """
    from pathlib import Path
    achados = []
    for formato in FORMATOS_SAIDA:
        p = caminho_de_saida(origem, formato)
        try:
            if p.exists():
                achados.append(p)
        except OSError:
            pass
    return achados
