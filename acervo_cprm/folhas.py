# -*- coding: utf-8 -*-
"""
folhas.py — Onde cada camada fica no mapa, deduzido do codigo da folha.

O catalogo do GEOSGB nao tem geometria. Conferido nas 35 colunas do catalogo
completo, inclusive as 23 que o plugin descarta: nao ha bounding box, nem
centroide, nem coordenada. O RiGeo e um DSpace — repositorio de documentos, nao
catalogo geoespacial —, entao nao ha o que extrair da API.

O que ha e o CODIGO DA FOLHA, e ele nao e rotulo arbitrario: o acervo e
indexado pela Carta Internacional ao Milionesimo, cuja malha e uma formula.
"SC.24" e a faixa 8S-12S no fuso -42..-36, e os sufixos cortam essa folha em
quadrantes ate a escala de 1:50.000.

O codigo de folha cobre 71,2% das 4.719 camadas do catalogo. A aerogeofisica
nao tem folha, tem PROJETO, e para ela a posicao vem de `projetos.py` — as duas
fontes somadas dao 76,8%:

    KML                        99,7%   folha
    Geofisica-Geotiff          90,1%   projeto + folha
    SIG (Vetores)              85,1%   folha
    Geofisica-XYZ              87,9%   projeto
    Mapa (PDF)                 76,4%   folha
    Geoquimica-XLSX            32,7%   folha
    LiDAR, ortofoto             0,0%   nao dizem onde ficam

O que sobra NAO tem caixa, e isso e dito em voz alta em vez de ser resolvido
por chute. Uma camada sem localizacao conhecida some do resultado quando o
filtro espacial esta ligado, e o painel informa quantas sumiram: filtro que
esconde dado em silencio e o oposto do que o resto do plugin faz.

Nao importa Qt nem qgis.core de proposito — a malha e aritmetica, e assim roda
em teste puro.
"""

import re

#: Faixas de latitude da CIM, de 4 graus cada, a partir do equador.
#: A = 0-4, B = 4-8, C = 8-12 ... I = 32-36. O hemisferio vem da letra N/S.
BANDAS = "ABCDEFGHIJKLMNOPQRSTUV"

#: Cada nivel de subdivisao: mapa do rotulo para (coluna, linha), mais quantas
#: colunas e linhas o nivel tem. A origem e sempre o canto NOROESTE.
#:
#: O 1:100.000 e o unico que nao e 2x2, e a conta decide qual: a folha de
#: 1:250.000 tem 1o30' de longitude por 1o de latitude, e cada folha de
#: 1:100.000 tem 30'x30'. Entao sao
#:
#:     1,5o / 30' = 3 COLUNAS      1,0o / 30' = 2 LINHAS
#:
#: e a numeracao corre em linha a partir do noroeste: I II III em cima,
#: IV V VI embaixo.
#:
#: Isto esteve 2x3 aqui, e o erro foi achado pelo uso, nao pelos testes.
#: Filtrando por Mage (RJ), o plugin trazia a folha Casimiro de Abreu
#: (SF.23-Z-B-III), que fica em Nova Friburgo, e escondia a Baia de Guanabara
#: (SF.23-Z-B-IV), que e a que cobre Mage. Com 2x3 a caixa saia 0,750 x 0,333
#: em vez de 0,500 x 0,500 — area quase igual, posicao trocada.
#:
#: Os dois testes que existiam passavam: um conferia a AREA somada das seis
#: (identica nos dois arranjos) e o outro as dimensoes, contra o numero que eu
#: mesmo tinha calculado da implementacao errada. Teste escrito a partir do
#: codigo confirma o codigo, nao a especificacao. O teste que vale agora fixa
#: 30'x30', que e o que a norma diz, e confere folha nomeada contra municipio
#: real.
NIVEIS = (
    ({"V": (0, 0), "X": (1, 0), "Y": (0, 1), "Z": (1, 1)}, 2, 2),          # 1:500k
    ({"A": (0, 0), "B": (1, 0), "C": (0, 1), "D": (1, 1)}, 2, 2),          # 1:250k
    ({"I": (0, 0), "II": (1, 0), "III": (2, 0),
      "IV": (0, 1), "V": (1, 1), "VI": (2, 1)}, 3, 2),                     # 1:100k
    ({"1": (0, 0), "2": (1, 0), "3": (0, 1), "4": (1, 1)}, 2, 2),          # 1:50k
    ({"NO": (0, 0), "NE": (1, 0), "SO": (0, 1), "SE": (1, 1)}, 2, 2),      # 1:25k
)

#: O codigo dentro de um titulo: "SIG (Vetores) - Aracaju SC.24",
#: "ARIM Serido: Folha Augusto Severo - SB.24-X-D-IV".
#:
#: O separador varia — ponto, hifen ou nada — e por isso e opcional em toda
#: parte. O `(?!\d)` no fim do par de digitos impede morder um numero maior:
#: sem ele, "SB.210" viraria fuso 21.
#:
#: O `(?![A-Za-z0-9])` depois de cada sufixo impede morder PALAVRA. Sem ele,
#: "Folha SC.24 Sergipe" virava "SC.24-SE" — o "Se" de Sergipe lido como o
#: quadrante sudeste de 1:25.000 — e a caixa saia 32 vezes menor que a folha
#: real, escondendo tudo que estava em volta. O mesmo acontecia com qualquer
#: titulo em que a folha fosse seguida de palavra comecando por SE, SO, NE, NO
#: ou I: "sem", "sobre", "norte".
#:
#: A ordem da alternancia tambem importa, e e do mais longo para o mais curto:
#: com "I" antes de "III", o motor casaria so o primeiro algarismo romano e
#: deixaria "II" para tras.
RE_CODIGO = re.compile(
    r"(?<![A-Za-z0-9])([NS][A-V])[.\-\s]?(\d{2})(?!\d)"
    r"((?:[.\-\s](?:NO|NE|SO|SE|VI|IV|III|II|I|V|X|Y|Z|[A-D]|[1-4])"
    r"(?![A-Za-z0-9]))*)",
    re.I)

#: Brasil continental com folga, para recusar caixa que caiu fora.
BRASIL = (-74.5, -34.0, -34.0, 6.5)


def codigo_do_texto(texto):
    """
    O codigo de folha dentro de um texto, normalizado, ou None.

    Devolve "SB.24-X-D-IV" para qualquer grafia de entrada. Normalizar aqui
    deixa `caixa` livre de lidar com as tres formas de separador.
    """
    m = RE_CODIGO.search(texto or "")
    if not m:
        return None
    banda, zona, resto = m.group(1).upper(), m.group(2), (m.group(3) or "")
    partes = [p for p in re.split(r"[.\-\s]+", resto.upper()) if p]
    return ".".join([banda, zona]) + ("-" + "-".join(partes) if partes else "")


def caixa(codigo):
    """
    A caixa de coordenadas da folha: (oeste, sul, leste, norte) em grau.

    Aritmetica pura, sem tabela: a malha da CIM e definida por formula. A folha
    de 1:1.000.000 tem 6 graus de longitude por 4 de latitude, e cada sufixo
    corta o que veio antes.

    Devolve None quando o codigo nao decodifica ou cai fora do Brasil — uma
    caixa errada e pior que caixa nenhuma, porque o filtro esconderia camada
    boa sem dizer por que.
    """
    if not codigo:
        return None
    partes = [p for p in re.split(r"[.\-\s]+", str(codigo).upper()) if p]
    if len(partes) < 2 or len(partes[0]) != 2:
        return None

    hemisferio, letra = partes[0][0], partes[0][1]
    if hemisferio not in "NS" or letra not in BANDAS:
        return None
    try:
        zona = int(partes[1])
    except ValueError:
        return None
    if not 1 <= zona <= 60:
        return None

    oeste = -180.0 + 6.0 * (zona - 1)
    leste = oeste + 6.0
    base = 4.0 * BANDAS.index(letra)
    if hemisferio == "S":
        norte, sul = -base, -base - 4.0
    else:
        sul, norte = base, base + 4.0

    for i, rotulo in enumerate(partes[2:]):
        if i >= len(NIVEIS):
            break                      # mais fundo que 1:25.000: para aqui
        mapa, colunas, linhas = NIVEIS[i]
        if rotulo not in mapa:
            break                      # sufixo estranho: vale o que ja se sabe
        cx, cy = mapa[rotulo]
        largura = (leste - oeste) / colunas
        altura = (norte - sul) / linhas
        oeste, leste = oeste + cx * largura, oeste + (cx + 1) * largura
        norte, sul = norte - cy * altura, norte - (cy + 1) * altura

    caixa_final = (oeste, sul, leste, norte)
    return caixa_final if cruza(caixa_final, BRASIL) else None


def _tabela_de_projetos():
    """
    A tabela de projetos aerogeofisicos, carregada uma vez por sessao.

    Preguicosa porque a maioria das camadas nao e aerogeofisica: quem so abre
    o painel e busca uma folha nunca paga a leitura.
    """
    global _PROJETOS
    if _PROJETOS is None:
        from . import projetos
        _PROJETOS = projetos.carregar()
    return _PROJETOS


_PROJETOS = None


def caixa_da_camada(camada):
    """
    A caixa de uma `Camada` do catalogo, ou None se ela nao disser onde fica.

    Duas fontes, nesta ordem:

    1. O NUMERO DE PROJETO no comeco do titulo ("1009-XYZ", "3065-Geotif"),
       contra a camada indice do SGB — ver projetos.py. Vem primeiro porque e
       area levantada de verdade, e nao uma folha inteira do IBGE em volta.
    2. O CODIGO DE FOLHA, no titulo ou nas pastas. O titulo costuma trazer, e
       quando nao traz, o nivel_3 ("Folha Aracaju - SC.24") traz.

    As duas se completam sem competir: um titulo de aerogeofisica nao tem
    codigo de folha, e um de carta geologica nao comeca com numero de projeto.

    O resultado fica guardado em `camada._caixa`, como `_busca` faz com o
    indice de texto: sao 4.719 camadas reexaminadas a cada mudanca de extensao,
    e as expressoes regulares nao podem rodar de novo a cada vez.
    """
    guardada = getattr(camada, "_caixa", False)
    if guardada is not False:
        return guardada

    from . import projetos
    achada = projetos.caixa_da_camada(camada, _tabela_de_projetos())
    if achada is None:
        for texto in (camada.titulo,) + tuple(camada.pastas):
            cod = codigo_do_texto(texto)
            if cod:
                achada = caixa(cod)
                if achada:
                    break
    try:
        camada._caixa = achada
    except AttributeError:
        pass          # objeto sem o slot (um duble de teste, por exemplo)
    return achada


def cruza(a, b):
    """
    As duas caixas se sobrepoem? Cada uma e (oeste, sul, leste, norte).

    Bordas contam como sobreposicao: a folha vizinha de quem esta exatamente
    na divisa interessa tanto quanto a de baixo do cursor.
    """
    if a is None or b is None:
        return False
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def folha_de(lon, lat):
    """
    A folha 1:1.000.000 que contem o ponto. Inversa de `caixa`.

    Nao e usada pelo filtro — esta aqui porque e o teste de ida e volta que
    prova a malha: gerar a folha a partir de uma coordenada conhecida e
    decodificar de volta tem que devolver uma caixa que contem o ponto.
    """
    import math
    zona = int(math.floor((lon + 180) / 6.0)) + 1
    indice = int(math.floor(abs(lat) / 4.0))
    if not (1 <= zona <= 60) or indice >= len(BANDAS):
        return None
    return "%s%s.%02d" % ("S" if lat < 0 else "N", BANDAS[indice], zona)


def separar_por_extensao(camadas, extensao):
    """
    Divide as camadas em (cruzam, fora, sem_caixa) para a extensao dada.

    Tres listas, e nao um filtro so, porque `sem_caixa` e informacao que o
    painel precisa mostrar: some do resultado, mas o usuario e avisado de
    quantas e por que.
    """
    cruzam, fora, sem_caixa = [], [], []
    for c in camadas:
        cx = caixa_da_camada(c)
        if cx is None:
            sem_caixa.append(c)
        elif cruza(cx, extensao):
            cruzam.append(c)
        else:
            fora.append(c)
    return cruzam, fora, sem_caixa
