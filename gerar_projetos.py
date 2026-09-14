#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_projetos.py — Area dos projetos aerogeofisicos, do geoportal do SGB.

    python gerar_projetos.py

Grava acervo_cprm/dados/projetos.csv.gz: 376 projetos com numero, titulo e
caixa de coordenadas. Comprimido, sao ~9 KB.

FONTE OFICIAL, e isso importa por dois motivos. Primeiro, procedencia: o
servico declara `copyrightText` como "Servico Geologico do Brasil - SGB -
CPRM", que e o mesmo orgao dono do acervo que o plugin baixa. Segundo,
reprodutibilidade: qualquer pessoa que clone o repositorio regenera a tabela
sem precisar de arquivo nenhum em disco.

    https://geoportal.sgb.gov.br/server/rest/services/
        geofisica/aerogeofisica/MapServer

Sao quatro camadas, uma por serie de projeto:

    0   Serie 1000 - Projetos DNPM e CPRM                  137
    1   Serie 2000 - Projetos CNEM e NUCLEBRAS              33
    2   Serie 3000 - Projetos governamentais e privados     93
    3   Serie 4000 - Projetos CNP e PETROBRAS              117

POR QUE ISTO EXISTE. O filtro espacial deduz a posicao do codigo de folha do
IBGE (ver folhas.py), e isso cobre 71% do acervo — mas zero por cento da
aerogeofisica, indexada por PROJETO e nao por folha: os titulos sao "1009-XYZ",
"3065-Geotif". Com esta tabela, `Geofisica-XYZ` sai de 0% para 85% e
`Geofisica-Geotiff` de 32% para 90%.

A CHAVE E `ID_PROJETO` SOZINHO. Parece obvio depois, mas `ID_SERIE` vale 1000 e
`ID_PROJETO` vale "1060" — a serie ja esta dentro do numero. Somar os dois
casava com nada, e foi assim que a primeira tentativa devolveu zero de 141.
"""

import io
import csv
import gzip
import json
import argparse
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DESTINO = AQUI / "acervo_cprm" / "dados" / "projetos.csv.gz"

SERVICO = ("https://geoportal.sgb.gov.br/server/rest/services/"
           "geofisica/aerogeofisica/MapServer")
CAMADAS = (0, 1, 2, 3)          # series 1000, 2000, 3000 e 4000

COLUNAS = ["numero", "titulo", "oeste", "sul", "leste", "norte"]

#: Brasil continental com folga, para recusar poligono absurdo.
BRASIL = (-74.5, -34.0, -34.0, 6.5)


def consultar(camada: int) -> list:
    """
    As feicoes de uma camada do servico, em GeoJSON.

    `outSR=4326` e explicito: o servico ja publica em 4326, mas pedir e barato
    e a comparacao do filtro e em grau — receber metros sem perceber daria uma
    tabela inteira errada, calada.

    `maxRecordCount` do servico e 1000 e a maior camada tem 137 feicoes, entao
    uma consulta basta. Se o SGB publicar mais de mil projetos de uma serie,
    esta funcao passa a truncar — e o teste de contagem no fim acusa.
    """
    parametros = urllib.parse.urlencode({
        "where": "1=1",
        "outFields": "ID_PROJETO,ID_SERIE,TITULO",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    })
    url = "%s/%d/query?%s" % (SERVICO, camada, parametros)
    pedido = urllib.request.Request(
        url, headers={"User-Agent": "acervo-cprm/gerador"})
    with urllib.request.urlopen(pedido, timeout=180) as resposta:
        dados = json.loads(resposta.read().decode("utf-8"))
    return dados.get("features", [])


def caixa_da_geometria(geom) -> tuple:
    """(oeste, sul, leste, norte) de qualquer geometria GeoJSON."""
    xs, ys = [], []

    def andar(coords):
        if coords and isinstance(coords[0], (int, float)):
            xs.append(coords[0])
            ys.append(coords[1])
            return
        for parte in coords:
            andar(parte)

    andar(geom["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def dentro_do_brasil(caixa) -> bool:
    return not (caixa[2] < BRASIL[0] or caixa[0] > BRASIL[2]
                or caixa[3] < BRASIL[1] or caixa[1] > BRASIL[3])


def coletar() -> dict:
    """
    {numero: (caixa, titulo)} juntando as quatro series.

    Um projeto pode ter mais de um poligono — area principal mais uma extensao
    voada depois. Nesse caso as caixas sao UNIDAS: o que interessa ao filtro e
    "este projeto alcanca este lugar?".
    """
    achados = {}
    for camada in CAMADAS:
        for feicao in consultar(camada):
            propriedades = feicao.get("properties") or {}
            geom = feicao.get("geometry")
            if not geom:
                continue
            try:
                numero = int(str(propriedades.get("ID_PROJETO")).strip())
            except (TypeError, ValueError):
                continue
            caixa = caixa_da_geometria(geom)
            titulo = (propriedades.get("TITULO") or "").strip()
            if numero in achados:
                anterior, titulo_anterior = achados[numero]
                caixa = (min(anterior[0], caixa[0]), min(anterior[1], caixa[1]),
                         max(anterior[2], caixa[2]), max(anterior[3], caixa[3]))
                titulo = titulo or titulo_anterior
            achados[numero] = (caixa, titulo)
    return achados


def gerar(destino: Path) -> dict:
    indice = coletar()
    linhas, recusados = [], []
    for numero, (caixa, titulo) in sorted(indice.items()):
        if not dentro_do_brasil(caixa) or caixa[0] >= caixa[2] \
                or caixa[1] >= caixa[3]:
            recusados.append(numero)
            continue
        # Tres casas sao ~100 m. A caixa serve para perguntar "cruza?", e o
        # proprio poligono ja e uma aproximacao da area voada.
        linhas.append([str(numero), titulo] + ["%.3f" % v for v in caixa])

    if len(linhas) < 300:
        raise SystemExit("so %d projetos; o servico do SGB mudou algo"
                         % len(linhas))

    buffer = io.StringIO()
    escritor = csv.writer(buffer, lineterminator="\n")
    escritor.writerow(COLUNAS)
    escritor.writerows(linhas)
    bruto = buffer.getvalue().encode("utf-8")

    destino.parent.mkdir(parents=True, exist_ok=True)
    # mtime fixo, como nos outros geradores: sem isso o .gz muda a cada
    # execucao e suja o diff do git mesmo sem mudanca de conteudo.
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(destino, "wb"),
                       compresslevel=9, mtime=0) as gz:
        gz.write(bruto)

    return {"total": len(linhas), "recusados": recusados,
            "bytes_comprimidos": destino.stat().st_size}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--destino", type=Path, default=DESTINO)
    args = ap.parse_args()
    info = gerar(args.destino)
    print("%d projetos aerogeofisicos" % info["total"])
    if info["recusados"]:
        print("  recusados (fora do Brasil ou caixa degenerada): %s"
              % info["recusados"])
    print("  %.0f KB -> %s" % (info["bytes_comprimidos"] / 1024,
                               args.destino.name))


if __name__ == "__main__":
    main()
