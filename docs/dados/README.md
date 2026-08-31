# Dados de referência

## BNCC da Computação

Duas peças, e as duas vivem no repositório:

- `apps/referenciais/fixtures/bncc_computacao.json`: o referencial, os três eixos
  (Pensamento Computacional, Mundo Digital, Cultura Digital) e as sete
  competências específicas do Ensino Médio.
- `docs/dados/bncc_computacao_habilidades.csv`: as 120 habilidades, transcritas do
  Complemento à BNCC (Resolução CNE/CEB nº 1/2022).

Para carregar:

    python manage.py loaddata bncc_computacao
    python manage.py importar_competencias --referencial BNCC-COMP --csv docs/dados/bncc_computacao_habilidades.csv

Importar de novo atualiza as descrições sem duplicar nada.

### O que foi transcrito, e o que não

| Etapa | Códigos | Quantidade |
|---|---|---|
| Educação Infantil | `EI03CO01` a `EI03CO11` | 11 |
| 1º ano | `EF01CO01` a `EF01CO07` | 7 |
| 2º ano | `EF02CO01` a `EF02CO06` | 6 |
| 3º ano | `EF03CO01` a `EF03CO09` | 9 |
| 4º ano | `EF04CO01` a `EF04CO08` | 8 |
| 5º ano | `EF05CO01` a `EF05CO11` | 11 |
| 6º ano | `EF06CO01` a `EF06CO10` | 10 |
| 7º ano | `EF07CO01` a `EF07CO11` | 11 |
| 8º ano | `EF08CO01` a `EF08CO11` | 11 |
| 9º ano | `EF09CO01` a `EF09CO10` | 10 |
| Ensino Médio | `EM13CO01` a `EM13CO26` | 26 |
| **Total** | | **120** |

Esses números estão em `apps/referenciais/tests/test_bncc.py`, contados no
documento e não no arquivo. É de propósito: um CSV pela metade importa limpo, a
tela mostra menos habilidades e ninguém percebe. Se o teste da contagem reprovar,
**falta linha no CSV**; não ajuste os números.

**Os blocos consolidados não entram.** O documento traz, além das habilidades ano
a ano, dois reagrupamentos: "POR ETAPA - 1º ao 5º" (`EF15CO`, 9) e
"POR ETAPA - 6º ao 9º" (`EF69CO`, 12). Eles cobrem o mesmo conteúdo com outro
código, para escolas que não separam por ano. Importar os dois faria cada
habilidade aparecer duas vezes na tela, com códigos diferentes, e a equipe não
teria como saber qual escolher.

### Onde a transcrição se afasta do impresso

Três pontos, registrados aqui porque **nunca se inventa código da BNCC** e
divergência resolvida em silêncio é a mesma coisa que invenção.

**1. `EF05CO011` virou `EF05CO11`.** O PDF imprime a última habilidade do 5º ano
com três dígitos; as outras 119 têm dois. É erro de diagramação: um código com
três dígitos não casa com nenhuma referência oficial.
`test_codigo_do_quinto_ano_normalizado` impede que volte sem que se perceba.

**2. As sete competências específicas do Ensino Médio têm rótulo curto.** O texto
oficial de cada uma é um parágrafo inteiro, e `Categoria.nome` tem 120 caracteres
(um parágrafo num select é ilegível de qualquer forma). O `nome` é redação nossa;
o **texto oficial completo está em `Categoria.descricao`**, na fixture, e é o que
a tela mostra ao passar o mouse. Os rótulos são:

| Rótulo | Habilidades |
|---|---|
| Possibilidades e limites da Computação | `EM13CO01` a `EM13CO06` |
| Análise crítica de artefatos computacionais | `EM13CO07`, `EM13CO08` |
| Técnicas computacionais para o mundo contemporâneo | `EM13CO09` a `EM13CO11` |
| Construção de conhecimento e artefatos | `EM13CO12` a `EM13CO16` |
| Projetos e decisões socialmente responsáveis | `EM13CO17`, `EM13CO18` |
| Expressão e partilha com tecnologias | `EM13CO19` a `EM13CO22` |
| Ação pessoal e coletiva com responsabilidade | `EM13CO23` a `EM13CO26` |

**3. A quarta competência do Médio aparece duas vezes no documento, com
redações diferentes.** Na lista de competências da etapa lê-se "produzindo
conteúdos e artefatos de forma criativa, com respeito às questões éticas e
legais"; no cabeçalho da tabela de habilidades, "produzindo informação e/ou
artefatos de forma criativa, com respeito às questões legais". A fixture guarda a
primeira, por ser a da seção que define as competências.

### Estrutura do CSV

Colunas: `codigo,descricao,etapa,categoria,objeto_conhecimento`.

- `etapa` usa o vocabulário do **referencial** (`EI`, `EF01` a `EF09`, `EM`), que
  não é o do curso: as habilidades do Ensino Médio valem para os três anos de uma
  vez. `apps.referenciais.choices.etapa_do_referencial()` traduz um no outro.
- `categoria` é o eixo, da Educação Infantil ao 9º ano, e o rótulo curto da
  competência específica no Ensino Médio.
- `objeto_conhecimento` é o nível que o Ensino Fundamental põe entre o eixo e a
  habilidade. Vem vazio na Educação Infantil e no Ensino Médio, que não o têm, e é
  coluna opcional no importador: outro referencial pode não ter esse nível.
- `descricao` não repete o código, que já é a primeira coluna.
