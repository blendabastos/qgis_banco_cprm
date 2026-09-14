# -*- coding: utf-8 -*-
"""
projetos.py — Onde ficam os projetos aerogeofisicos, pelo geoportal do SGB.

O filtro espacial deduz a posicao do codigo de folha do IBGE (ver folhas.py), e
isso cobre 71,2% do acervo — mas cobria ZERO por cento da aerogeofisica. Ela
sao indexados por PROJETO, nao por folha: os titulos sao "1009-XYZ",
"3065-Geotif", um numero e nao uma carta.

Esta tabela fecha a lacuna. 376 projetos com a caixa de coordenadas, do
geoportal oficial do SGB, coletados por `gerar_projetos.py`:

    https://geoportal.sgb.gov.br/server/rest/services/
        geofisica/aerogeofisica/MapServer

Medido no catalogo, somando com o codigo de folha:

    Geofisica-XYZ        141 camadas ->  124 com posicao (87,9%, era 0%)
    Geofisica-Geotiff    243 camadas ->  219 com posicao (90,1%, era 32,5%)

Sao 9 KB comprimidos, e com eles o XYZ deixa de ser o unico tipo do acervo
invisivel ao filtro.

Como o resto do nucleo, nao importa Qt: e um CSV e uma comparacao de numero.
"""

import csv
import gzip
import io
import re
from pathlib import Path

DADOS = Path(__file__).resolve().parent / "dados"
EMBUTIDO = DADOS / "projetos.csv.gz"

#: O numero do projeto no comeco do titulo: "1009-XYZ", "3065-Geotif".
#:
#: Ancorado no inicio de proposito. Solto, casaria com qualquer numero de
#: quatro digitos no meio de um titulo — um ano, por exemplo: "Carta Geologica
#: ... (2020)" viraria projeto 2020, e a camada iria parar em outro estado.
RE_NUMERO = re.compile(r"^\s*(\d{4})\s*-")


class Projeto:
    """Um projeto aerogeofisico: numero, titulo e a area levantada."""

    __slots__ = ("numero", "titulo", "caixa")

    def __init__(self, numero, titulo, caixa):
        self.numero = numero
        self.titulo = titulo
        self.caixa = caixa

    def __repr__(self):
        return "<Projeto %d %s>" % (self.numero, self.titulo[:30])


def carregar(caminho: Path = None) -> dict:
    """
    {numero: Projeto}. Dicionario vazio se a tabela faltar ou nao servir.

    Vazio em vez de excecao: sem ela o filtro volta a ignorar a aerogeofisica
    e todo o resto do plugin segue igual.
    """
    caminho = Path(caminho) if caminho else EMBUTIDO
    try:
        bruto = caminho.read_bytes()
        if bruto[:2] == b"\x1f\x8b":
            bruto = gzip.decompress(bruto)
        saida = {}
        for linha in csv.DictReader(io.StringIO(bruto.decode("utf-8-sig"))):
            try:
                numero = int(linha["numero"])
                caixa = (float(linha["oeste"]), float(linha["sul"]),
                         float(linha["leste"]), float(linha["norte"]))
            except (TypeError, ValueError, KeyError):
                continue
            saida[numero] = Projeto(numero, (linha.get("titulo") or "").strip(),
                                    caixa)
        return saida
    except Exception:                                   # noqa: BLE001
        return {}


def numero_do_texto(texto: str):
    """O numero de projeto no comeco de um titulo, ou None."""
    m = RE_NUMERO.match(texto or "")
    return int(m.group(1)) if m else None


def caixa_da_camada(camada, tabela) -> tuple:
    """
    A caixa de uma `Camada` cujo titulo comeca com numero de projeto, ou None.

    So olha o TITULO, nunca as pastas. As pastas de aerogeofisica sao coisas
    como "Projetos Aerogeofisicos (XYZ e Geotif)", sem numero — e procurar numa
    pasta generica so criaria chance de casar numero que nao e de projeto.
    """
    if not tabela:
        return None
    numero = numero_do_texto(getattr(camada, "titulo", ""))
    if numero is None:
        return None
    projeto = tabela.get(numero)
    return projeto.caixa if projeto else None
