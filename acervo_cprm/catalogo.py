# -*- coding: utf-8 -*-
"""
catalogo.py — Leitura do catalogo de camadas SIG e montagem da arvore.

Nao importa nada de Qt nem do QGIS de proposito: assim roda em teste puro,
sem subir interface. O painel consome `Camada` e `No`; a origem dos dados
(arquivo embutido ou copia atualizada) fica escondida aqui.
"""

import csv
import gzip
import io
import unicodedata
from pathlib import Path

DADOS = Path(__file__).resolve().parent / "dados"
EMBUTIDO = DADOS / "catalogo_sig.csv.gz"

# A URL do catalogo atualizado mora em `config.PADROES`, e so la: havia uma
# copia aqui que ninguem lia, e duas fontes para o mesmo endereco e o tipo de
# coisa que so aparece no dia em que uma das duas e trocada.


def sem_acento(s: str) -> str:
    """Para a busca casar 'geologica' com 'Geológica'."""
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").casefold()


def bytes_legivel(n) -> str:
    """
    Tamanho em bytes como o usuario le: "365,6 MB".

    Fonte unica. Havia tres copias desta funcao — na ficha do catalogo, na
    tela de conversao e na barra de download — e elas ja formatavam o
    separador decimal de jeitos diferentes.
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "?"
    if n <= 0:
        return "?"
    for unidade, limite in (("GB", 2**30), ("MB", 2**20), ("KB", 2**10)):
        if n >= limite:
            return f"{n/limite:,.1f} {unidade}".replace(",", ".")
    return f"{n} B"


class Camada:
    """Uma linha do catalogo: um pacote SIG baixavel."""

    # `_caixa` guarda a caixa de coordenadas deduzida do codigo da folha, pela
    # mesma razao de `_busca`: e cara de calcular e nao muda. False e "ainda
    # nao perguntei"; None e "perguntei e esta camada nao diz onde fica" — os
    # dois precisam ser distinguiveis, senao a camada sem codigo seria
    # reprocessada a cada filtragem, que e justamente o caso mais caro.
    __slots__ = ("id", "titulo", "pastas", "tipo", "nome_arquivo",
                 "formato", "tamanho_bytes", "link", "origem", "_busca",
                 "_caixa")

    def __init__(self, linha: dict):
        self.id = (linha.get("id") or "").strip()
        self.titulo = (linha.get("titulo") or "").strip()
        self.pastas = tuple(
            p for p in (linha.get(f"nivel_{i}") for i in range(1, 5))
            if p and p.strip())
        self.tipo = (linha.get("tipo") or "").strip()
        self.nome_arquivo = (linha.get("nome_arquivo") or "").strip()
        self.formato = (linha.get("formato") or "").strip()
        try:
            self.tamanho_bytes = int(linha.get("tamanho_bytes") or 0)
        except ValueError:
            self.tamanho_bytes = 0
        self.link = (linha.get("link_download") or "").strip()
        self.origem = (linha.get("origem") or "").strip()
        # Indice de busca pre-calculado: filtrar 1.824 camadas a cada tecla
        # digitada nao pode custar normalizacao de acento toda vez.
        self._busca = sem_acento(" ".join(
            (self.titulo, self.nome_arquivo) + self.pastas))
        self._caixa = False        # nao calculada ainda; ver folhas.py

    @property
    def tamanho_legivel(self) -> str:
        return bytes_legivel(self.tamanho_bytes)

    def casa(self, termo_normalizado: str) -> bool:
        return termo_normalizado in self._busca

    def __repr__(self):
        return f"<Camada {self.id} {self.titulo[:40]!r}>"


# ─── Nomes de pasta seguros no Windows ───────────────────────────────────────
# Mesma regra do projeto "Banco CPRM", e pela mesma razao: truncar DEPOIS de
# limpar as pontas deixa espaco no fim do nome, e o Explorer nao abre nem
# apaga pastas assim.

import re as _re

_INVALIDOS = _re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVADOS = {"CON", "PRN", "AUX", "NUL",
               *(f"COM{i}" for i in range(1, 10)),
               *(f"LPT{i}" for i in range(1, 10))}


def limpar_nome(nome: str, limite: int = 80) -> str:
    nome = unicodedata.normalize("NFC", nome or "")
    nome = _INVALIDOS.sub("-", nome)
    nome = " ".join(nome.split())
    if len(nome) > limite:
        nome = nome[:limite].rstrip()
        if " " in nome:
            nome = nome.rsplit(" ", 1)[0]
    nome = nome.strip(". ")
    if nome.upper() in _RESERVADOS:
        nome = "_" + nome
    return nome or "sem_nome"


# ─── Arvore ──────────────────────────────────────────────────────────────────

class No:
    """Pasta da arvore. Folhas carregam `camada`; galhos carregam `filhos`."""

    __slots__ = ("nome", "filhos", "camada", "pai")

    def __init__(self, nome: str, camada: Camada = None, pai: "No" = None):
        self.nome = nome
        self.camada = camada
        self.filhos = []
        self.pai = pai

    @property
    def eh_folha(self) -> bool:
        return self.camada is not None

    def contar(self) -> int:
        """Quantas camadas existem nesta subarvore."""
        if self.eh_folha:
            return 1
        return sum(f.contar() for f in self.filhos)

    def __repr__(self):
        return f"<No {self.nome!r} {len(self.filhos)} filhos>"


def montar_arvore(camadas) -> No:
    """
    Reconstroi a hierarquia do site a partir das colunas nivel_1..nivel_4.

    Duas camadas podem ter o mesmo titulo dentro da mesma pasta (o SIG e o KML
    da mesma folha, por exemplo), entao as folhas sao diferenciadas pelo tipo.
    """
    raiz = No("Acervo SIG")
    indice = {}
    for cam in camadas:
        atual = raiz
        acumulado = ()
        for parte in cam.pastas:
            acumulado += (parte,)
            no = indice.get(acumulado)
            if no is None:
                no = No(parte, pai=atual)
                indice[acumulado] = no
                atual.filhos.append(no)
            atual = no
        rotulo = cam.titulo
        if cam.tipo == "KML" and not rotulo.upper().startswith("KML"):
            rotulo = f"{rotulo} (KML)"
        atual.filhos.append(No(rotulo, camada=cam, pai=atual))
    return raiz


def filtrar(camadas, termo: str = "", tipos=None):
    """Filtra por texto (sem acento, sem caixa) e por tipo."""
    termo = sem_acento(termo.strip())
    resultado = []
    for cam in camadas:
        if tipos and cam.tipo not in tipos:
            continue
        if termo and not cam.casa(termo):
            continue
        resultado.append(cam)
    return resultado


# ─── Carga ───────────────────────────────────────────────────────────────────

def ler_csv(dados: bytes) -> list:
    texto = dados.decode("utf-8-sig")
    return [Camada(linha) for linha in csv.DictReader(io.StringIO(texto))]


def carregar(caminho: Path = None) -> list:
    """
    Le o catalogo. Aceita .csv.gz (o embutido) e .csv (uma copia atualizada).

    Se a copia atualizada existir mas estiver corrompida, cai para o embutido:
    um download interrompido nao pode deixar o plugin inutilizavel.
    """
    caminho = Path(caminho) if caminho else EMBUTIDO
    try:
        bruto = caminho.read_bytes()
        if caminho.suffix == ".gz" or bruto[:2] == b"\x1f\x8b":
            bruto = gzip.decompress(bruto)
        camadas = ler_csv(bruto)
        if camadas:
            return camadas
        raise ValueError("catalogo vazio")
    except Exception:
        if caminho != EMBUTIDO:
            return carregar(EMBUTIDO)
        raise


def filtrar_sig_do_catalogo_completo(dados: bytes) -> bytes:
    """
    Reduz o catalogo.csv completo (35 colunas, 5.258 linhas) as colunas e
    linhas que o plugin usa. E o que roda quando o usuario pede para atualizar
    o catalogo a partir do repositorio.

    O filtro e por TIPO, o mesmo de gerar_catalogo.py, e nao pela coluna
    `eh_sig`: ela responde "isto e dado geoespacial?", e desde que o plugin
    passou a oferecer a carta em PDF as duas perguntas deixaram de ser a
    mesma. Filtrar por eh_sig aqui deixava o catalogo atualizado menor que o
    embutido, e o usuario perdia as cartas ao clicar em "atualizar".

    Aceita o catalogo comprimido, reconhecido pelos bytes magicos e nao pela
    extensao da URL — mesma regra de `carregar`. Cru sao 5,3 MB; comprimido,
    472 KB. Quem esta em campo, que e quem mais usa este plugin, paga essa
    diferenca na franquia de dados.
    """
    from .config import COLUNAS_CATALOGO, TIPOS_INCLUIDOS
    if dados[:2] == b"\x1f\x8b":
        dados = gzip.decompress(dados)
    leitor = csv.DictReader(io.StringIO(dados.decode("utf-8-sig")))
    saida = io.StringIO()
    escritor = csv.DictWriter(saida, fieldnames=COLUNAS_CATALOGO,
                              extrasaction="ignore", lineterminator="\n")
    escritor.writeheader()
    n = 0
    for linha in leitor:
        if (linha.get("tipo") in TIPOS_INCLUIDOS
                and linha.get("status") == "ok"):
            escritor.writerow({c: linha.get(c, "") for c in COLUNAS_CATALOGO})
            n += 1
    if not n:
        raise ValueError("o catalogo baixado nao tem nenhuma camada conhecida")
    return saida.getvalue().encode("utf-8")
