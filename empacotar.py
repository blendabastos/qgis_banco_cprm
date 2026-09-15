#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
empacotar.py — Gera o ZIP instalavel e, opcionalmente, instala no perfil local.

    python empacotar.py                # gera dist/acervo_cprm-<versao>.zip
    python empacotar.py --instalar     # tambem copia para o perfil do QGIS
    python empacotar.py --instalar --perfil default

O ZIP segue o formato que o Gerenciador de Complementos espera: uma unica pasta
de primeiro nivel com o nome do plugin.
"""

import re
import shutil
import zipfile
import argparse
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PLUGIN = AQUI / "acervo_cprm"
DIST = AQUI / "dist"

#: Nao vao para o ZIP: lixo de execucao e arquivos de desenvolvimento.
IGNORAR_PASTAS = {"__pycache__", ".git", ".pytest_cache"}
IGNORAR_SUFIXOS = {".pyc", ".pyo", ".orig", ".rej"}

#: Manifesto que `gerar_catalogo.py` escreve para conferencia no repositorio.
#: O plugin nunca le, e ele traz o caminho da maquina que gerou o catalogo.
IGNORAR_NOMES = {"catalogo_sig.json"}


def versao() -> str:
    texto = (PLUGIN / "metadata.txt").read_text(encoding="utf-8")
    m = re.search(r"^version\s*=\s*(.+)$", texto, re.M)
    return m.group(1).strip() if m else "0.0.0"


def arquivos():
    for p in sorted(PLUGIN.rglob("*")):
        if not p.is_file():
            continue
        if any(parte in IGNORAR_PASTAS for parte in p.parts):
            continue
        if p.suffix.lower() in IGNORAR_SUFIXOS or p.name in IGNORAR_NOMES:
            continue
        yield p


def conferir():
    """Falta de um destes so apareceria como plugin quebrado dentro do QGIS."""
    faltando = [n for n in ("__init__.py", "metadata.txt", "plugin.py",
                            "dados/catalogo_sig.csv.gz")
                if not (PLUGIN / n).exists()]
    if faltando:
        raise SystemExit("faltando no plugin: " + ", ".join(faltando))


def empacotar() -> Path:
    conferir()
    DIST.mkdir(exist_ok=True)
    alvo = DIST / f"acervo_cprm-{versao()}.zip"
    with zipfile.ZipFile(alvo, "w", zipfile.ZIP_DEFLATED) as z:
        for p in arquivos():
            z.write(p, Path("acervo_cprm") / p.relative_to(PLUGIN))
    return alvo


def perfis_qgis():
    import os
    base = Path(os.environ.get("APPDATA", Path.home())) / "QGIS"
    for versao_qgis in ("QGIS4", "QGIS3"):
        raiz = base / versao_qgis / "profiles"
        if raiz.is_dir():
            for p in raiz.iterdir():
                if p.is_dir():
                    yield versao_qgis, p


def instalar(perfil_desejado: str = "default"):
    alvos = [p for v, p in perfis_qgis()
             if v == "QGIS4" and p.name == perfil_desejado]
    if not alvos:
        disponiveis = ", ".join(f"{v}/{p.name}" for v, p in perfis_qgis())
        raise SystemExit(f"perfil QGIS4/{perfil_desejado} nao encontrado. "
                         f"Disponiveis: {disponiveis or 'nenhum'}")

    destino = alvos[0] / "python" / "plugins" / "acervo_cprm"
    if destino.exists():
        # Apaga tudo, inclusive __pycache__: bytecode de uma versao anterior
        # ao lado de fonte nova e fonte de confusao dificil de diagnosticar.
        shutil.rmtree(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    for p in arquivos():
        alvo = destino / p.relative_to(PLUGIN)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, alvo)
    return destino


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instalar", action="store_true",
                    help="copia para o perfil do QGIS 4")
    ap.add_argument("--perfil", default="default")
    args = ap.parse_args()

    z = empacotar()
    print(f"ZIP: {z}  ({z.stat().st_size/1024:.0f} KB)")

    if args.instalar:
        destino = instalar(args.perfil)
        print(f"instalado em: {destino}")
        print("\nNo QGIS: Complementos > Gerenciar e Instalar Complementos >")
        print("  Instalados > marque 'Acervo SIG - CPRM'")
        print("  (se ja estava carregado, use o plugin Plugin Reloader)")


if __name__ == "__main__":
    main()
