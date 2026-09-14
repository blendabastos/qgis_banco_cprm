#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gerar_catalogo.py — Extrai do catalogo.csv do projeto "Banco CPRM" a fatia que
o plugin precisa e grava comprimida em acervo_cprm/dados/catalogo_sig.csv.gz.

    python gerar_catalogo.py
    python gerar_catalogo.py --origem "..\\Banco CPRM\\catalogo.csv"

Por que so uma fatia: o catalogo completo tem 5.258 linhas e 35 colunas (5,3 MB).
O plugin usa 4.719 linhas e 12 colunas, que comprimidas dao 174 KB — cabe no
repositorio do plugin sem incomodar ninguem.

Esta e a UNICA ponte entre os dois projetos. O plugin nao importa codigo do
"Banco CPRM": o link de download ja vem verificado no catalogo, entao ele so
precisa baixar, descompactar e adicionar.
"""

import io
import sys
import csv
import gzip
import json
import argparse
import hashlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from acervo_cprm.config import TIPOS_INCLUIDOS   # noqa: E402

AQUI = Path(__file__).resolve().parent
ORIGEM_PADRAO = AQUI.parent / "Banco CPRM" / "catalogo.csv"
DESTINO = AQUI / "acervo_cprm" / "dados" / "catalogo_sig.csv.gz"
MANIFESTO = AQUI / "acervo_cprm" / "dados" / "catalogo_sig.json"

#: O catalogo COMPLETO, publicado na raiz do repositorio — e de onde o botao
#: "Atualizar catalogo" busca (ver config.PADROES["url_catalogo"]).
#:
#: Fica FORA de acervo_cprm/ de proposito: `empacotar.py` so varre essa pasta,
#: entao o arquivo nao entra no ZIP do plugin e nao paga 472 KB no pacote que
#: todo mundo instala. Quem clica em "atualizar" e que o baixa.
#:
#: Gerado aqui junto com o embutido para os dois nao divergirem: publicar um
#: catalogo enxuto novo e deixar o completo velho no repositorio faria o botao
#: "atualizar" ANDAR PARA TRAS, entregando menos camadas do que ja vinham.
COMPLETO = AQUI / "catalogo.csv.gz"

COLUNAS = [
    "id",             # ID no GEOSGB
    "titulo",         # como aparece no site
    "nivel_1", "nivel_2", "nivel_3", "nivel_4",   # hierarquia, para a arvore
    "tipo",           # ver TIPOS_GEOESPACIAIS
    "nome_arquivo",   # nome real no servidor, extensao ja corrigida
    "formato",
    "tamanho_bytes",
    "link_download",  # link direto, ja verificado
    "origem",         # rigeo | gd
]

#: Os tipos que entram no plugin: tudo que e DADO GEOESPACIAL.
#:
#: Nao e a mesma coisa que "o QGIS abre". Os XYZ dos projetos aerogeofisicos
#: (serie 1000/3000) sao formato Geosoft, com blocos "LI n" e sem cabecalho
#: delimitado — o QGIS nao le. Ainda assim precisam estar no catalogo: o
#: usuario baixa e abre no Oasis Montaj, ou converte. O plugin baixa e extrai
#: tudo; adicionar como camada e o que fica condicionado ao formato.
#:


def gerar(origem: Path, destino: Path, manifesto: Path) -> dict:
    with open(origem, encoding="utf-8-sig", newline="") as f:
        linhas = [r for r in csv.DictReader(f)
                  if r.get("status") == "ok"
                  and r.get("tipo") in TIPOS_INCLUIDOS]

    # Ordem estavel: a arvore do painel e montada nesta sequencia.
    linhas.sort(key=lambda r: (r["nivel_1"], r["nivel_2"], r["nivel_3"],
                               r["nivel_4"], r["titulo"]))

    destino.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUNAS, extrasaction="ignore",
                       lineterminator="\n")
    w.writeheader()
    for r in linhas:
        w.writerow({c: r.get(c, "") for c in COLUNAS})
    bruto = buf.getvalue().encode("utf-8")

    # mtime fixo: sem isso o .gz muda a cada execucao e polui o diff do git.
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(destino, "wb"),
                       compresslevel=9, mtime=0) as gz:
        gz.write(bruto)

    info = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "origem": str(origem),
        "total": len(linhas),
        "colunas": COLUNAS,
        "bytes_brutos": len(bruto),
        "bytes_comprimidos": destino.stat().st_size,
        "sha256": hashlib.sha256(bruto).hexdigest(),
        "tamanho_acervo_bytes": sum(int(r["tamanho_bytes"] or 0) for r in linhas),
        "por_tipo": {t: sum(1 for r in linhas if r["tipo"] == t)
                     for t in sorted(TIPOS_INCLUIDOS)},
    }
    manifesto.write_text(json.dumps(info, ensure_ascii=False, indent=1),
                         encoding="utf-8")
    info["bytes_completo"] = publicar_completo(origem, COMPLETO)
    return info


def publicar_completo(origem: Path, destino: Path) -> int:
    """
    Copia o catalogo completo, comprimido, para a raiz do repositorio.

    E o arquivo que o botao "Atualizar catalogo" busca. Vai comprimido porque
    sao 5,3 MB crus contra 472 KB — e quem usa este plugin costuma estar em
    campo, com franquia contada.

    Mesmo `mtime=0` do embutido: sem isso o .gz muda a cada execucao e suja o
    diff do git mesmo quando o catalogo nao mudou.
    """
    bruto = origem.read_bytes()
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(destino, "wb"),
                       compresslevel=9, mtime=0) as gz:
        gz.write(bruto)
    return destino.stat().st_size


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--origem", type=Path, default=ORIGEM_PADRAO)
    args = ap.parse_args()

    if not args.origem.exists():
        raise SystemExit(
            f"catalogo nao encontrado: {args.origem}\n"
            f"Gere-o antes com: python mapear.py && python tipos.py --aplicar")

    info = gerar(args.origem, DESTINO, MANIFESTO)
    print(f"{info['total']} camadas SIG")
    print(f"  {info['bytes_brutos']/1024:>8.0f} KB brutos")
    print(f"  {info['bytes_comprimidos']/1024:>8.0f} KB comprimidos -> {DESTINO.name}")
    print(f"  {info['bytes_completo']/1024:>8.0f} KB completo    -> {COMPLETO.name}")
    print(f"  acervo: {info['tamanho_acervo_bytes']/2**30:.1f} GB")


if __name__ == "__main__":
    main()
