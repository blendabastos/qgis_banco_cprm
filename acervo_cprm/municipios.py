# -*- coding: utf-8 -*-
"""
municipios.py — Busca por cidade, offline.

5.571 municipios com nome, UF e caixa de coordenadas, embutidos em
dados/municipios.csv.gz (101 KB). Gerados por `gerar_municipios.py` a partir
de duas rotas publicas do IBGE — as malhas v4 e a API de localidades.

A TABELA E EMBUTIDA, e isso e a decisao inteira. O plugin nao chama o IBGE em
tempo de execucao: buscar "Parauapebas" funciona sem rede, num levantamento de
campo, e nao depende de um servico que pode mudar de contrato ou sair do ar.
Fora daqui, o plugin so fala com o GEOSGB, e assim continua.

Nao importa Qt nem qgis.core: a busca e comparacao de texto e a caixa e uma
tupla de quatro numeros.
"""

import csv
import gzip
import io
from pathlib import Path

from .catalogo import sem_acento

DADOS = Path(__file__).resolve().parent / "dados"
EMBUTIDO = DADOS / "municipios.csv.gz"

#: Quanto folgar em volta do municipio ao enquadrar o mapa.
#:
#: Sem folga, o municipio encosta nas quatro bordas da tela e nao se ve o que
#: ha em volta — e o que ha em volta e justamente o que o filtro vai mostrar,
#: porque a folha do acervo e muito maior que qualquer municipio.
FOLGA = 0.12

#: Teto do que o completador oferece. Buscar "santa" casa 200 e poucos nomes, e
#: uma lista desse tamanho nao ajuda ninguem a escolher.
LIMITE_SUGESTOES = 40


class Municipio:
    """Um municipio: nome, UF e a caixa que o contem."""

    __slots__ = ("nome", "uf", "caixa", "_busca")

    def __init__(self, nome, uf, caixa):
        self.nome = nome
        self.uf = uf
        self.caixa = caixa
        self._busca = sem_acento(nome)

    @property
    def rotulo(self) -> str:
        """Como aparece na lista: 'Parauapebas — PA'."""
        return "%s — %s" % (self.nome, self.uf) if self.uf else self.nome

    def __repr__(self):
        return "<Municipio %s/%s>" % (self.nome, self.uf)


def carregar(caminho: Path = None) -> list:
    """
    Le a tabela embutida. Lista vazia se ela faltar ou nao servir.

    Vazio em vez de excecao de proposito: sem a tabela o plugin perde a busca
    por cidade e mantem todo o resto. Derrubar o painel inteiro por causa de um
    arquivo de conveniencia seria desproporcional.
    """
    caminho = Path(caminho) if caminho else EMBUTIDO
    try:
        bruto = caminho.read_bytes()
        if bruto[:2] == b"\x1f\x8b":
            bruto = gzip.decompress(bruto)
        leitor = csv.DictReader(io.StringIO(bruto.decode("utf-8-sig")))
        saida = []
        for linha in leitor:
            try:
                caixa = (float(linha["oeste"]), float(linha["sul"]),
                         float(linha["leste"]), float(linha["norte"]))
            except (TypeError, ValueError, KeyError):
                continue
            saida.append(Municipio((linha.get("nome") or "").strip(),
                                   (linha.get("uf") or "").strip(), caixa))
        return saida
    except Exception:                                   # noqa: BLE001
        return []


def procurar(municipios, termo: str, limite: int = LIMITE_SUGESTOES) -> list:
    """
    Os municipios cujo nome casa com o termo, sem acento e sem caixa.

    Quem comeca com o termo vem antes de quem apenas o contem: digitando
    "belo", "Belo Horizonte" tem que aparecer acima de "Formoso do Araguaia".
    Dentro de cada grupo a ordem e alfabetica, que e como se procura numa lista.
    """
    termo = sem_acento((termo or "").strip())
    if not termo:
        return []
    comeca, contem = [], []
    for m in municipios:
        if m._busca.startswith(termo):
            comeca.append(m)
        elif termo in m._busca:
            contem.append(m)
    comeca.sort(key=lambda m: (m.nome, m.uf))
    contem.sort(key=lambda m: (m.nome, m.uf))
    return (comeca + contem)[:limite]


def por_rotulo(municipios, rotulo: str):
    """
    O municipio de um rotulo exato ('Parauapebas — PA'), ou None.

    Existe porque 232 nomes se repetem entre estados. O rotulo com a UF e o
    unico identificador que o usuario ve e que nao e ambiguo — sem ele,
    escolher "Bom Jesus" na lista nao diria a qual dos varios o mapa iria.
    """
    alvo = (rotulo or "").strip()
    for m in municipios:
        if m.rotulo == alvo:
            return m
    # Sem UF no texto: aceita o nome cru quando ele for unico.
    iguais = [m for m in municipios
              if sem_acento(m.nome) == sem_acento(alvo)]
    return iguais[0] if len(iguais) == 1 else None


def com_folga(caixa, folga: float = FOLGA) -> tuple:
    """
    Afasta as bordas da caixa, em fracao do proprio tamanho.

    Um municipio pequeno enquadrado justo daria uma tela de poucos quilometros,
    e a folha do acervo que o contem tem 6 graus — o filtro mostraria a folha,
    mas nada do contexto. A folga tem um minimo absoluto para que municipio
    minusculo nao produza uma janela microscopica.
    """
    oeste, sul, leste, norte = caixa
    dx = max((leste - oeste) * folga, 0.02)
    dy = max((norte - sul) * folga, 0.02)
    return (oeste - dx, sul - dy, leste + dx, norte + dy)
