# -*- coding: utf-8 -*-
"""
alfa.py — Tira a moldura branca dos GeoTIFF aerogeofisicos.

Os GeoTIFF da geofisica do SGB sao imagens ja coloridas, nao grades: 3 bandas
RGB de 8 bits, sem nodata, sem mascara e sem alfa. Medido nos 19 arquivos dos
projetos 1017 e 1030, o fundo ocupa de 33% a 49% da imagem — e aparece no QGIS
como um retangulo branco cobrindo o mapa embaixo.

A correcao e uma quarta banda, a de alfa, que todo software GIS entende.

O QUE **NAO** FUNCIONA e dizer "branco e fundo". Numa composicao ternaria,
branco significa K, Th e U altos ao mesmo tempo — e dado, e dos bons. Rotulando
os componentes conexos do branco nos 19 arquivos:

    15 arquivos      o branco e UM componente so, encostando na moldura
    1017_TERNARIO    24 ilhas de branco cercadas por dado, 3.231 px
    1030_TERNARIO    49 ilhas, 700 px
    1017_1DV/ASA/MAG  4 ilhas, 108 px

Tratar cor como fundo furaria o mapa exatamente em cima das anomalias. Entao a
regra e outra: **e fundo o branco que alcanca a moldura**. Preenchimento a
partir da borda, nao comparacao de cor.

Custo medido, com o GDAL do QGIS 4.0.1:

    1030_CT.tif        1,3 MB -> 0,3 MB   em 0,1 s
    1017_TERNARIO.tif  2,1 MB -> 0,5 MB   em 0,3 s

O arquivo ENCOLHE: DEFLATE com preditor ganha do PACKBITS original com sobra,
mesmo carregando uma banda a mais. As bandas RGB saem byte a byte identicas, e
a georreferencia e a projecao tambem.
"""

import os
from pathlib import Path

from .pacote import caminho_para_abrir, caminho_longo, sem_prefixo

#: Cor do fundo nos mapas do SGB. A compressao original e PACKBITS, sem perdas,
#: entao o valor chega exato — nao ha artefato para tolerar.
BRANCO = 255

#: Como gravar. TILED e DEFLATE com preditor horizontal: e o que faz o arquivo
#: sair menor que o original mesmo com a banda a mais.
OPCOES = ["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES", "BIGTIFF=IF_SAFER"]

#: Acima disto nao mexemos, e o numero vem de uma conta de memoria.
#:
#: O preenchimento precisa da imagem inteira: nao da para decidir se um branco
#: alcanca a moldura olhando um pedaco. Por pixel gastamos 6 bytes — 3 do RGB
#: lido, mais tres mascaras de 1 byte (branco, fundo, alfa). A 60 milhoes de
#: pixels sao uns 360 MB, que e o teto que aceito pedir dentro do processo do
#: QGIS, onde o usuario tem os proprios projetos abertos.
#:
#: Para referencia, os GeoTIFF medidos tem 1,4 milhao de pixels — quarenta
#: vezes abaixo do limite. Um raster maior que isto sai com a moldura branca
#: em vez de arriscar derrubar o QGIS por falta de memoria.
LIMITE_PIXELS = 60_000_000


def precisa_de_alfa(caminho) -> bool:
    """
    True se vale a pena mexer: GeoTIFF RGB de 8 bits, sem alfa, com fundo branco.

    Barato de responder — le so os metadados e o canto da imagem.
    """
    from osgeo import gdal
    try:
        ds = gdal.Open(caminho_para_abrir(caminho))
    except Exception:
        return False
    if ds is None:
        return False
    try:
        if ds.RasterCount != 3:
            return False              # ja tem alfa, ou nao e RGB
        if any(ds.GetRasterBand(i + 1).DataType != gdal.GDT_Byte
               for i in range(3)):
            return False
        if any(ds.GetRasterBand(i + 1).GetNoDataValue() is not None
               for i in range(3)):
            return False              # o arquivo ja declara o fundo
        if ds.RasterXSize * ds.RasterYSize > LIMITE_PIXELS:
            return False
        canto = ds.ReadAsArray(0, 0, 1, 1)
        return bool((canto[:, 0, 0] == BRANCO).all())
    finally:
        ds = None


def fundo_alcancavel(branco):
    """
    Quais pixels brancos alcancam a moldura, por vizinhanca de 4.

    Preenchimento por faixas horizontais, em numpy puro. `scipy.ndimage.label`
    resolveria em uma linha, mas nem toda instalacao do QGIS traz scipy, e o
    plugin nao tem dependencia externa nenhuma — nao vai ganhar uma agora.

    Vizinhanca de 4, nao de 8, de proposito: o fundo nao atravessa um encontro
    diagonal de um pixel. Na duvida o pixel continua opaco, que e o erro cujo
    custo e menor — deixar um ponto branco a mais e visivel e corrigivel; furar
    o dado passa despercebido.
    """
    import numpy as np

    h, w = branco.shape
    visto = np.zeros((h, w), dtype=bool)

    def inicios_de_faixa(linha_bool, desde, ate):
        """Onde comeca cada sequencia de True dentro de [desde, ate)."""
        trecho = linha_bool[desde:ate]
        if not trecho.any():
            return ()
        anterior = np.concatenate(([False], trecho[:-1]))
        return np.flatnonzero(trecho & ~anterior) + desde

    pilha = []
    for x in inicios_de_faixa(branco[0], 0, w):
        pilha.append((0, int(x)))
    if h > 1:
        for x in inicios_de_faixa(branco[h - 1], 0, w):
            pilha.append((h - 1, int(x)))
    for y in range(h):
        if branco[y, 0]:
            pilha.append((y, 0))
        if w > 1 and branco[y, w - 1]:
            pilha.append((y, w - 1))

    while pilha:
        y, x = pilha.pop()
        if visto[y, x] or not branco[y, x]:
            continue
        linha = branco[y]
        inicio = x
        while inicio > 0 and linha[inicio - 1] and not visto[y, inicio - 1]:
            inicio -= 1
        fim = x
        while fim < w - 1 and linha[fim + 1] and not visto[y, fim + 1]:
            fim += 1
        visto[y, inicio:fim + 1] = True
        for vizinha in (y - 1, y + 1):
            if 0 <= vizinha < h:
                livre = branco[vizinha] & ~visto[vizinha]
                for nx in inicios_de_faixa(livre, inicio, fim + 1):
                    pilha.append((vizinha, int(nx)))
    return visto


def aplicar(caminho) -> bool:
    """
    Acrescenta a banda alfa ao GeoTIFF, no lugar.

    Grava ao lado e so entao substitui: uma falha no meio nao pode deixar o
    usuario sem o arquivo que ele baixou. Devolve True se mexeu.
    """
    import numpy as np
    from osgeo import gdal

    caminho = sem_prefixo(Path(caminho))
    if not precisa_de_alfa(caminho):
        return False

    ds = gdal.Open(caminho_para_abrir(caminho))
    dados = ds.ReadAsArray()
    branco = ((dados[0] == BRANCO) & (dados[1] == BRANCO)
              & (dados[2] == BRANCO))
    if not branco.any():
        ds = None
        return False

    fundo = fundo_alcancavel(branco)
    if not fundo.any():
        ds = None
        return False
    alfa = np.where(fundo, 0, 255).astype(np.uint8)

    temporario = caminho.with_name(caminho.name + ".alfa.tmp")
    drv = gdal.GetDriverByName("GTiff")
    saida = drv.Create(caminho_para_abrir(temporario),
                       ds.RasterXSize, ds.RasterYSize, 4, gdal.GDT_Byte,
                       options=OPCOES)
    saida.SetGeoTransform(ds.GetGeoTransform())
    saida.SetProjection(ds.GetProjection())
    cores = (gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand)
    for i in range(3):
        banda = saida.GetRasterBand(i + 1)
        banda.WriteArray(dados[i])
        banda.SetColorInterpretation(cores[i])
    banda_alfa = saida.GetRasterBand(4)
    banda_alfa.WriteArray(alfa)
    banda_alfa.SetColorInterpretation(gdal.GCI_AlphaBand)
    saida.FlushCache()
    saida = None
    ds = None

    try:
        os.replace(caminho_longo(temporario), caminho_longo(caminho))
    except OSError:
        try:
            os.remove(caminho_longo(temporario))
        except OSError:
            pass
        raise
    return True


def aplicar_na_pasta(raiz, progresso=None, cancelado=None) -> int:
    """
    Aplica a todo GeoTIFF da pasta que precisar. Devolve quantos mudaram.

    Nunca levanta por causa de um arquivo: um TIFF estranho no meio do pacote
    nao pode impedir os outros dezesseis de ficarem utilizaveis.
    """
    alvos = [p for p in sorted(Path(caminho_longo(sem_prefixo(raiz))).rglob("*"))
             if p.suffix.lower() in (".tif", ".tiff")]
    mexidos = 0
    for i, p in enumerate(alvos):
        if cancelado is not None and cancelado():
            break
        try:
            if aplicar(sem_prefixo(p)):
                mexidos += 1
        except Exception:                            # noqa: BLE001
            pass
        if progresso is not None:
            progresso(i + 1, len(alvos))
    return mexidos
