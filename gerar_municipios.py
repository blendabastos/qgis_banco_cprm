#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_municipios.py — Tabela de municipios com caixa de coordenadas, do IBGE.

    python gerar_municipios.py

Grava acervo_cprm/dados/municipios.csv.gz: 5.571 municipios com nome, UF e
bounding box em grau decimal. Comprimido, sao ~100 KB.

RODA UMA VEZ, AQUI, e o resultado vai embutido no plugin. O plugin nao chama o
IBGE em tempo de execucao: a busca por cidade funciona offline, sem servico de
terceiro que possa sair do ar ou mudar de contrato. Essa e a unica razao pela
qual buscar cidade e aceitavel num plugin que, fora isso, so fala com o GEOSGB.

Duas rotas do IBGE, as duas publicas e sem chave:

  malhas v4     /malhas/paises/BR?intrarregiao=municipio&qualidade=minima
                Devolve a geometria de TODOS os municipios de uma vez —
                3,8 MB em 2,5 s. Pedir um por um seriam 5.571 requisicoes.
                A API nao publica bounding box; ela sai da geometria, aqui.

  localidades   /localidades/municipios
                O nome e a UF de cada codigo. A malha so traz `codarea`.

O `qualidade=minima` nao prejudica: a caixa de um poligono simplificado e a
mesma do detalhado a menos de alguns metros, e a caixa e para enquadrar o mapa,
nao para medir area.
"""

import io
import csv
import gzip
import json
import argparse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DESTINO = AQUI / "acervo_cprm" / "dados" / "municipios.csv.gz"

URL_MALHAS = ("https://servicodados.ibge.gov.br/api/v4/malhas/paises/BR"
              "?formato=application/vnd.geo+json&qualidade=minima"
              "&intrarregiao=municipio")
URL_LOCALIDADES = ("https://servicodados.ibge.gov.br/api/v1/localidades/"
                   "municipios")

COLUNAS = ["nome", "uf", "oeste", "sul", "leste", "norte"]


def baixar(url: str) -> bytes:
    """
    GET simples, aceitando gzip.

    A API de localidades responde comprimida quando se pede, e sao 2,4 MB
    contra algumas centenas de KB. `urlopen` nao descomprime sozinho.
    """
    pedido = urllib.request.Request(
        url, headers={"Accept-Encoding": "gzip",
                      "User-Agent": "acervo-cprm/gerador"})
    with urllib.request.urlopen(pedido, timeout=300) as resposta:
        dados = resposta.read()
    return gzip.decompress(dados) if dados[:2] == b"\x1f\x8b" else dados


def caixa_da_geometria(geom) -> tuple:
    """
    (oeste, sul, leste, norte) de qualquer geometria GeoJSON.

    Anda a arvore de coordenadas sem supor a profundidade: um municipio e
    Polygon, mas os que tem ilha sao MultiPolygon, com um nivel a mais.
    """
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


def sigla_da_uf(municipio: dict) -> str:
    """
    A UF de um municipio da API de localidades.

    Ha DUAS hierarquias na resposta, e um municipio traz uma ou outra: a
    antiga (microrregiao > mesorregiao > UF) e a divisao de 2017
    (regiao-imediata > regiao-intermediaria > UF). Ler so a primeira levanta
    TypeError nos municipios novos, porque `microrregiao` vem nulo.
    """
    caminhos = (("microrregiao", "mesorregiao", "UF", "sigla"),
                ("regiao-imediata", "regiao-intermediaria", "UF", "sigla"))
    for caminho in caminhos:
        no = municipio
        for chave in caminho:
            no = no.get(chave) if isinstance(no, dict) else None
            if no is None:
                break
        if no:
            return no
    return ""


def gerar(destino: Path) -> dict:
    malha = json.loads(baixar(URL_MALHAS).decode("utf-8"))
    caixas = {f["properties"]["codarea"]: caixa_da_geometria(f["geometry"])
              for f in malha["features"]}

    municipios = json.loads(baixar(URL_LOCALIDADES).decode("utf-8"))

    linhas, sem_malha, sem_uf = [], 0, 0
    for m in municipios:
        caixa = caixas.get(str(m["id"]))
        if caixa is None:
            sem_malha += 1
            continue
        uf = sigla_da_uf(m)
        if not uf:
            sem_uf += 1
        # Tres casas decimais sao ~100 m, de sobra para enquadrar o mapa, e
        # cortam a tabela quase pela metade contra as seis que a API devolve.
        linhas.append([m["nome"], uf] + ["%.3f" % v for v in caixa])

    if sem_malha:
        raise SystemExit("%d municipios sem malha; o IBGE mudou algo" % sem_malha)
    if sem_uf:
        raise SystemExit("%d municipios sem UF; ver sigla_da_uf" % sem_uf)

    buffer = io.StringIO()
    escritor = csv.writer(buffer, lineterminator="\n")
    escritor.writerow(COLUNAS)
    escritor.writerows(sorted(linhas))
    bruto = buffer.getvalue().encode("utf-8")

    destino.parent.mkdir(parents=True, exist_ok=True)
    # mtime fixo: sem isso o .gz muda a cada execucao e polui o diff do git
    # mesmo quando a tabela nao mudou. Mesma regra de gerar_catalogo.py.
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(destino, "wb"),
                       compresslevel=9, mtime=0) as gz:
        gz.write(bruto)

    return {"total": len(linhas), "bytes_brutos": len(bruto),
            "bytes_comprimidos": destino.stat().st_size}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--destino", type=Path, default=DESTINO)
    args = ap.parse_args()
    info = gerar(args.destino)
    print("%d municipios" % info["total"])
    print("  %6.0f KB brutos" % (info["bytes_brutos"] / 1024))
    print("  %6.0f KB comprimidos -> %s"
          % (info["bytes_comprimidos"] / 1024, args.destino.name))


if __name__ == "__main__":
    main()
