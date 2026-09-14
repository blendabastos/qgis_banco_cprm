# Acervo SIG — CPRM

Plugin de QGIS para baixar as camadas do acervo do Serviço Geológico do Brasil
(SGB/CPRM) publicadas no portal
[GEOSGB](https://geosgb.sgb.gov.br/downloads/), e adicioná-las ao projeto.

O portal publica **5.258 arquivos**. Destes, **4.719 têm link em
funcionamento e interessam a quem trabalha com o mapa** — 643 GB —, e são eles
que o plugin oferece: as camadas de dado mais a carta geológica em PDF de cada
folha. Ficam de fora os 480 relatórios de texto e os 54 links quebrados.

Você busca a folha ou o projeto no painel, confirma o download, escolhe o que
do pacote interessa, e as camadas entram no mapa. Sem navegar o site, sem
descompactar à mão, sem procurar onde o arquivo caiu.

Também abre o que o QGIS sozinho não abre: os **126 projetos aerogeofísicos** em
formato Geosoft — 248 GB de XYZ, perto de 1,4 bilhão de pontos de aquisição —
viram tabelas de pontos, e as **planilhas de geoquímica** sem shapefile viram
camadas a partir das colunas de coordenada.

> **Requer QGIS 4.0 ou superior** (PyQt6). Não roda no QGIS 3.x.

---

## Índice

1. [Instalação](#instalação)
2. [Como usar](#como-usar)
3. [O que está disponível](#o-que-está-disponível)
4. [O que o plugin resolve](#o-que-o-plugin-resolve)
5. [Arquitetura](#arquitetura)
6. [O catálogo](#o-catálogo)
7. [Testes](#testes)
8. [Limitações](#limitações)

Duas coisas que talvez você tenha vindo procurar:
[XYZ aerogeofísico vira tabela de pontos](#xyz-aerogeofísico-vira-tabela-de-pontos)
· [Tabelas de geoquímica viram pontos](#tabelas-de-geoquímica-viram-pontos)

---

## Instalação

```powershell
python empacotar.py --instalar
```

Gera `dist/acervo_cprm-<versão>.zip` e copia para o perfil do QGIS 4. Depois, no
QGIS: **Plugins → Manage and Install Plugins → Installed**, e marque
*Acervo SIG - CPRM*.

Em outra máquina, use o ZIP em **Install from ZIP**.

Sem dependência externa: só a biblioteca padrão do Python e o que já vem no QGIS.

Durante o desenvolvimento, para recarregar sem reiniciar:

```python
import qgis.utils
qgis.utils.reloadPlugin('acervo_cprm')
```

---

## Como usar

O botão na barra de ferramentas abre o painel, ancorado à direita.

> **A lista fica por último, e é de propósito.** Ancorado à direita, o painel
> tem a altura inteira da janela do QGIS — e quando essa janela é mais alta que
> a tela, o fim do painel cai fora do monitor. Com a ficha e os botões no
> rodapé, eles ficavam inalcançáveis, e só apareciam movendo o painel para o
> topo. Nenhum ajuste de tamanho resolve isso: o problema não é o painel ser
> pequeno demais, é ele ser mais alto que a tela. Com a árvore em último, tudo
> o que se clica fica a uma distância fixa do topo, e é a lista que cresce.

**1. Busque.** O campo filtra por folha, projeto ou palavra, ignorando acento e
caixa — `geologica` acha `Geológica`. O seletor ao lado restringe por tipo.

**2. Clique na camada.** Uma ficha abaixo da árvore mostra título, tipo, tamanho
e caminho, e avisa se o pacote **já está baixado**. Clicar não transfere nada.

**3. Confirme.** O botão **Baixar…** (ou duplo clique) abre um diálogo com o que
será transferido, o tamanho, o destino e o ID no GEOSGB. Acima de 200 MB há um
aviso explícito. Se o pacote já estiver em disco, o diálogo avisa e o botão vira
**Adicionar ao projeto**.

**4. Converta o XYZ, se houver.** Em pacote de aerogeofísica, o plugin lista os
arquivos Geosoft com o que deduziu de cada um — colunas de coordenada, CRS, e
**de onde tirou essa conclusão** — mais a estimativa de pontos e de tempo. Você
marca o que converter. [Detalhes abaixo](#xyz-aerogeofísico-vira-tabela-de-pontos).

**5. Escolha o que entra.** O pacote é aberto e o plugin lista cada arquivo com
tipo, contagem e CRS. Camadas vazias vêm desmarcadas; o que o QGIS não abre
aparece como *somente download*, com um botão para abrir a pasta.

As selecionadas entram num **grupo com o nome do pacote**, recolhido, no topo do
painel de camadas — vetores acima dos rasters, para o GeoTIFF não esconder os
lineamentos.

O download e a conversão rodam em segundo plano, com **barra de progresso no topo do mapa** — quanto já veio de quanto falta, ou qual arquivo está sendo convertido — e botão de cancelar ao lado.

Botão direito na camada: copiar o link de download ou o ID do GEOSGB.

**Pasta de destino** — padrão `Documentos\Acervo CPRM`, alterável no rodapé.
Cada pacote ganha **uma pasta própria, direto ali**, e é o que responde "já
baixei isto?" — um pacote baixado duas vezes não é rebaixado.

> O plugin já espelhou a árvore de quatro níveis do site. Medido sobre os 5.258
> pacotes do catálogo completo, isso dava caminhos de 209 caracteres na mediana
> e 333 no pior caso: **267 pacotes estouravam o limite de 260 do Windows antes
> mesmo de o ZIP abrir**, e `rglob` devolvia lista vazia em silêncio. Direto sob
> o destino, a mediana é 68 e o máximo 117.

**Atualizar catálogo** — busca a versão mais recente no repositório
[download_banco_cprm](https://github.com/blendabastos/download_banco_cprm). Se
falhar, o plugin segue com o catálogo embutido.

---

## O que está disponível

Os nomes abaixo são os que aparecem no seletor do painel. No catálogo eles têm
os rótulos do SGB — `SIG (Vetores)`, `Geoquímica-XLSX` —, que é por onde o
filtro casa.

| Tipo | Camadas | Abre no QGIS como |
|---|---:|---|
| Vetores | 1.523 | vetor |
| Mapa (PDF) | 2.062 | raster, quando for GeoPDF |
| Geoquímica — planilha | 336 | tabela — ou pontos, ver abaixo |
| KML | 301 | vetor |
| Geofísica — Geotiff | 243 | raster, sem a moldura branca |
| Geofísica — XYZ | 141 | tabela de pontos, ver abaixo |
| Nuvem de pontos (LiDAR) | 56 | nuvem de pontos |
| Ortofoto e raster | 56 | raster |
| Geoquímica — CSV | 1 | tabela — ou pontos, ver abaixo |

**643 GB** no total. Fica de fora apenas Relatório: 480 PDFs de texto, que
não pertencem a nenhuma folha e só encompridariam a árvore.

A carta em PDF cai no mesmo ramo da árvore que os vetores da folha, então quem
está olhando a folha acha a carta ali do lado.

### A carta em PDF, quando é GeoPDF

A carta do SGB costuma ser um **GeoPDF**: tem georreferença dentro, e o GDAL a
abre como raster, com CRS — nada de converter. Numa amostra aleatória de 60
cartas, **51 (85%) abriram georreferenciadas**; as outras 9 são imagem sem lugar
no mapa.

Quem decide é o GDAL, arquivo por arquivo, e não a extensão
(`pacote.pdf_georreferenciado`). Sem essa pergunta o driver PDF abriria
*qualquer* PDF como raster — um relatório de texto entraria no projeto como
imagem empilhada sobre a origem do plano. A carta sem georreferença aparece no
diálogo listada e desabilitada, com o tamanho: ela veio no pacote, e isso o
usuário precisa saber.

Fica de fora o que há de vetorial *dentro* do GeoPDF. O GDAL enxerga essas
subcamadas, mas elas variam demais para uma regra honesta: numa carta são 32
camadas de verdade (`Fusão_Geologia_X_MDT`, 4.471 feições); noutra, 196
primitivas de desenho de uma feição cada, chamadas `Group_49_Line_107`. Quem
precisar delas abre o PDF pelo *Adicionar camada* do próprio QGIS, que pergunta
quais quer.

`Geofísica — XYZ` continua sendo o único tipo que só se baixa
(`TIPOS_SO_DOWNLOAD` no `config.py`): tem caminho próprio, a conversão em
pontos.

Um arquivo também raramente é uma camada só. KML, KMZ, GeoPackage e GML
guardam quantas quiserem, e o plugin lista uma por uma: o KML de Regência traz
*Drenagem* (27 feições), *Corpos d'água* (60) e *Litologia* (23) no mesmo
arquivo. Abrir só a primeira entregava 27 de 110 e descartava o resto em
silêncio — e o KML parecia magro sem que desse para saber o que faltava.
(KML é sempre WGS 84, `EPSG:4326`, por especificação.)

Um pacote raramente é uma camada só. O SIG de Jardim do Ouro traz 16 shapefiles
em subpastas temáticas; a *Base* aerogeofísica de SD.22-Z-B-VI traz 17 GeoTIFF
(canal total, eTh, eU, K%, ternário) e 4 shapefiles. Daí o diálogo de seleção.

### Tabelas de geoquímica viram pontos

**129 dos 337 pacotes de geoquímica baixam como planilha solta**, sem o
shapefile que o SGB costuma anexar. Para esses, a coordenada só existe nas
colunas `LATITUDE`/`LONGITUDE`.

Quando o plugin detecta essas colunas, o diálogo de seleção oferece **converter
a tabela em camada de pontos** — uma por aba da planilha. O resultado é um GeoPackage gravado ao lado da
planilha — não uma camada de memória, então sobrevive ao fechar o projeto.

> **O download continua sendo um arquivo só.** As abas são visões da mesma
> planilha, abertas com `|layername=`. O único arquivo novo em disco é o
> GeoPackage de cada aba que você mandar espacializar — e ele é ignorado ao
> listar o pacote de novo, para não aparecer como camada duplicada.

O datum não é chute: o shapefile que o SGB entrega junto das mesmas análises
declara `GEOGCS["GCS_SIRGAS"]`, então o padrão é **SIRGAS 2000 (EPSG:4674)**,
alterável no seletor ao lado. Linhas sem coordenada utilizável são puladas —
célula vazia, texto no lugar de número, e `0/0`, que cairia no Golfo da Guiné.

> A leitura usa GDAL direto, não `QgsVectorLayer`: o provedor OGR do QGIS mantém
> um pool de conexões e deixava a planilha aberta depois da conversão, com o
> Windows recusando mover ou apagar a pasta.

### Filtro por lugar: a tela do mapa, ou uma cidade

A caixa **Só nesta tela** deixa na árvore apenas o que cruza a área visível do
mapa. E o campo **Ir para cidade…** aceita qualquer um dos 5.571 municípios do
Brasil: escolher um leva o mapa até lá e liga o filtro.

> **Os municípios vêm embutidos, e isso é a decisão inteira.** A tabela é
> gerada uma vez por `gerar_municipios.py`, a partir de duas rotas públicas do
> IBGE — as malhas v4 e a API de localidades —, e vai no pacote com 101 KB.
> O plugin **não chama o IBGE em tempo de execução**: buscar "Parauapebas"
> funciona num levantamento de campo, sem sinal, e não depende de um serviço
> que possa mudar de contrato. Fora isso, o plugin só fala com o GEOSGB.
>
> A rota `intrarregiao` entrega a geometria de todos os municípios numa
> requisição — 3,8 MB em 2,5 s com `qualidade=minima`. Pedir um a um seriam
> 5.571 chamadas. O bounding box a API não publica; ele sai da geometria, no
> gerador.

A busca ignora acento e caixa, e quem começa com o termo vem antes de quem
apenas o contém. O rótulo traz a UF porque **232 nomes se repetem entre
estados** — escolher "Bom Jesus" sem a sigla não diria a qual deles o mapa
iria, e o plugin prefere não adivinhar.

**O acervo não publica geometria.** Conferi as 35 colunas do catálogo completo,
inclusive as 23 que o plugin descarta — não há bounding box, centroide nem
coordenada. O RiGeo é um DSpace, repositório de documentos, e a API não expõe
nada espacial.

O que há é o **código da folha**, e ele não é rótulo arbitrário: o acervo é
indexado pela Carta Internacional ao Milionésimo, cuja malha é uma fórmula.
`SC.24` é a faixa 8°S–12°S no fuso −42°..−36°, e cada sufixo corta essa folha
em quadrantes — até 0,375° × 0,167° em `SB.21-Z-A-III-2`. São 40 linhas de
aritmética, sem tabela e sem dependência.

**A aerogeofísica não tem folha, tem projeto.** Os títulos são `1009-XYZ` e
`3065-Geotif`: um número, não uma carta. Para esses, a posição vem do
[geoportal do SGB](https://geoportal.sgb.gov.br/server/rest/services/geofisica/aerogeofisica/MapServer),
que publica a área levantada de **376 projetos** em quatro séries — 1000 (DNPM
e CPRM), 2000 (CNEN e Nuclebrás), 3000 (governamentais e privados) e 4000 (CNP
e Petrobras). O `gerar_projetos.py` consulta o serviço e reduz tudo a caixas:
9 KB no pacote.

Fonte oficial de propósito, e por duas razões. **Procedência:** o serviço
declara `copyrightText` como *Serviço Geológico do Brasil — SGB — CPRM*, o
mesmo órgão dono do acervo que o plugin baixa. **Reprodutibilidade:** quem
clonar o repositório regenera a tabela sem precisar de arquivo nenhum em disco.

A chave é `ID_PROJETO` **sozinho**, e não a soma dele com `ID_SERIE`: a série já
está dentro do número do projeto (`ID_SERIE=1000`, `ID_PROJETO=1060`). Somar os
dois casava com nada — foi assim que a primeira tentativa devolveu zero de 141.

| Tipo | Tem posição |
|---|---:|
| KML | 99,7% |
| Geofísica — Geotiff | 90,1% |
| Vetores | 85,1% |
| **Geofísica — XYZ** | **87,9%** |
| Mapa (PDF) | 76,4% |
| Geoquímica — planilha | 32,7% |
| LiDAR, ortofoto | 0% |
| **Total** | **76,8%** |

O que sobra sem posição some quando o filtro está ligado — e **o painel diz
quantos são**, porque filtro que esconde dado em silêncio é o oposto do que o
resto do plugin faz.

> Uma validação cruzada que vale registro, e há teste cobrando: o `xyz.py`
> sabe, de ter lido o arquivo, que o projeto 1009 grava coordenada em
> `grau.minuto.segundo`, e que `-15.27.08.20` é uma latitude dele. Essa
> latitude cai dentro da caixa que a camada índice do SGB dá para o mesmo
> projeto. Duas fontes que nunca se falaram, concordando sobre o mesmo lugar.

> A extensão é convertida do CRS do projeto para `EPSG:4326` antes de comparar.
> Sem isso, um projeto em UTM entregaria uma extensão em **metros** comparada
> com graus — nada cruzaria, e a árvore ficaria vazia sem explicação. Há teste
> cobrando, com um `QgsMapCanvas` de verdade em SIRGAS 2000 / UTM 23S.

Dois defeitos que os testes pegaram enquanto isto era escrito. O primeiro:
`Folha SC.24 Sergipe` virava `SC.24-SE`, porque o *Se* de Sergipe casava com o
quadrante sudeste de 1:25.000 — a caixa saía 32× menor que a folha real. O
segundo é do próprio teste: `QgsMapCanvas.setExtent` **estica** a caixa até a
proporção do widget, então pedir 10°×10° devolvia 35°×10°, e a asserção
acusava folha vizinha legítima como erro.

#### E um terceiro, que os testes não pegaram

A folha de 1:100.000 estava em **2 colunas × 3 linhas**, e o certo é **3 × 2**.
A conta decide: a folha de 1:250.000 tem 1°30′ × 1°, e cada folha de 1:100.000
tem 30′ × 30′ — logo 1,5° ÷ 30′ = 3 colunas e 1° ÷ 30′ = 2 linhas.

O sintoma apareceu no uso, não em teste: filtrando por **Magé (RJ)**, o plugin
trazia a carta *Casimiro de Abreu*, que fica a uns 60 km dali, e escondia a
*Baía de Guanabara*, que é a folha de Magé. Área somada idêntica, posição
trocada.

**Os dois testes que existiam passavam.** Um conferia a área somada das seis
folhas — igual nos dois arranjos. O outro conferia as dimensões, contra o
número que eu mesmo havia calculado da implementação errada. Teste escrito a
partir do código confirma o código, não a especificação.

O teste que vale fixa 30′ × 30′, que é o que a norma diz. E há um segundo, que
amarra a malha ao mundo: cruza **325 cartas do catálogo com a caixa do
município homônimo** na tabela do IBGE.

Mas a pergunta dele é de **posição, não de continência**. Exigir que a folha
*contenha* o município homônimo seria exigir do acervo algo que a norma não
promete — o nome da folha é rótulo, e o filtro trabalha com espaço geográfico.
Cabedelo (PB) fica 0,03° ao sul da folha que leva seu nome, e isso não é
defeito de ninguém. Então o que se mede é a **distância** entre a folha e o
lugar que a nomeia:

| arranjo | mediana | **p90** |
|---|---:|---:|
| 2 × 3 (errado) | 0,000 | **0,556** |
| **3 × 2 (certo)** | 0,000 | **0,000** |

A mediana não separa os dois arranjos; o p90 separa com folga. A cauda é ruído
de **nome**, não de geometria — há *Rio Pardo* em mais de um estado, e a folha
de um não fica perto do município do outro. Por isso o teste olha o percentil
90 e ignora o topo.

### A moldura branca dos GeoTIFF some sozinha

Os GeoTIFF da geofísica do SGB são **imagens já coloridas, não grades**: 3
bandas RGB de 8 bits, sem `nodata`, sem máscara, sem alfa. O fundo do
levantamento é pixel branco puro — e ocupa de **33% a 49%** da imagem, chegando
no QGIS como um retângulo branco que tapa o mapa embaixo.

O plugin acrescenta a quarta banda, a de alfa, automaticamente ao baixar. Não há
caixa para marcar: não existe caso em que a moldura branca seja desejável.

**O que não funciona é dizer "branco é fundo".** Rotulando os componentes
conexos do branco nos 19 arquivos dos projetos 1017 e 1030:

| | branco | componentes | ilhas cercadas por dado |
|---|---:|---:|---|
| 15 arquivos | 33–48% | 1 | nenhuma |
| `1017_1DV`, `ASA`, `MAG` | 43,8% | 14 | 4 ilhas, 108 px |
| **`1017_TERNARIO`** | 48,7% | 25 | **24 ilhas, 3.231 px** |
| **`1030_TERNARIO_RGB`** | 39,7% | 50 | **49 ilhas, 700 px** |

Numa composição ternária, branco significa **K, Th e U altos ao mesmo tempo** —
é dado, e dos bons. Tratar cor como fundo furaria o mapa exatamente em cima das
anomalias. A regra é outra: **é fundo o branco que alcança a moldura**.
Preenchimento a partir da borda, vizinhança de 4 — o fundo não atravessa um
encontro diagonal de um pixel, então na dúvida o pixel fica opaco.

O custo surpreende para baixo. Medido nos 19 arquivos:

| | |
|---|---|
| tempo | **0,12 a 0,31 s** por arquivo |
| tamanho | **32,2 MB → 7,3 MB**, 23% do original |
| RGB | byte a byte idêntico; georreferência e projeção também |
| QGIS | usa o alfa sozinho, sem configurar nada |

O arquivo **encolhe** porque DEFLATE com preditor ganha do PACKBITS original com
sobra, mesmo carregando uma banda a mais. É o que torna defensável reescrever um
arquivo do usuário sem perguntar: o dado não muda e passa a ocupar menos.

> O preenchimento é numpy puro, não `scipy.ndimage.label`. Confere exatamente
> com o scipy nos 19 arquivos, e o plugin continua sem nenhuma dependência
> externa — nem toda instalação do QGIS traz scipy.

### XYZ aerogeofísico vira tabela de pontos

Os 126 projetos aerogeofísicos são o maior acervo de dados de aquisição que o
SGB publica: **248 GB de `.xyz` descompactado em 677 arquivos**, algo perto de
**1,4 bilhão de pontos**. O QGIS não abre o formato Geosoft, e até a versão 0.9
o plugin apenas deixava os arquivos em disco.

Agora, depois de baixar, o plugin oferece converter cada arquivo em uma tabela
de pontos: uma linha por medida, com a linha de voo, o número do voo, a data e
todos os canais. As linhas de controle (`Tie`) entram junto, com uma coluna
dizendo qual é — são o mesmo levantamento.

**O que não se junta é `Mag` com `Gama`.** No projeto 3065 são 3.153.422 contra
315.339 pontos, exatamente 10:1, porque a amostragem é de 0,1 s contra 1 s.
Fundir produziria 90% de células vazias. Cada arquivo vira uma tabela.

#### As cinco formas de gravar coordenada

Levantado arquivo por arquivo nos 126 projetos. **Todos têm coordenada** — o
que falta em 11 deles é o nome da coluna, não o número:

| forma | como é reconhecida | projetos |
|---|---|---:|
| grau decimal, colunas nomeadas | `LONGITUDE`/`LATITUDE` | 108 |
| UTM, colunas nomeadas | `UTME`/`UTMN`, `X`/`Y` | 106 |
| UTM nas colunas 0 e 1, sem nome | faixa de valores | 7 |
| Mercator Equatorial, esfera Clarke 1880 | faixa de valores | 3 |
| `grau.minuto.segundo`, latitude primeiro | formato dos valores | 1 |

A última é o projeto 1009: `-15.27.08.20` são 15° 27′ 08,20″ **sul**, e a
latitude vem antes da longitude, ao contrário de todos os outros. Um `float()`
ingênuo levanta `ValueError` ali — falha barulhenta em vez de coordenada
errada.

A penúltima não tem código EPSG. Está descrita em prosa dentro de um `.doc` do
Word que veio no pacote do projeto 1014, nas palavras do próprio SGB: *"esfera
Clarke 1880, com raio de 6378249,145 m; meridiano de origem 0º"*.

#### De onde sai o CRS

Quatro fontes, nesta ordem de confiança:

1. **O próprio XYZ** — `/COORDENADAS UTM ELIPSÓIDE INTERNACIONAL HAYFORD 1910 MC= -39`, em 34 projetos
2. **O leiame do pacote** — o 1054 diz `Datum SAD 29 - UTM zona 23S`
3. **Um arquivo irmão** — o `1114_Cruzamentos.XYZ` não declara fuso, mas o `1114_MagLine.XYZ` ao lado traz X, Y, `LONGITUDE` e `LATITUDE` na mesma linha; a longitude diz o fuso
4. **O nome do arquivo** — `SB22XC2G.XYZ` é folha do IBGE, e o `22` *é* o fuso

Quando nada disso resolve, a tela pede o fuso em vez de chutar.

#### Nada é deduzido em silêncio

A tela mostra **de onde veio cada decisão**, e o plugin **confere a extensão
convertida** contra o Brasil e, quando o leiame traz a caixa de coordenadas do
projeto, contra ela também. Se não bater, recusa.

Isso existe porque errar o CRS produz um arquivo que abre, desenha e está
errado. Aconteceu durante o desenvolvimento, duas vezes: uma latitude 283 por
coluna adivinhada, e uma latitude quase certa pega na coluna vizinha errada —
essa segunda ficaria *dentro* do Brasil e passaria pela verificação. O
desempate é a convenção do Geosoft, longitude antes de latitude, e há teste
cobrando.

#### Custo, medido

Convertendo o `Mag.XYZ` do projeto 3065 (570 MB) com o GDAL do QGIS 4.0.1:

| | |
|---|---|
| taxa | **38,5 mil pontos/s** — 3.153.422 pontos em 82 s |
| memória | **~120 MB, constante** — não cresce com a contagem de pontos |
| maior projeto (1112) | 12,4 GB → ~68 milhões de pontos, **~30 min** |

E o tamanho do arquivo, medido no `1117_MagLine.XYZ`, de 1,79 GB:

| | |
|---|---|
| GeoPackage | 2,61 GB |
| **GeoParquet** | **460 MB** — 5,7× menor, mesmo tempo de escrita |

Daí o GeoParquet ser o padrão; o QGIS 4.0.1 o abre nativamente, 315 mil feições
em 0,05 s. O GeoPackage fica na lista para quem precisa levar o dado ao ArcGIS
ou ao QGIS 3.

> A taxa é medida no caminho que o usuário percorre de verdade — GeoParquet,
> com o progresso ligado. A primeira versão usava os 52 mil/s da escrita em
> GeoPackage sem índice e prometia um terço a menos de espera. Errar para menos
> é pior: quem espera 10 minutos por uma barra que prometia 5 conclui que
> travou.

A conversão roda em `QgsTask`, com **barra de progresso no topo do mapa** —
qual arquivo, quantos pontos, e o botão de cancelar — atualizada umas duas
vezes por segundo. A tela estima pontos e tempo **antes** de começar.

#### O que fica em disco

Cada XYZ gera uma tabela ao lado dele, e **converter de novo apaga a saída
anterior, em qualquer formato**. Sem isso, converter em GeoParquet e depois em
GeoPackage deixava as duas na pasta — o projeto 1117 chegou a 5,3 GB, com o
mesmo dado três vezes: o XYZ original de 1,79 GB, o `.parquet` de 460 MB e o
`.gpkg` de 2,61 GB, os dois últimos oferecidos como camada.

A tela tem uma coluna dizendo o que já existe em disco, e uma opção de **apagar
o XYZ original depois de converter**, com o espaço que isso libera. Ela começa
desmarcada, e o original só é apagado quando a verificação não acusou nada: se
a leitura estiver errada, o arquivo bruto é o único jeito de descobrir.

---

## O que o plugin resolve

Cada um destes é um problema real do acervo, encontrado ao construir o catálogo
ou ao testar o plugin:

**Nem tudo é ZIP, e nem todo ZIP é pacote.** 112 arquivos são `.las`/`.jp2`
soltos e 129 são planilhas. Mas um `.xlsx` *é* um ZIP: `is_zipfile()` diz sim, e
extraí-lo espalhava `[Content_Types].xml`, `_rels/` e `xl/` na pasta — depois
apagando o original, tratado como "zip já extraído". Por isso a regra é uma
**lista de permissão** (`.zip` apenas), não de negação: o SGB publica planilha
XLSX com nome terminando em `.xls`, e nenhuma lista de negação antecipa isso.

**Planilha tem abas.** A tabela do ARIM Seridó tem `Contagem` (1 linha, só um
resumo), `Mineralometria` (169) e `Sedimento de corrente` (197). Ler só a
primeira entregava a linha de resumo e escondia as 366 amostras. Cada aba vira
uma camada.

**Link morto do RiGeo responde HTTP 200**, com a página do DSpace no corpo. Sem
checar, viraria um `.zip` de 3 KB que falha ao abrir sem explicação.

**Download cortado vira arquivo truncado.** Os bytes recebidos são comparados
com o `Content-Length` antes de promover o `.parcial`.

**Acento no nome dentro do ZIP.** Os pacotes do SGB não marcam a flag UTF-8, e o
tratamento ingênuo corrompe os nomes — nos dois sentidos. Ver
[o caso dos acentos](#o-caso-dos-acentos).

**Atributos em latin-1.** A maioria dos pacotes traz `.cpg` declarando a
codificação, mas nem todos, e o `.dbf` do SGB costuma ser latin-1. Sem tratar,
`Formação` chega como `FormaÃ§Ã£o`.

**Caminhos longos.** Espelhar a árvore do site dava mediana de 209 caracteres e
máximo de 333: **267 dos 5.258 pacotes estouravam os 260 do Windows antes de o
ZIP abrir**, e `rglob` devolvia lista vazia em silêncio — o plugin dizia "nenhum
arquivo que o QGIS abra" com 13 arquivos na pasta. Hoje o pacote fica direto sob
o destino (mediana 68), e toda operação ainda usa `\\?\` para o que sobra.

**Clique acidental não baixa 1,6 GB.** O download exige confirmação explícita.

**XYZ do Geosoft não tem um formato, tem cinco.** Levantado arquivo por arquivo
nos 126 projetos: de 4 a 37 colunas, rótulo de linha escrito `Line`, `LINE` ou
`LI`, e 11 projetos sem nome de coluna nenhum. **Todos têm coordenada** — falta
o nome, não o número. Ver
[a seção sobre XYZ](#xyz-aerogeofísico-vira-tabela-de-pontos).

**Número plausível é pior que erro.** O `float()` do Python aceita `"nan"` e
`"inf"` sem reclamar: um NaN na coluna de coordenada viraria geometria em NaN e
levaria junto a extensão da camada — inclusive a verificação que existe para
pegar coordenada errada. E `"-15.99.99"`, que tem 99 minutos e 99 segundos,
virava −16,6775: dentro do Brasil, a uns 75 km do lugar certo. Os dois são
recusados como ausentes.

**O nome do SGB nem sempre serve de rótulo.** O catálogo chama um tipo de
`SIG (Vetores)` — e isso sugere que o resto não é SIG, quando raster, LiDAR e
tabela também são. Na tela aparece **Vetores**; o valor gravado continua sendo
o do SGB, porque é por ele que o filtro casa. A tradução mora em
`config.ROTULO_TIPO`.

**O manifesto é ASCII puro.** O `metadata.txt` já apareceu no Gerenciador de
Complementos como *"ServiÃ§o GeolÃ³gico"* — os acentos gravados duas vezes.
Corrigir a codificação resolveu o arquivo, mas quem lê o manifesto não é o
nosso código, e não há como verificar daqui como cada QGIS o interpreta. ASCII
tira a variável do caminho, e um teste recusa qualquer acento que volte.

**Um só jeito de perguntar "já baixei isto?".** A resposta mora em
`pacote.pasta_tem_conteudo`, e só lá. Havia quatro cópias da mesma linha — na
ficha do painel, no diálogo de download, na tarefa de baixar e numa função do
baixador que ninguém chamava. Iguais hoje, sem garantia de continuarem iguais;
a que esquecesse o prefixo de caminho longo diria "não baixei" para um pacote
que está em disco, e o usuário rebaixaria 1,6 GB. Um teste lê o código.

**Sem CRS, o filtro recusa em vez de supor.** Se o projeto está com um sistema
de coordenadas inválido, não dá para saber a unidade da extensão do mapa.
Seguir em frente seria supor grau — e num projeto em metros isso devolveria uma
lista errada, calada. O painel diz que não conseguiu ler a extensão e mostra
tudo.

**Um só jeito de criar pasta.** Toda escrita passa por `pacote.criar_pasta`,
que sempre usa o prefixo de caminho longo. Havia um `mkdir` cru ao lado de um
`open` com prefixo, na mesma função — o arquivo seria gravado e a pasta que o
abriga, não. Um teste lê o código, não o comportamento, porque a falha só
acontece no `qgis-bin.exe`: o `python-qgis.bat`, onde os testes rodam, entende
caminho longo e esconderia o defeito.

**Coordenada errada é pior que conversão recusada.** Errar o CRS produz um
arquivo que abre, desenha e está errado. O plugin mostra de onde deduziu cada
decisão e confere a extensão contra o Brasil — e contra a caixa de coordenadas
do leiame, quando o pacote traz uma.

---

## Arquitetura

```
acervo_cprm/
├── __init__.py           classFactory
├── metadata.txt          manifesto (qgisMinimumVersion=4.0)
├── plugin.py             ação na barra, ciclo de vida do painel
├── painel.py             QDockWidget: árvore, busca, ficha, ações
├── dialogo_download.py   confirmação antes de transferir
├── dialogo_camadas.py    seleção do que entra no projeto
├── dialogo_xyz.py        o que converter, e por que o plugin leu assim
├── baixador.py           QgsTask: download, verificação, extração
├── tarefa_xyz.py         QgsTask: conversão do XYZ, com progresso
├── xyz.py                o leitor de XYZ: dialetos, coordenada, CRS
├── alfa.py               tira a moldura branca dos GeoTIFF da geofísica
├── pacote.py             descompactação, inspeção, adição ao projeto
├── catalogo.py           leitura do catálogo, árvore, nomes seguros
├── folhas.py             onde cada camada fica, pela malha do IBGE
├── municipios.py         busca por cidade, offline
├── projetos.py           área dos projetos, do geoportal do SGB
├── config.py             preferências e as listas de tipos/extensões
└── dados/
    ├── catalogo_sig.csv.gz   174 KB, 4.719 camadas
    ├── municipios.csv.gz     101 KB, 5.571 municípios do IBGE
    └── projetos.csv.gz         9 KB, 376 projetos aerogeofísicos
```

`catalogo.py`, `folhas.py`, `municipios.py`, `projetos.py`, `xyz.py` e a maior
parte de `pacote.py` **não importam Qt**, então rodam em teste puro. Os diálogos e o painel são só apresentação.

`xyz.py` é o módulo mais denso do plugin, e de propósito: toda a decisão sobre
dialeto, coordenada e CRS mora nele, sem Qt e sem disco, o que permitiu validá-lo
contra os 120 projetos reais antes de existir qualquer tela.

Decisões que valem registro:

**Download em `QgsTask`.** O maior pacote tem 1,6 GB. Baixar na thread da
interface congelaria o QGIS.

**Rede via `QgsNetworkAccessManager`, não `urllib`.** O NAM respeita o proxy, os
certificados e o timeout configurados no QGIS. Numa rede institucional, `urllib`
falharia sem explicação.

**`config.TIPOS_INCLUIDOS` é fonte única.** O gerador do catálogo filtra por ela,
o painel monta o seletor com ela, e um teste falha se as pontas divergirem.

**Análise antes de conversão, sempre.** `xyz.analisar()` lê 4.000 linhas e já
verifica a extensão resultante. Converter 12,4 GB para só então descobrir que o
fuso estava errado seriam 30 minutos perdidos — e o usuário só perceberia se
olhasse o mapa.

**A `QgsTask` é destruída pelo gerenciador.** Guardar a referência e chamar
`isCanceled()` depois levanta `wrapped C/C++ object has been deleted` — era o que
quebrava o segundo download da sessão. A limpeza tolera isso, e o cálculo de
caminho virou função pura, sem instanciar tarefa à toa.

### O caso dos acentos

O `zipfile` decodifica nomes como **cp437** quando o ZIP não marca a flag UTF-8
(bit `0x800`) — e os pacotes do SGB não marcam. Há dois casos, e confundi-los
corrompe nome que estava bom:

| Caso | Bytes no ZIP | cp437 dá | Ação correta |
|---|---|---|---|
| cp437 de verdade | `Geol\xa2gica` | `Geológica` ✔ | não mexer |
| UTF-8 sem flag | `Geol\xc3\xb3gica` | `Geol├│gica` ✘ | reconstruir |

O KML da folha Regência é o primeiro caso: `0xA2` em cp437 **é** `ó`, e o
`zipfile` já acerta. Uma primeira versão deste plugin tentava re-decodificar com
cp1252 e transformava esse `ó` correto em `¢`.

A regra implementada: só substituir quando a decodificação UTF-8 **tiver
sucesso**. Sequência multibyte válida não acontece por acaso. Qualquer outro
palpite — cp1252, latin-1 — sempre "funciona" e destruiria o primeiro caso.

---

## O catálogo

O plugin **não conversa com a API do GEOSGB**. O catálogo já traz o
`link_download` verificado, então resta baixar, descompactar e adicionar. Toda a
complexidade de resolver link (`BASEURL`, RiGeo, candidatos alternativos) ficou
congelada no projeto
[download_banco_cprm](https://github.com/blendabastos/download_banco_cprm).

```powershell
python gerar_catalogo.py
```

Lê o `catalogo.csv` daquele projeto, filtra por `config.TIPOS_INCLUIDOS` e
`status=ok`, mantém 12 das 35 colunas e grava comprimido. De 5,3 MB para
**102 KB**.

| Coluna | Uso no plugin |
|---|---|
| `id`, `titulo` | identificação e rótulo na árvore |
| `nivel_1`…`nivel_4` | a hierarquia que vira a árvore |
| `tipo` | filtro e escolha do provedor |
| `nome_arquivo`, `formato` | nome do arquivo em disco |
| `tamanho_bytes` | exibição e verificação do download |
| `link_download` | o link direto, já verificado |
| `origem` | `rigeo` ou `gd`, para diagnóstico |

Esta é a única ponte entre os dois projetos: um arquivo de dados versionado, não
código compartilhado.

---

## Testes

```powershell
$q = "C:\Program Files\QGIS 4.0.1\bin\python-qgis.bat"

& $q testes\test_plugin.py              # lógica + um download real
& $q testes\test_plugin.py --sem-rede   # sem tocar a rede
& $q testes\test_xyz.py                 # o leitor de XYZ aerogeofísico
& $q testes\test_alfa.py                # a banda alfa dos GeoTIFF
& $q testes\test_carga.py               # o plugin com interface de verdade
```

São **276 testes** — 78 de lógica, 48 do leitor de XYZ, 27 da malha do IBGE,
19 dos municípios, 10 dos projetos, 20 da banda alfa e 74 com interface de
verdade —, rodando dentro do QGIS e não contra dublês: é o único jeito de pegar
enum renomeado no PyQt6 ou sinal que não existe mais.

`test_xyz.py` usa recortes reais dos arquivos do SGB, não invenção. Quase todo
teste ali trava um defeito que existiu de verdade durante o desenvolvimento: o
cabeçalho lido da primeira linha em vez da última, o `\b` de regex que nunca
casava em `SB22XC2G`, a coluna vizinha errada tomada por latitude.

`test_plugin.py` termina baixando o menor SIG real do acervo (66 KB) e
verificando que as 7 camadas abrem com geometria e CRS corretos.

`test_carga.py` sobe o plugin com um `QgisInterface` falso e uma `QMainWindow`
real. Vários testes existem por causa de um bug que apareceu no uso: que
selecionar não baixa, que cancelar não baixa, que uma `QgsTask` já destruída não
derruba o fluxo.

> Um detalhe aprendido: testar o fluxo de download **através** do diálogo modal
> não prova nada — `exec()` num ambiente sem interface devolve o que quiser. Os
> testes substituem o diálogo por um dublê que aceita ou cancela sob controle.

---

## Limitações

**Sem simbologia.** Os pacotes trazem arquivos `.lyr`, formato fechado do
ArcGIS, que o QGIS não lê. As camadas chegam com a cor padrão. A informação de
estilo não existe em formato aberto dentro do pacote.

**XYZ depende de dedução.** O QGIS não abre o formato Geosoft, então o plugin
converte (ver acima). Em 11 dos 126 projetos não há nome de coluna nenhum e a
leitura sai de faixa de valores; em 3 o CRS é um Mercator sem código EPSG. A
tela mostra de onde veio cada decisão e confere a extensão antes de gravar, mas
quem conhece o dado deve olhar.

**O filtro espacial alcança 71% do acervo.** A posição sai do código de folha
no título, porque o catálogo não publica geometria — conferido nas 35 colunas
do catálogo completo, inclusive as 23 que o plugin descarta. Os 29% restantes
são XYZ, LiDAR e ortofoto, indexados por projeto e não por folha: eles somem
quando o filtro está ligado, e o painel diz quantos são.

**Catálogo tem validade.** Os links foram verificados quando o catálogo foi
gerado. Se um falhar, *Atualizar catálogo* costuma resolver.

**QGIS 4 apenas.** O código usa a API do PyQt6. Portar para 3.x é mecânico, mas
não foi feito.

---

## Licença

MIT. Os dados baixados são do Serviço Geológico do Brasil — consulte os termos
de uso do [GEOSGB](https://geosgb.sgb.gov.br/).
