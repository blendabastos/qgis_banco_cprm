# -*- coding: utf-8 -*-
"""
test_projetos.py — A camada indice dos projetos aerogeofisicos.

Roda sem QGIS.

    python testes\\test_projetos.py

Ate esta tabela entrar, `Geofisica-XYZ` era o unico tipo do acervo 100%
invisivel ao filtro espacial: os titulos sao "1009-XYZ", numero de projeto e
nao codigo de folha do IBGE.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acervo_cprm import projetos                                # noqa: E402
from acervo_cprm import folhas                                  # noqa: E402
from acervo_cprm import catalogo as cat                         # noqa: E402


class TesteCarga(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tabela = projetos.carregar()

    def test_carrega_os_projetos(self):
        self.assertGreater(len(self.tabela), 140)

    def test_toda_caixa_e_coerente_e_cai_no_brasil(self):
        for numero, p in self.tabela.items():
            o, s, l, n = p.caixa
            with self.subTest(projeto=numero):
                self.assertLess(o, l)
                self.assertLess(s, n)
                self.assertTrue(folhas.cruza(p.caixa, folhas.BRASIL))

    def test_as_series_1000_e_3000_estao_la(self):
        """Sao as duas series de projeto aerogeofisico que o acervo publica."""
        self.assertTrue(any(1000 <= n < 2000 for n in self.tabela))
        self.assertTrue(any(3000 <= n < 4000 for n in self.tabela))

    def test_tabela_ausente_nao_derruba(self):
        self.assertEqual(projetos.carregar(Path("nao_existe.csv.gz")), {})


class TesteNumeroDoTexto(unittest.TestCase):

    def test_le_o_numero_do_titulo(self):
        for texto, esperado in (("1009-XYZ", 1009),
                                ("3065-Geotif", 3065),
                                ("  1117-XYZ", 1117),
                                ("1112 - XYZ", 1112)):
            with self.subTest(texto=texto):
                self.assertEqual(projetos.numero_do_texto(texto), esperado)

    def test_so_no_comeco_do_titulo(self):
        """
        Ancorado de proposito. Solto, "Carta Geologica ... (2020)" viraria
        projeto 2020 e a camada iria parar em outro estado — um erro que
        ninguem percebe olhando a arvore, so olhando o mapa.
        """
        for texto in ("Carta Geologica - Cachoeira Seca SB.21-X-C-V (2020)",
                      "Projeto Aerogeofisico 1117",
                      "Levantamento 3065 Mag",
                      "SIG (Vetores) - Aracaju SC.24",
                      "", None):
            with self.subTest(texto=texto):
                self.assertIsNone(projetos.numero_do_texto(texto))


class TesteContraOCatalogo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.camadas = cat.carregar()
        cls.tabela = projetos.carregar()

    def test_a_aerogeofisica_ganhou_posicao(self):
        """
        Medido: 116 de 141 XYZ e 122 de 243 Geotiff casam com o indice.
        Os que faltam sao projetos que o SGB publica sem poligono no indice.
        """
        for tipo, minimo in (("Geofísica-XYZ", 0.75),
                             ("Geofísica-Geotiff", 0.45)):
            alvo = [c for c in self.camadas if c.tipo == tipo]
            com = [c for c in alvo
                   if projetos.caixa_da_camada(c, self.tabela) is not None]
            with self.subTest(tipo=tipo):
                self.assertGreater(len(com) / len(alvo), minimo,
                                   "%d de %d" % (len(com), len(alvo)))

    def test_o_1009_cai_onde_o_leitor_de_xyz_diz(self):
        """
        Validacao cruzada entre duas fontes independentes.

        `xyz.py` sabe, de ter lido o arquivo, que o projeto 1009 grava
        coordenada em grau.minuto.segundo e que "-15.27.08.20" e uma latitude
        de verdade dele. Essa latitude tem que cair dentro da caixa que a
        camada indice do SGB da para o mesmo projeto — duas fontes que nunca
        se falaram concordando sobre o mesmo lugar.
        """
        from acervo_cprm import xyz
        lat = xyz.ler_gms("-15.27.08.20")
        self.assertAlmostEqual(lat, -15.4523, places=3)
        caixa = self.tabela[1009].caixa
        self.assertTrue(caixa[1] <= lat <= caixa[3],
                        "latitude %.4f fora de %s" % (lat, caixa))

    def test_nenhuma_carta_geologica_pegou_caixa_de_projeto(self):
        """
        O risco da extracao por numero: casar com um ano no titulo. Nenhuma
        camada que nao seja de geofisica pode ter vindo desta tabela.
        """
        for c in self.camadas:
            if c.tipo.startswith("Geofísica"):
                continue
            with self.subTest(titulo=c.titulo[:40]):
                self.assertIsNone(
                    projetos.caixa_da_camada(c, self.tabela))

    def test_a_caixa_entra_no_filtro(self):
        """Ponta a ponta: o XYZ agora responde ao filtro espacial."""
        xyz_c = [c for c in self.camadas if c.tipo == "Geofísica-XYZ"]
        alvo = next(c for c in xyz_c if c.titulo.startswith("1009-"))
        caixa = folhas.caixa_da_camada(alvo)
        self.assertIsNotNone(caixa)
        cruzam, fora, sem = folhas.separar_por_extensao([alvo], caixa)
        self.assertEqual(len(cruzam), 1)
        self.assertEqual(sem, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
