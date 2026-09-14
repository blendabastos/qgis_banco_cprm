# -*- coding: utf-8 -*-
"""
test_municipios.py — A tabela de municipios do IBGE, embutida.

Roda sem QGIS: `municipios.py` e leitura de CSV e comparacao de texto.

    python testes\\test_municipios.py

Confere contra a tabela de verdade, nao contra invencao. As caixas foram
calculadas das malhas oficiais do IBGE por `gerar_municipios.py`; se alguma
estiver errada, o mapa vai para o lugar errado e o filtro esconde o acervo
certo — erro que ninguem percebe olhando a tela.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acervo_cprm import municipios as mun                       # noqa: E402
from acervo_cprm import folhas                                  # noqa: E402


class TesteCarga(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ms = mun.carregar()

    def test_carrega_os_municipios_do_brasil(self):
        """
        5.571 e o numero do IBGE: 5.570 municipios mais Fernando de Noronha,
        que e distrito estadual e tem malha propria.
        """
        self.assertEqual(len(self.ms), 5571)

    def test_todo_municipio_tem_nome_uf_e_caixa(self):
        for m in self.ms:
            self.assertTrue(m.nome, m)
            self.assertEqual(len(m.uf), 2, m)
            self.assertEqual(len(m.caixa), 4, m)

    def test_toda_caixa_e_coerente(self):
        """Oeste < leste e sul < norte, senao a caixa esta invertida."""
        for m in self.ms:
            o, s, l, n = m.caixa
            self.assertLess(o, l, m)
            self.assertLess(s, n, m)

    def test_toda_caixa_cai_no_brasil(self):
        """
        Fernando de Noronha e a UNICA excecao, e legitimamente: fica em
        -32,4 de longitude, a leste do limite -34 de `folhas.BRASIL`, que e
        definida como Brasil CONTINENTAL e existe para recusar folha decodifi-
        cada errado. Nao ha por que afrouxa-la por uma ilha — isso deixaria
        passar justamente os erros que ela pega.
        """
        fora = [m for m in self.ms
                if not folhas.cruza(m.caixa, folhas.BRASIL)]
        self.assertEqual([m.nome for m in fora], ["Fernando de Noronha"])

    def test_nenhuma_caixa_absurda(self):
        """
        Os extremos, medidos na tabela: Altamira (PA) tem 6,65 graus de altura
        e Tapaua (AM) 5,69 de largura. Altamira e o maior municipio do Brasil,
        maior que varios paises — nao ha nada de errado com a caixa dela.

        O teto de 8 graus existe so para pegar geometria corrompida na geracao,
        que produziria caixa de dezenas de graus.
        """
        for m in self.ms:
            o, s, l, n = m.caixa
            self.assertLess(l - o, 8.0, m)
            self.assertLess(n - s, 8.0, m)

    def test_os_extremos_conhecidos(self):
        """Trava os dois maiores: se mudarem, a geracao mudou de fonte."""
        mais_alto = max(self.ms, key=lambda m: m.caixa[3] - m.caixa[1])
        mais_largo = max(self.ms, key=lambda m: m.caixa[2] - m.caixa[0])
        self.assertEqual(mais_alto.rotulo, "Altamira — PA")
        self.assertEqual(mais_largo.rotulo, "Tapauá — AM")

    def test_tabela_ausente_nao_derruba(self):
        """Sem a tabela o plugin perde a busca por cidade e mantem o resto."""
        self.assertEqual(mun.carregar(Path("nao_existe_isto.csv.gz")), [])


class TesteBusca(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ms = mun.carregar()

    def test_acha_sem_acento_e_sem_caixa(self):
        """'sao gabriel' tem que achar 'São Gabriel' — e assim que se digita."""
        for termo in ("sao gabriel", "SAO GABRIEL", "São Gabriel"):
            with self.subTest(termo=termo):
                achados = mun.procurar(self.ms, termo)
                self.assertTrue(any(m.nome.startswith("São Gabriel")
                                    for m in achados), termo)

    def test_quem_comeca_com_o_termo_vem_antes(self):
        """
        Digitando "belo", "Belo Horizonte" tem que aparecer acima de
        "Formoso do Araguaia", que apenas contem "belo" no meio.
        """
        achados = mun.procurar(self.ms, "belo")
        nomes = [m.nome for m in achados]
        self.assertIn("Belo Horizonte", nomes)
        comecam = [i for i, n in enumerate(nomes)
                   if n.lower().startswith("belo")]
        contem = [i for i, n in enumerate(nomes)
                  if not n.lower().startswith("belo")]
        if comecam and contem:
            self.assertLess(max(comecam), min(contem))

    def test_termo_vazio_nao_devolve_tudo(self):
        for termo in ("", "   ", None):
            with self.subTest(termo=termo):
                self.assertEqual(mun.procurar(self.ms, termo), [])

    def test_limite_de_sugestoes(self):
        """'santa' casa centenas; a lista tem que parar num tamanho util."""
        achados = mun.procurar(self.ms, "santa")
        self.assertLessEqual(len(achados), mun.LIMITE_SUGESTOES)

    def test_rotulo_traz_a_uf(self):
        p = mun.por_rotulo(self.ms, "Parauapebas — PA")
        self.assertIsNotNone(p)
        self.assertEqual(p.uf, "PA")
        self.assertEqual(p.rotulo, "Parauapebas — PA")

    def test_nome_repetido_exige_a_uf(self):
        """
        232 nomes se repetem entre estados. Sem a UF nao da para saber a qual
        deles o mapa deveria ir, e o certo e nao adivinhar.
        """
        repetidos = {}
        for m in self.ms:
            repetidos.setdefault(m.nome, []).append(m)
        nome = next(n for n, v in repetidos.items() if len(v) > 1)
        self.assertIsNone(mun.por_rotulo(self.ms, nome))
        # com a UF, resolve
        alvo = repetidos[nome][0]
        self.assertIs(mun.por_rotulo(self.ms, alvo.rotulo), alvo)

    def test_nome_unico_dispensa_a_uf(self):
        self.assertIsNotNone(mun.por_rotulo(self.ms, "Parauapebas"))

    def test_rotulo_desconhecido_devolve_none(self):
        for ruim in ("", None, "Cidade Que Nao Existe — ZZ", "   "):
            with self.subTest(rotulo=ruim):
                self.assertIsNone(mun.por_rotulo(self.ms, ruim))


class TesteFolga(unittest.TestCase):

    def test_a_folga_afasta_as_bordas(self):
        caixa = (-51.2, -6.5, -49.7, -5.9)
        o, s, l, n = mun.com_folga(caixa)
        self.assertLess(o, caixa[0])
        self.assertLess(s, caixa[1])
        self.assertGreater(l, caixa[2])
        self.assertGreater(n, caixa[3])

    def test_municipio_minusculo_ganha_folga_minima(self):
        """
        Sem o piso, um municipio de poucos quarteiroes daria uma janela
        microscopica — e a folha do acervo que o contem tem 6 graus.
        """
        caixa = (-43.0, -20.0, -42.999, -19.999)
        o, s, l, n = mun.com_folga(caixa)
        self.assertGreater(l - o, 0.04)
        self.assertGreater(n - s, 0.04)


class TesteContraOAcervo(unittest.TestCase):
    """O que importa de verdade: a cidade encontra o acervo da regiao."""

    @classmethod
    def setUpClass(cls):
        cls.ms = mun.carregar()
        from acervo_cprm import catalogo as cat
        cls.camadas = cat.carregar()

    def test_cidades_conhecidas_acham_acervo(self):
        """
        Cada uma destas e uma regiao com acervo publicado do SGB. Se alguma
        parar de achar camada, ou a caixa mudou ou a extracao de folha quebrou.
        """
        for rotulo in ("Parauapebas — PA", "Brasília — DF",
                       "Ouro Preto — MG", "Manaus — AM",
                       "Caetité — BA"):
            with self.subTest(cidade=rotulo):
                m = mun.por_rotulo(self.ms, rotulo)
                self.assertIsNotNone(m, rotulo)
                cruzam, _, _ = folhas.separar_por_extensao(
                    self.camadas, mun.com_folga(m.caixa))
                self.assertTrue(cruzam, "%s nao achou acervo" % rotulo)

    def test_municipio_grande_cruza_mais_de_uma_folha(self):
        """
        Um municipio NAO cabe necessariamente numa folha 1:1M (6x4 graus):
        Altamira tem 6,65 graus de altura e Almeirim 4,40 — as duas passam dos
        4 graus de altura da folha.

        Isso nao e defeito, e a razao de o filtro ser por CRUZAMENTO e nao por
        continencia. Se fosse por continencia, Altamira nao acharia folha
        nenhuma.
        """
        m = mun.por_rotulo(self.ms, "Altamira — PA")
        self.assertIsNotNone(m)
        self.assertGreater(m.caixa[3] - m.caixa[1], 4.0)
        cruzam, _, _ = folhas.separar_por_extensao(self.camadas, m.caixa)
        self.assertTrue(cruzam, "Altamira nao achou acervo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
