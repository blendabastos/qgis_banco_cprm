# -*- coding: utf-8 -*-
"""
test_folhas.py — A malha da Carta Internacional ao Milionesimo.

Roda sem QGIS: `folhas.py` e aritmetica pura, de proposito.

    python testes\\test_folhas.py

O teste que mais importa e o de ida e volta: gerar a folha a partir da
coordenada de uma cidade conhecida e decodificar de volta tem que devolver uma
caixa que contem aquela cidade. Se a formula estiver errada em qualquer nivel,
esse teste acusa — e foi ele que pegou tres expectativas erradas minhas durante
o desenvolvimento (eu havia atribuido Belem a SA.23, Altamira a SB.21 e Porto
Alegre a SI.22; as tres estavam erradas, o decodificador nao).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acervo_cprm import folhas                                  # noqa: E402
from acervo_cprm import catalogo as cat                         # noqa: E402


#: Capitais e cidades de referencia: (nome, lon, lat).
CIDADES = [
    ("Aracaju", -37.07, -10.91),
    ("Belem", -48.50, -1.46),
    ("Sao Paulo", -46.63, -23.55),
    ("Brasilia", -47.88, -15.79),
    ("Altamira", -52.21, -3.20),
    ("Porto Alegre", -51.23, -30.03),
    ("Manaus", -60.02, -3.12),
    ("Recife", -34.88, -8.05),
    ("Cuiaba", -56.10, -15.60),
    ("Rio de Janeiro", -43.17, -22.91),
    ("Boa Vista", 	-60.67, 2.82),
    ("Rio Branco", -67.81, -9.97),
]


class TesteIdaEVolta(unittest.TestCase):
    """A prova da malha: coordenada -> folha -> caixa tem que conter a origem."""

    def test_toda_cidade_cai_na_propria_folha(self):
        for nome, lon, lat in CIDADES:
            with self.subTest(cidade=nome):
                codigo = folhas.folha_de(lon, lat)
                self.assertIsNotNone(codigo, nome)
                caixa = folhas.caixa(codigo)
                self.assertIsNotNone(caixa, f"{nome}: {codigo} nao decodificou")
                o, s, l, n = caixa
                self.assertTrue(o <= lon <= l and s <= lat <= n,
                                f"{nome} ({lon}, {lat}) fora de {codigo} {caixa}")

    def test_hemisferio_norte(self):
        """Boa Vista e Roraima estao acima do equador; a letra N importa."""
        self.assertEqual(folhas.folha_de(-60.67, 2.82), "NA.20")
        o, s, l, n = folhas.caixa("NA.20")
        self.assertEqual((s, n), (0.0, 4.0))


class TesteTamanhoDaFolha(unittest.TestCase):
    """Cada sufixo corta a folha; os tamanhos sao os da especificacao."""

    def test_a_folha_do_milionesimo_e_6_por_4(self):
        o, s, l, n = folhas.caixa("SC.24")
        self.assertAlmostEqual(l - o, 6.0)
        self.assertAlmostEqual(n - s, 4.0)

    def test_cada_nivel_corta(self):
        esperado = [
            ("SB.21", 6.0, 4.0),              # 1:1.000.000
            ("SB.21-Z", 3.0, 2.0),            # 1:500.000
            ("SB.21-Z-A", 1.5, 1.0),          # 1:250.000
            ("SB.21-Z-A-III", 0.5, 0.5),      # 1:100.000 = 30' x 30'
            ("SB.21-Z-A-III-2", 0.25, 0.25),  # 1:50.000  = 15' x 15'
        ]
        for codigo, largura, altura in esperado:
            with self.subTest(codigo=codigo):
                o, s, l, n = folhas.caixa(codigo)
                self.assertAlmostEqual(l - o, largura, places=6)
                self.assertAlmostEqual(n - s, altura, places=6)

    def test_o_cem_mil_e_tres_colunas_por_duas_linhas(self):
        """
        A folha de 1:100.000 tem 30' x 30'. A conta decide o arranjo:
        1o30' / 30' = 3 COLUNAS e 1o / 30' = 2 LINHAS. Nao 2x3.

        Este teste ja existiu conferindo 2x3, porque eu o escrevi a partir da
        minha implementacao em vez da norma. Ele passava, e o plugin trazia a
        folha errada: filtrando por Mage (RJ) vinha Casimiro de Abreu, que fica
        em Nova Friburgo, e faltava a Baia de Guanabara. Area somada igual,
        posicao trocada — por isso a verificacao por area nao acusava.

        Agora o teste fixa o TAMANHO de cada folha, que e o que a norma diz.
        """
        MEIO_GRAU = 0.5
        rotulos = ("I", "II", "III", "IV", "V", "VI")
        filhas = [folhas.caixa("SB.21-Z-A-%s" % r) for r in rotulos]
        for rotulo, (o, s, l, n) in zip(rotulos, filhas):
            with self.subTest(folha=rotulo):
                self.assertAlmostEqual(l - o, MEIO_GRAU, places=9)
                self.assertAlmostEqual(n - s, MEIO_GRAU, places=9)

        pai = folhas.caixa("SB.21-Z-A")
        # As seis cobrem o pai, sem sobra e sem buraco.
        self.assertAlmostEqual(sum((l - o) * (n - s) for o, s, l, n in filhas),
                               (pai[2] - pai[0]) * (pai[3] - pai[1]), places=9)
        # I e o canto noroeste, III o nordeste, IV o sudoeste, VI o sudeste.
        self.assertAlmostEqual(filhas[0][0], pai[0])     # I:  oeste
        self.assertAlmostEqual(filhas[0][3], pai[3])     # I:  norte
        self.assertAlmostEqual(filhas[2][2], pai[2])     # III: leste
        self.assertAlmostEqual(filhas[2][3], pai[3])     # III: norte
        self.assertAlmostEqual(filhas[3][0], pai[0])     # IV: oeste
        self.assertAlmostEqual(filhas[3][1], pai[1])     # IV: sul
        self.assertAlmostEqual(filhas[5][2], pai[2])     # VI: leste
        self.assertAlmostEqual(filhas[5][1], pai[1])     # VI: sul

        # I, II e III sao vizinhas na MESMA linha: mesma latitude, longitudes
        # encostadas. Com 2x3 isto era falso, e era o defeito.
        for a, b in ((filhas[0], filhas[1]), (filhas[1], filhas[2])):
            self.assertAlmostEqual(a[1], b[1], places=9)   # mesmo sul
            self.assertAlmostEqual(a[3], b[3], places=9)   # mesmo norte
            self.assertAlmostEqual(a[2], b[0], places=9)   # encostadas

    def test_os_quadrantes_nao_se_sobrepoem(self):
        cantos = [folhas.caixa("SC.24-%s" % q) for q in ("V", "X", "Y", "Z")]
        for i in range(len(cantos)):
            for j in range(i + 1, len(cantos)):
                a, b = cantos[i], cantos[j]
                # Tocar na borda vale; sobrepor area, nao.
                largura = min(a[2], b[2]) - max(a[0], b[0])
                altura = min(a[3], b[3]) - max(a[1], b[1])
                self.assertLessEqual(min(largura, altura), 1e-9,
                                     f"quadrantes {i} e {j} se sobrepoem")


class TesteExtracaoDoCodigo(unittest.TestCase):
    """Achar o codigo no meio do titulo, nas grafias que o acervo usa."""

    def test_grafias_reais_do_catalogo(self):
        casos = [
            ("SIG (Vetores) - Aracaju SC.24", "SC.24"),
            ("Carta Geologica - Aracaju SC.24", "SC.24"),
            ("KML - Aracaju SC.24", "SC.24"),
            ("SC.20-X-C-III - Geotif", "SC.20-X-C-III"),
            ("ARIM Serido: Folha Augusto Severo - SB.24-X-D-IV",
             "SB.24-X-D-IV"),
            ("Carta Geologica - Cachoeira Seca SB.21-X-C-V (2020)",
             "SB.21-X-C-V"),
            ("Folha SB-22-Z-B", "SB.22-Z-B"),          # hifen no lugar do ponto
            ("folha sc24 sem separador", "SC.24"),     # sem separador nenhum
        ]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(folhas.codigo_do_texto(texto), esperado)

    def test_nao_inventa_codigo(self):
        for texto in ("Projeto Aerogeofisico 1117", "Geoquimica do Parana",
                      "Levantamento 3065 Mag", "", None,
                      "NUVEM DE PONTOS LIDAR"):
            with self.subTest(texto=texto):
                self.assertIsNone(folhas.codigo_do_texto(texto))

    def test_nao_morde_numero_maior(self):
        """Sem o (?!\\d), 'SB.210' viraria fuso 21 e uma caixa errada."""
        self.assertIsNone(folhas.codigo_do_texto("amostra SB.210 do lote"))

    def test_nao_morde_palavra_como_sufixo(self):
        """
        O defeito que este arquivo pegou: "Folha SC.24 Sergipe" virava
        "SC.24-SE", porque o "Se" de Sergipe casava com o quadrante sudeste de
        1:25.000. A caixa saia 32x menor que a folha real — o filtro esconderia
        tudo em volta, e nada na tela diria por que.
        """
        casos = [
            ("Folha SC.24 Sergipe", "SC.24"),
            ("folha sc24 sem separador", "SC.24"),
            ("SB.21 sobre o rio Xingu", "SB.21"),
            ("SD.23 norte de Brasilia", "SD.23"),
            ("SC.24 Nordeste do pais", "SC.24"),
        ]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                self.assertEqual(folhas.codigo_do_texto(texto), esperado)

    def test_sufixo_legitimo_ainda_casa(self):
        """A correcao acima nao pode ter matado o sufixo de verdade."""
        self.assertEqual(folhas.codigo_do_texto("Folha SB.22-Z-B-SE"),
                         "SB.22-Z-B-SE")
        self.assertEqual(folhas.codigo_do_texto("SC.24-Y-D-VI-3-NE"),
                         "SC.24-Y-D-VI-3-NE")


class TesteCaixaRecusada(unittest.TestCase):
    """Caixa errada e pior que caixa nenhuma: o filtro esconderia dado bom."""

    def test_codigo_invalido(self):
        for ruim in ("", None, "XX.24", "SC.99", "SC", "SC.ab", "24.SC"):
            with self.subTest(codigo=ruim):
                self.assertIsNone(folhas.caixa(ruim))

    def test_fora_do_brasil_e_recusado(self):
        """SA.01 fica no Pacifico; nao ha acervo do SGB la."""
        self.assertIsNone(folhas.caixa("SA.01"))

    def test_sufixo_estranho_mantem_o_que_se_sabe(self):
        """Um sufixo desconhecido para a subdivisao, sem derrubar a folha."""
        caixa = folhas.caixa("SC.24-Q")
        self.assertEqual(caixa, folhas.caixa("SC.24"))


class TesteCruzamento(unittest.TestCase):

    def test_sobreposicao(self):
        a = (-48.0, -16.0, -42.0, -12.0)
        self.assertTrue(folhas.cruza(a, (-45.0, -14.0, -44.0, -13.0)))  # dentro
        self.assertTrue(folhas.cruza(a, (-50.0, -18.0, -46.0, -14.0)))  # parcial
        self.assertFalse(folhas.cruza(a, (-40.0, -16.0, -38.0, -12.0)))  # a leste
        self.assertFalse(folhas.cruza(a, (-48.0, -20.0, -42.0, -17.0)))  # ao sul

    def test_borda_conta_como_cruzamento(self):
        """Quem esta na divisa quer as duas folhas, nao uma."""
        a = (-48.0, -16.0, -42.0, -12.0)
        self.assertTrue(folhas.cruza(a, (-42.0, -14.0, -36.0, -13.0)))

    def test_none_nao_cruza(self):
        self.assertFalse(folhas.cruza(None, (-48.0, -16.0, -42.0, -12.0)))
        self.assertFalse(folhas.cruza((-48.0, -16.0, -42.0, -12.0), None))


class TesteContraOCatalogoReal(unittest.TestCase):
    """Contra as 4.719 camadas de verdade, nao contra invencao."""

    @classmethod
    def setUpClass(cls):
        cls.camadas = cat.carregar()

    def test_cobertura_nao_regride(self):
        """
        76,8% das camadas tem posicao: 71,2% pelo codigo de folha, mais a
        aerogeofisica que veio da camada indice. O numero pode SUBIR (o SGB
        publica mais), mas se cair e porque uma das duas fontes quebrou — e a
        falha seria silenciosa, um filtro que esconde demais.
        """
        com = sum(1 for c in self.camadas
                  if folhas.caixa_da_camada(c) is not None)
        fracao = com / len(self.camadas)
        self.assertGreater(fracao, 0.72,
                           "cobertura caiu para %.1f%%" % (100 * fracao))

    def test_toda_caixa_cai_no_brasil(self):
        for c in self.camadas:
            caixa = folhas.caixa_da_camada(c)
            if caixa is None:
                continue
            with self.subTest(titulo=c.titulo[:40]):
                self.assertTrue(folhas.cruza(caixa, folhas.BRASIL))

    def test_a_aerogeofisica_nao_vem_de_codigo_de_folha(self):
        """
        Os titulos de aerogeofisica sao "1009-XYZ": numero de projeto, nunca
        codigo de folha. A caixa deles vem da camada indice (projetos.py) — se
        `codigo_do_texto` passasse a casar com esses titulos, seria sinal de
        que a expressao regular esta mordendo numero que nao e folha.
        """
        for tipo in ("Geofísica-XYZ", "Nuvem de pontos (LiDAR)",
                     "Ortofoto/raster"):
            com_folha = [c for c in self.camadas if c.tipo == tipo
                         and folhas.codigo_do_texto(c.titulo)]
            with self.subTest(tipo=tipo):
                self.assertEqual(com_folha, [],
                                 [c.titulo for c in com_folha[:3]])

    def test_a_aerogeofisica_ganhou_posicao_pelo_indice(self):
        """
        Ate a camada indice entrar, XYZ era o unico tipo do acervo 100%
        invisivel ao filtro. Se cair para zero de novo, a tabela de projetos
        sumiu ou a chave mudou — e o filtro voltaria a esconder 141 camadas
        sem dizer nada.
        """
        xyz = [c for c in self.camadas if c.tipo == "Geofísica-XYZ"]
        com = [c for c in xyz if folhas.caixa_da_camada(c) is not None]
        self.assertGreater(len(com) / len(xyz), 0.75,
                           "so %d de %d XYZ tem posicao" % (len(com), len(xyz)))

    def test_separar_devolve_todas(self):
        """Nenhuma camada pode sumir da soma das tres listas."""
        extensao = (-48.0, -16.0, -42.0, -12.0)     # Brasilia
        cruzam, fora, sem = folhas.separar_por_extensao(self.camadas, extensao)
        self.assertEqual(len(cruzam) + len(fora) + len(sem), len(self.camadas))
        self.assertTrue(cruzam, "nada cruzou a folha de Brasilia")

    def test_brasilia_traz_a_folha_de_brasilia(self):
        """Um caso concreto ponta a ponta, com nome conferivel no mapa."""
        codigo = folhas.folha_de(-47.88, -15.79)
        self.assertEqual(codigo, "SD.23")
        extensao = folhas.caixa(codigo)
        cruzam, _, _ = folhas.separar_por_extensao(self.camadas, extensao)
        titulos = " | ".join(c.titulo for c in cruzam)
        self.assertIn("SD.23", titulos)

    def test_o_cache_nao_muda_a_resposta(self):
        """`_caixa` guarda o resultado; a segunda pergunta tem que ser igual."""
        amostra = self.camadas[:200]
        primeira = [folhas.caixa_da_camada(c) for c in amostra]
        segunda = [folhas.caixa_da_camada(c) for c in amostra]
        self.assertEqual(primeira, segunda)


class TesteFolhaNomeadaContraMunicipio(unittest.TestCase):
    """
    A verificacao que faltava: a folha que LEVA O NOME de um lugar tem que
    conter aquele lugar.

    Nenhum teste de geometria pura pega troca de posicao entre folhas irmas —
    elas tem o mesmo tamanho e cobrem a mesma area somada, entao conferir
    dimensao e area passa nos dois arranjos. So amarrar o codigo a um lugar de
    VERDADE acusa.

    O defeito que motivou esta classe: filtrar por Mage (RJ) trazia a folha
    Casimiro de Abreu, que fica a uns 60 km dali, e escondia a Baia de
    Guanabara, que e a folha de Mage. Foi achado pelo uso, com o plugin na
    mao, depois de dois testes verdes.
    """

    @classmethod
    def setUpClass(cls):
        from acervo_cprm import municipios
        cls.mun = municipios
        cls.municipios = municipios.carregar()
        cls.camadas = cat.carregar()

    def _pares_do_catalogo(self):
        """
        (codigo, municipio) para toda carta cujo nome e de um municipio.

        Sai do proprio catalogo do SGB cruzado com a tabela do IBGE — sao 325
        pares, e nenhum foi escolhido a dedo.
        """
        for c in self.camadas:
            if not c.titulo.startswith("Carta Geol"):
                continue
            codigo = folhas.codigo_do_texto(c.titulo)
            if not codigo or "-" not in codigo:
                continue
            nome = c.titulo.split(" - ", 1)[-1].rsplit(codigo, 1)[0].strip()
            m = self.mun.por_rotulo(self.municipios, nome)
            if m is not None:
                yield codigo, nome, m

    @staticmethod
    def _distancia(a, b):
        """Distancia entre duas caixas, em grau. Zero quando se tocam."""
        dx = max(0.0, max(a[0] - b[2], b[0] - a[2]))
        dy = max(0.0, max(a[1] - b[3], b[1] - a[3]))
        return (dx * dx + dy * dy) ** 0.5

    def test_a_folha_fica_ONDE_esta_o_municipio_que_a_batiza(self):
        """
        A pergunta e de POSICAO, nao de continencia.

        Exigir que a folha CONTENHA o municipio homonimo seria exigir do
        acervo algo que a norma nao promete: o nome da folha e rotulo, e o
        filtro trabalha com espaco geografico. Uma folha batizada por
        localidade de borda — Cabedelo (PB) fica 0,03 grau ao sul da sua — nao
        tem defeito nenhum, e o teste nao pode chamar isso de erro.

        O que importa e a DISTANCIA entre a folha e o lugar que a nomeia, que
        tem que ser zero na esmagadora maioria. Medido sobre 325 cartas do
        catalogo cruzadas com a tabela do IBGE:

            arranjo 3x2 (certo)    mediana 0,000   p90 0,000
            arranjo 2x3 (errado)   mediana 0,000   p90 0,556

        A mediana nao distingue os dois; o p90 distingue com folga. E a cauda
        e ruido de NOME, nao de geometria: ha "Rio Pardo" em mais de um estado,
        e a folha de um nao fica perto do municipio do outro. Por isso o teste
        olha o percentil 90 e ignora o topo.
        """
        distancias = sorted(self._distancia(folhas.caixa(codigo), m.caixa)
                            for codigo, _nome, m in self._pares_do_catalogo())
        self.assertGreater(len(distancias), 250,
                           "poucos pares para o teste valer")
        p90 = distancias[int(0.90 * len(distancias))]
        self.assertLess(
            p90, 0.1,
            "p90 da distancia folha-municipio = %.3f grau. Com a malha certa e "
            "0,000; um arranjo trocado de subdivisao leva isto para 0,5+." % p90)

    def test_mage_traz_guanabara_e_nao_casimiro_de_abreu(self):
        """
        O caso concreto do defeito, travado pelo nome.

        As duas folhas sao irmas, do mesmo tamanho, na mesma folha de
        1:250.000. Trocar uma pela outra leva o usuario a uns 60 km de
        distancia sem nenhum sinal na tela — o filtro simplesmente mostra a
        carta errada e esconde a certa.
        """
        mage = self.mun.por_rotulo(self.municipios, "Magé — RJ")
        self.assertIsNotNone(mage)
        guanabara = folhas.caixa("SF.23-Z-B-IV")
        casimiro = folhas.caixa("SF.23-Z-B-III")
        self.assertTrue(folhas.cruza(guanabara, mage.caixa),
                        "Mage perdeu a folha Baia de Guanabara")
        self.assertFalse(folhas.cruza(casimiro, mage.caixa),
                         "Mage pegou Casimiro de Abreu, que fica a 60 km")

    def test_o_filtro_traz_a_carta_de_mage(self):
        """Ponta a ponta, pelo caminho que o painel percorre."""
        mage = self.mun.por_rotulo(self.municipios, "Magé — RJ")
        cruzam, _, _ = folhas.separar_por_extensao(
            self.camadas, self.mun.com_folga(mage.caixa))
        titulos = " | ".join(c.titulo for c in cruzam)
        self.assertIn("Guanabara", titulos)


if __name__ == "__main__":
    unittest.main(verbosity=2)
