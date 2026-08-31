# Plano 7: a BNCC por etapa na ficha do curso

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Escolhida a BNCC e a etapa, a ficha do curso oferece os eixos e as
habilidades daquele ano; sem referencial, esse bloco não existe.

**Architecture:** Nenhum modelo novo. `Categoria` já é agrupamento genérico e
recebe as sete competências específicas do Ensino Médio ao lado dos três eixos;
`Competencia` ganha um campo de texto para o objeto de conhecimento e um
vocabulário de etapa próprio. As 120 habilidades entram por CSV, pelo comando que
já existe, com a contagem por etapa presa em teste. A tela filtra por HTMX.

**Tech Stack:** Django 5.2, Python 3.13, PostgreSQL, pytest + pytest-django, HTMX.

**Spec:** `docs/superpowers/specs/2026-08-25-integrasi-design.md`, seção 4.2
(atualizada no commit `d07e8e3`) e seção 15.

**Fonte dos dados:** Computação: Complemento à BNCC (Resolução CNE/CEB nº 1/2022),
PDF fornecido pelo responsável pelo projeto.

## Global Constraints

- **Nunca invente códigos de habilidade da BNCC.** Toda linha do CSV vem
  transcrita do documento. Onde a transcrição divergir do impresso, a divergência
  é registrada em `docs/dados/README.md`, nunca resolvida em silêncio.
- **Nenhuma tela, filtro ou relatório pode pressupor BNCC.** Curso sem referencial
  é de primeira classe.
- `save()` chama `full_clean()`, exceto quando vem `update_fields`.
- Só `services.py` altera campo de status.
- Checagem de permissão em `cursos/permissions.py`, chamada pelos serviços.
- Texto de interface em português acentuado; valores gravados sem acento e nunca
  alterados por passada de texto.
- **Nada de travessão** em lugar nenhum do repositório: nem o caractere em-dash
  (U+2014), nem a entidade HTML equivalente. `tests/test_estilo.py` reprova.
- JS próprio só onde HTMX não alcança. Esta tela é HTMX.
- TDD: o teste que falha vem primeiro.

## Como provar que uma regra está presa

Ao terminar cada tarefa, **comite**, depois apague **uma guarda de cada vez** e
rode a suíte. Se nada ficar vermelho, escreva o teste antes de restaurar. Dois
avisos que já custaram caro neste projeto:

- **Guarda de view mascarada pelo serviço**: toda guarda de view precisa de um
  caminho onde responda sozinha (um GET, um id inexistente).
- **`git checkout` leva junto o que não foi commitado.** Comite antes de mutilar.

Um aviso próprio desta tarefa: **dado ausente não levanta exceção.** Um CSV pela
metade importa limpo, a tela mostra menos habilidades e ninguém percebe. É por
isso que a contagem por etapa é teste, com números lidos do PDF e não do arquivo.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Tarefa |
|---|---|---|
| `apps/referenciais/choices.py` | `ETAPAS_REFERENCIAL`, `etapa_do_referencial`, `rotulo_da_competencia` | 1 |
| `apps/referenciais/models.py` | `Categoria.descricao`, `Competencia.objeto_conhecimento`, `Referencial.organiza_por_etapa` | 1 |
| `apps/referenciais/fixtures/bncc_computacao.json` | referencial, 3 eixos e 7 competências específicas | 2 |
| `docs/dados/bncc_computacao_habilidades.csv` | as 120 habilidades transcritas | 2 |
| `apps/referenciais/management/commands/importar_competencias.py` | coluna opcional `objeto_conhecimento` | 2 |
| `apps/cursos/views/professor.py` | o bloco de habilidades por HTMX | 3 |
| `templates/cursos/_habilidades.html` | o bloco em si | 3 |
| `apps/cursos/validacoes.py` | referencial por etapa exige etapa | 4 |

---

### Task 1: o modelo acomoda a BNCC como ela é

**Files:**
- Modify: `apps/referenciais/choices.py`
- Modify: `apps/referenciais/models.py`
- Create: `apps/referenciais/migrations/0002_bncc_por_etapa.py` (gerada)
- Test: `apps/referenciais/tests/test_models.py`

**Interfaces:**
- Produces: `choices.ETAPAS_REFERENCIAL`;
  `choices.etapa_do_referencial(etapa_ano) -> str`;
  `choices.rotulo_da_competencia(etapa, plural=False) -> str`;
  `Categoria.descricao`; `Competencia.objeto_conhecimento`;
  `Referencial.organiza_por_etapa -> bool`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescente a `apps/referenciais/tests/test_models.py`:

```python
def test_etapa_do_curso_vira_etapa_do_referencial():
    """As habilidades do Medio (EM13CO) valem para os tres anos de uma vez, entao
    os tres anos do curso apontam para a mesma etapa do referencial."""
    from apps.referenciais.choices import etapa_do_referencial

    assert etapa_do_referencial("EM01") == "EM"
    assert etapa_do_referencial("EM02") == "EM"
    assert etapa_do_referencial("EM03") == "EM"


def test_etapas_do_fundamental_e_da_infantil_passam_direto():
    """Prende o outro lado: so o Medio e agregado. Sem este par, um
    `return "EM"` incondicional passaria no teste de cima."""
    from apps.referenciais.choices import etapa_do_referencial

    assert etapa_do_referencial("EF05") == "EF05"
    assert etapa_do_referencial("EI") == "EI"


def test_curso_sem_etapa_nao_tem_etapa_de_referencial():
    """Curso comunitario nao tem etapa_ano. Devolver "" e o que deixa a tela
    mostrar lista vazia em vez de estourar."""
    from apps.referenciais.choices import etapa_do_referencial

    assert etapa_do_referencial("") == ""
    assert etapa_do_referencial(None) == ""


def test_educacao_infantil_chama_de_objetivo_de_aprendizagem():
    """O documento usa dois termos, e a tela precisa usar o da etapa (spec 4.2)."""
    from apps.referenciais.choices import rotulo_da_competencia

    assert rotulo_da_competencia("EI") == "objetivo de aprendizagem"
    assert rotulo_da_competencia("EI", plural=True) == "objetivos de aprendizagem"


def test_do_primeiro_ano_em_diante_chama_de_habilidade():
    from apps.referenciais.choices import rotulo_da_competencia

    assert rotulo_da_competencia("EF01") == "habilidade"
    assert rotulo_da_competencia("EM", plural=True) == "habilidades"


@pytest.mark.django_db
def test_referencial_sem_competencias_nao_organiza_por_etapa():
    """A pergunta e sobre o DADO, e nao sobre a sigla: nenhuma tela pode
    pressupor BNCC (spec 4.2). Referencial recem-criado, sem CSV importado
    ainda, nao pode exigir etapa de curso nenhum."""
    referencial = Referencial.objects.create(nome="Vazio", sigla="VAZIO")
    assert referencial.organiza_por_etapa is False
```

O teste de que um referencial **com** competências organiza por etapa vem no Step
5, depois que houver como criar uma competência com a etapa nova.

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/referenciais/tests/test_models.py -v`
Expected: FAIL, `ImportError` para `etapa_do_referencial` e `AttributeError`
para `organiza_por_etapa`.

- [ ] **Step 3: O vocabulário de etapa do referencial**

Acrescente a `apps/referenciais/choices.py`:

```python
# Etapas como a BNCC organiza as habilidades, que NAO sao as do curso.
#
# O curso e proposto para um ano ("EM02"), mas as habilidades do Ensino Medio
# valem para os tres anos de uma vez ("EM13CO01"). Forcar o mesmo vocabulario nos
# dois obrigaria a gravar cada habilidade do Medio tres vezes, com o mesmo codigo,
# o que a unicidade de (referencial, codigo) nem permitiria.
ETAPAS_REFERENCIAL = [
    ("EI", "Educação Infantil"),
    ("EF01", "1º ano do Ensino Fundamental"),
    ("EF02", "2º ano do Ensino Fundamental"),
    ("EF03", "3º ano do Ensino Fundamental"),
    ("EF04", "4º ano do Ensino Fundamental"),
    ("EF05", "5º ano do Ensino Fundamental"),
    ("EF06", "6º ano do Ensino Fundamental"),
    ("EF07", "7º ano do Ensino Fundamental"),
    ("EF08", "8º ano do Ensino Fundamental"),
    ("EF09", "9º ano do Ensino Fundamental"),
    ("EM", "Ensino Médio"),
]


def etapa_do_referencial(etapa_ano):
    """Traduz a etapa do curso para a etapa em que o referencial organiza."""
    if not etapa_ano:
        return ""
    if etapa_ano.startswith("EM"):
        return "EM"
    return etapa_ano


def rotulo_da_competencia(etapa, plural=False):
    """Como a etapa chama o que o referencial oferece (spec 4.2).

    A Educacao Infantil da BNCC diz "objetivo de aprendizagem"; do 1o ano em
    diante, "habilidade". O modelo continua chamando tudo de Competencia, que e o
    nome generico do sistema; quem muda de palavra e a tela.
    """
    if etapa == "EI":
        return "objetivos de aprendizagem" if plural else "objetivo de aprendizagem"
    return "habilidades" if plural else "habilidade"
```

- [ ] **Step 4: Os campos e a propriedade**

Em `apps/referenciais/models.py`, troque o import de `ETAPAS` por
`ETAPAS_REFERENCIAL` e aplique:

Em `Referencial`, depois de `valida_quantidade`:

```python
    @property
    def organiza_por_etapa(self):
        """Este referencial separa o que oferece por etapa escolar?

        Derivado do dado, e nao um campo: campo seria segunda fonte de verdade e
        sairia de sincronia na primeira importacao. E a pergunta e sobre o dado, e
        nao sobre a sigla, porque nenhuma tela pode pressupor BNCC (spec 4.2).
        """
        return self.competencias.exists()
```

Em `Categoria`, depois de `nome`:

```python
    descricao = models.TextField("descrição", blank=True)
```

Em `Competencia`, depois de `descricao`:

```python
    # O nivel que o Ensino Fundamental da BNCC poe entre o eixo e a habilidade
    # ("Conceituacao de Algoritmos"). Campo, e nao modelo: agrupa na tela, nao tem
    # identidade nem regra, e um modelo custaria tabela e join para um rotulo.
    objeto_conhecimento = models.CharField(
        "objeto de conhecimento", max_length=120, blank=True
    )
```

E a etapa passa a usar o vocabulário do referencial:

```python
    etapa = models.CharField("etapa", max_length=4, choices=ETAPAS_REFERENCIAL)
```

- [ ] **Step 5: Migração e o par do teste de `organiza_por_etapa`**

Run: `python manage.py makemigrations referenciais --name bncc_por_etapa`
Run: `python manage.py migrate`

Acrescente a `apps/referenciais/tests/test_models.py`:

```python
@pytest.mark.django_db
def test_referencial_com_competencias_organiza_por_etapa():
    """Prende o outro lado: sem este par, um `return False` fixo passaria."""
    referencial = Referencial.objects.create(nome="Com dados", sigla="COMD")
    categoria = Categoria.objects.create(referencial=referencial, nome="Eixo", ordem=1)
    Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="XX01CO01",
        descricao="Descricao qualquer.", etapa="EM", ordem=1,
    )
    assert referencial.organiza_por_etapa is True
```

`etapa="EM"` de propósito: é o valor que só existe no vocabulário novo, então
este teste também prende a troca de `ETAPAS` por `ETAPAS_REFERENCIAL`.

- [ ] **Step 6: Rodar tudo e commitar**

Run: `pytest`
Expected: PASS.

Comite, depois apague só o `if etapa_ano.startswith("EM")` e confirme que
`test_etapa_do_curso_vira_etapa_do_referencial` fica vermelho. Restaure.

```bash
git add -A
git commit -m "feat(referenciais): o modelo acomoda a BNCC como ela e"
```

---

### Task 2: as 120 habilidades

**Files:**
- Modify: `apps/referenciais/fixtures/bncc_computacao.json`
- Create: `docs/dados/bncc_computacao_habilidades.csv`
- Modify: `apps/referenciais/management/commands/importar_competencias.py`
- Modify: `docs/dados/README.md`
- Test: `apps/referenciais/tests/test_bncc.py` (novo)

**Interfaces:**
- Consumes: `ETAPAS_REFERENCIAL` e `Competencia.objeto_conhecimento` (Task 1).
- Produces: o CSV com as colunas
  `codigo,descricao,etapa,categoria,objeto_conhecimento`.

**A fonte.** Transcreva do Complemento à BNCC. As contagens, lidas do documento:

| Etapa | Códigos | Quantidade |
|---|---|---|
| `EI` | `EI03CO01` a `EI03CO11` | 11 |
| `EF01` | `EF01CO01` a `EF01CO07` | 7 |
| `EF02` | `EF02CO01` a `EF02CO06` | 6 |
| `EF03` | `EF03CO01` a `EF03CO09` | 9 |
| `EF04` | `EF04CO01` a `EF04CO08` | 8 |
| `EF05` | `EF05CO01` a `EF05CO11` | 11 |
| `EF06` | `EF06CO01` a `EF06CO10` | 10 |
| `EF07` | `EF07CO01` a `EF07CO11` | 11 |
| `EF08` | `EF08CO01` a `EF08CO11` | 11 |
| `EF09` | `EF09CO01` a `EF09CO10` | 10 |
| `EM` | `EM13CO01` a `EM13CO26` | 26 |
| **Total** | | **120** |

Os blocos `EF15CO` e `EF69CO` **não entram** (decisão registrada na spec §15).

**A divergência a registrar.** O PDF imprime a última habilidade do 5º ano como
`(EF05CO011)`, com três dígitos; as outras 119 têm dois. Transcreva como
`EF05CO11` e registre a divergência em `docs/dados/README.md`. Normalizar um erro
de diagramação não é inventar habilidade, mas precisa ficar dito onde a
transcrição se afasta da fonte.

- [ ] **Step 1: Escrever o teste da contagem**

Crie `apps/referenciais/tests/test_bncc.py`:

```python
"""A transcricao da BNCC, conferida contra numeros lidos do documento.

Dado ausente nao levanta excecao: um CSV pela metade importa limpo, a tela mostra
menos habilidades e ninguem percebe. Os numeros abaixo foram contados no
Complemento a BNCC, nao no arquivo, e e isso que faz deles um teste.
"""

import csv
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

CSV = Path(settings.BASE_DIR) / "docs" / "dados" / "bncc_computacao_habilidades.csv"

POR_ETAPA = {
    "EI": 11, "EF01": 7, "EF02": 6, "EF03": 9, "EF04": 8, "EF05": 11,
    "EF06": 10, "EF07": 11, "EF08": 11, "EF09": 10, "EM": 26,
}
TOTAL = 120


def linhas():
    with CSV.open(encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def test_o_csv_tem_a_contagem_do_documento():
    contagem = {}
    for linha in linhas():
        contagem[linha["etapa"]] = contagem.get(linha["etapa"], 0) + 1
    assert contagem == POR_ETAPA


def test_o_csv_tem_o_total_do_documento():
    assert len(linhas()) == TOTAL


def test_nenhum_codigo_repetido():
    codigos = [linha["codigo"] for linha in linhas()]
    assert len(set(codigos)) == len(codigos)


def test_nenhuma_descricao_vazia():
    """Codigo sem descricao passaria pela contagem e apareceria em branco na tela."""
    vazias = [linha["codigo"] for linha in linhas() if not (linha["descricao"] or "").strip()]
    assert vazias == []


def test_codigo_do_quinto_ano_normalizado():
    """O PDF imprime (EF05CO011), com tres digitos. A divergencia esta registrada
    em docs/dados/README.md; este teste impede que ela volte em silencio."""
    codigos = {linha["codigo"] for linha in linhas()}
    assert "EF05CO11" in codigos
    assert "EF05CO011" not in codigos


@pytest.mark.django_db
def test_importacao_carrega_tudo_e_agrupa():
    """Ponta a ponta: a fixture mais o CSV precisam bastar. Se uma categoria do
    CSV nao existir na fixture, o comando recusa e este teste acusa."""
    from apps.referenciais.models import Competencia, Referencial

    call_command("loaddata", "bncc_computacao", verbosity=0)
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(CSV), verbosity=0)

    bncc = Referencial.objects.get(sigla="BNCC-COMP")
    assert bncc.competencias.count() == TOTAL
    assert Competencia.objects.filter(referencial=bncc, etapa="EM").count() == 26
    # O Medio pendura em competencia especifica, nao em eixo (spec 4.2).
    eixos_no_medio = set(
        Competencia.objects.filter(referencial=bncc, etapa="EM").values_list(
            "categoria__nome", flat=True
        )
    )
    assert "Pensamento Computacional" not in eixos_no_medio


@pytest.mark.django_db
def test_importar_duas_vezes_nao_duplica():
    """O comando usa update_or_create; reimportar corrige descricao sem duplicar."""
    from apps.referenciais.models import Referencial

    call_command("loaddata", "bncc_computacao", verbosity=0)
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(CSV), verbosity=0)
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(CSV), verbosity=0)
    assert Referencial.objects.get(sigla="BNCC-COMP").competencias.count() == TOTAL
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/referenciais/tests/test_bncc.py -v`
Expected: FAIL, `FileNotFoundError` no CSV.

- [ ] **Step 3: As sete competências específicas do Ensino Médio na fixture**

`Categoria.nome` tem 120 caracteres e as competências específicas do Médio são
parágrafos inteiros. Grave um **rótulo curto** em `nome` e o **texto oficial
completo** em `descricao` (campo criado na Task 1). O rótulo é redação sua, para
caber num select; o texto que a escola vai conferir continua ali, inteiro.

Acrescente à fixture, com `pk` a partir de 4 e `ordem` a partir de 4:

| pk | nome (rótulo) | descricao (texto oficial, na íntegra) |
|---|---|---|
| 4 | Possibilidades e limites da Computação | "Compreender as possibilidades e os limites da Computação para resolver problemas..." |
| 5 | Análise crítica de artefatos computacionais | "Analisar criticamente artefatos computacionais, sendo capaz de identificar as vulnerabilidades..." |
| 6 | Técnicas computacionais para o mundo contemporâneo | "Analisar situações do mundo contemporâneo, selecionando técnicas computacionais apropriadas..." |
| 7 | Construção de conhecimento e artefatos | "Construir conhecimento usando técnicas e tecnologias computacionais, produzindo conteúdos e artefatos..." |
| 8 | Projetos e decisões socialmente responsáveis | "Desenvolver projetos para investigar desafios do mundo contemporâneo, construir soluções e tomar decisões éticas..." |
| 9 | Expressão e partilha com tecnologias | "Expressar e partilhar informações, ideias, sentimentos e soluções computacionais utilizando diferentes plataformas..." |
| 10 | Ação pessoal e coletiva com responsabilidade | "Agir pessoal e coletivamente com respeito, autonomia, responsabilidade, flexibilidade, resiliência e determinação..." |

Copie cada `descricao` **na íntegra** do documento, sem as reticências acima.

- [ ] **Step 4: O CSV**

Crie `docs/dados/bncc_computacao_habilidades.csv` com o cabeçalho
`codigo,descricao,etapa,categoria,objeto_conhecimento` e as 120 linhas.

Regras da transcrição:
- `categoria` é o eixo (`Pensamento Computacional`, `Mundo Digital`,
  `Cultura Digital`) da Educação Infantil ao 9º ano, e o **rótulo curto** da
  competência específica no Ensino Médio.
- `objeto_conhecimento` vem preenchido no Fundamental, onde o documento o traz, e
  vazio na Educação Infantil e no Ensino Médio, onde ele não existe.
- `descricao` é o texto da habilidade **sem** o código entre parênteses: o código
  já é a primeira coluna.
- Vírgula dentro do texto exige aspas, que é o padrão do módulo `csv`. Escreva o
  arquivo com `csv.writer`, não à mão, para não errar isso em 120 linhas.

- [ ] **Step 5: A coluna opcional no comando de importação**

Em `apps/referenciais/management/commands/importar_competencias.py`, o conjunto
`COLUNAS` continua sendo o das obrigatórias; `objeto_conhecimento` entra como
opcional, para que um CSV de outro referencial, sem essa coluna, siga funcionando:

```python
    # Opcional de proposito: outro referencial pode nao ter esse nivel, e exigir a
    # coluna quebraria um CSV que hoje importa.
    objeto = (linha.get("objeto_conhecimento") or "").strip()
```

e passe `"objeto_conhecimento": objeto` no `defaults` do `update_or_create`.

- [ ] **Step 6: Rodar e ver passar**

Run: `pytest apps/referenciais/tests/test_bncc.py -v`
Expected: PASS, os sete testes.

Se `test_o_csv_tem_a_contagem_do_documento` falhar, **não ajuste os números**:
eles vieram do documento. Falta linha no CSV.

- [ ] **Step 7: Documentar e commitar**

Atualize `docs/dados/README.md`: o CSV agora vive no repositório, o comando é o
mesmo, e a divergência do `EF05CO011` fica registrada com o motivo.

Run: `pytest`

```bash
git add -A
git commit -m "feat(referenciais): as 120 habilidades da BNCC da Computacao"
```

---

### Task 3: o bloco de habilidades na ficha

**Files:**
- Modify: `apps/cursos/forms.py` (`FichaCursoForm.clean`)
- Modify: `apps/cursos/views/professor.py`, `views/__init__.py`, `urls.py`
- Create: `templates/cursos/_habilidades.html`
- Modify: `templates/cursos/ficha.html`
- Test: `apps/cursos/tests/test_ficha.py`

**Interfaces:**
- Consumes: `etapa_do_referencial`, `rotulo_da_competencia` (Task 1).
- Produces: url `ficha_habilidades` em `cursos/<int:pk>/ficha/habilidades/`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescente a `apps/cursos/tests/test_ficha.py`:

```python
@pytest.fixture
def bncc(db):
    from django.core.management import call_command
    from apps.referenciais.models import Referencial

    call_command("loaddata", "bncc_computacao", verbosity=0)
    return Referencial.objects.get(sigla="BNCC-COMP")


@pytest.mark.django_db
def test_bloco_de_habilidades_nao_existe_sem_referencial(client, proposta, professor):
    """Spec 4.2: campo vazio de um referencial que nao foi adotado e ruido."""
    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    assert "id=\"habilidades\"" in html
    assert "Nenhum referencial escolhido" in html


@pytest.mark.django_db
def test_bloco_lista_so_as_habilidades_da_etapa(client, proposta, professor, bncc, habilidades):
    client.force_login(professor)
    resposta = client.get(
        reverse("ficha_habilidades", args=[proposta.pk]),
        {"referencial": bncc.pk, "etapa_ano": "EF05"},
    )
    html = resposta.content.decode()
    assert "EF05CO01" in html
    assert "EF01CO01" not in html


@pytest.mark.django_db
def test_bloco_do_ensino_medio_aceita_qualquer_um_dos_tres_anos(
    client, proposta, professor, bncc, habilidades
):
    """As habilidades do Medio valem para os tres anos (spec 4.2)."""
    client.force_login(professor)
    for ano in ("EM01", "EM02", "EM03"):
        html = client.get(
            reverse("ficha_habilidades", args=[proposta.pk]),
            {"referencial": bncc.pk, "etapa_ano": ano},
        ).content.decode()
        assert "EM13CO01" in html


@pytest.mark.django_db
def test_educacao_infantil_usa_o_termo_do_documento(
    client, proposta, professor, bncc, habilidades
):
    client.force_login(professor)
    html = client.get(
        reverse("ficha_habilidades", args=[proposta.pk]),
        {"referencial": bncc.pk, "etapa_ano": "EI"},
    ).content.decode()
    assert "bjetivos de aprendizagem" in html
    assert "habilidades" not in html.lower()


@pytest.mark.django_db
def test_habilidade_de_outra_etapa_e_recusada(proposta, bncc, habilidades):
    """A tela filtra, mas um POST forjado nao passa pela tela. A regra fica no
    formulario, onde tem mensagem e teste."""
    from apps.cursos.choices import TipoPublico
    from apps.cursos.forms import FichaCursoForm

    de_outra_etapa = bncc.competencias.filter(etapa="EI").first()
    form = FichaCursoForm(
        ficha_valida(
            tipo_publico=TipoPublico.ESCOLAR, etapa_ano="EF05",
            referencial=bncc.pk, competencias=[de_outra_etapa.pk],
        ),
        instance=proposta,
    )
    assert form.is_valid() is False
    assert "competencias" in form.errors


@pytest.mark.django_db
def test_habilidade_da_etapa_certa_e_aceita(proposta, bncc, habilidades):
    """Prende o outro lado: sem este par, um `raise` incondicional passaria."""
    from apps.cursos.choices import TipoPublico
    from apps.cursos.forms import FichaCursoForm

    da_etapa = list(bncc.competencias.filter(etapa="EF05")[:2])
    form = FichaCursoForm(
        ficha_valida(
            tipo_publico=TipoPublico.ESCOLAR, etapa_ano="EF05",
            referencial=bncc.pk, competencias=[c.pk for c in da_etapa],
        ),
        instance=proposta,
    )
    assert form.is_valid() is True, form.errors
```

A fixture `habilidades` importa o CSV uma vez:

```python
@pytest.fixture
def habilidades(bncc):
    from pathlib import Path
    from django.conf import settings
    from django.core.management import call_command

    call_command(
        "importar_competencias", referencial="BNCC-COMP",
        csv=str(Path(settings.BASE_DIR) / "docs" / "dados" / "bncc_computacao_habilidades.csv"),
        verbosity=0,
    )
    return bncc
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/cursos/tests/test_ficha.py -v`
Expected: FAIL, `NoReverseMatch` para `ficha_habilidades`.

- [ ] **Step 3: A view parcial e a url**

Em `apps/cursos/views/professor.py`:

```python
@login_required
def ficha_habilidades(request, pk):
    """O bloco de habilidades da ficha, trocado por HTMX quando muda o
    referencial ou a etapa.

    Guarda propria: e um GET, e ele responde sozinho. Sem ela, qualquer pessoa
    logada leria a ficha de qualquer curso pela url do bloco.
    """
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(
        permissions.pode_editar_ficha(request.user, curso),
        "Somente a equipe do curso edita a ficha, e apenas enquanto ele está em produção.",
    )
    return render(request, "cursos/_habilidades.html", contexto_das_habilidades(request, curso))


def contexto_das_habilidades(request, curso):
    """Monta o bloco a partir do que a tela tem AGORA, e nao do que esta gravado:
    a pessoa acabou de trocar o select e ainda nao salvou."""
    from apps.referenciais.choices import etapa_do_referencial, rotulo_da_competencia
    from apps.referenciais.models import Referencial

    referencial_id = request.GET.get("referencial") or curso.referencial_id
    etapa_ano = request.GET.get("etapa_ano") if "etapa_ano" in request.GET else curso.etapa_ano
    referencial = Referencial.objects.filter(pk=referencial_id or 0).first()
    etapa = etapa_do_referencial(etapa_ano)

    grupos = []
    if referencial and etapa:
        competencias = referencial.competencias.filter(etapa=etapa).select_related("categoria")
        atual = None
        for competencia in competencias:
            if atual is None or atual["categoria"] != competencia.categoria:
                atual = {"categoria": competencia.categoria, "itens": []}
                grupos.append(atual)
            atual["itens"].append(competencia)
    return {
        "curso": curso,
        "referencial": referencial,
        "etapa": etapa,
        "grupos": grupos,
        "rotulo": rotulo_da_competencia(etapa, plural=True),
        "escolhidas": set(curso.competencias.values_list("pk", flat=True)),
    }
```

O agrupamento sequencial funciona porque `Competencia.Meta.ordering` já ordena por
`referencial, etapa, ordem, codigo`, e a ordem do CSV segue o documento, que
agrupa por eixo. Se algum dia deixar de seguir, o teste da Task 5 acusa.

Em `apps/cursos/urls.py`, depois da linha de `ficha`:

```python
    path("cursos/<int:pk>/ficha/habilidades/", views.ficha_habilidades, name="ficha_habilidades"),
```

Acrescente `ficha_habilidades` ao import e ao `__all__` de
`apps/cursos/views/__init__.py`.

- [ ] **Step 4: O bloco e a ligação com a ficha**

Crie `templates/cursos/_habilidades.html`:

```html
<div id="habilidades"
     hx-get="{% url 'ficha_habilidades' curso.pk %}"
     hx-trigger="change from:#id_referencial, change from:#id_etapa_ano"
     hx-include="#id_referencial, #id_etapa_ano"
     hx-target="#habilidades"
     hx-swap="outerHTML">
  {% if not referencial %}
    <p class="apoio">Nenhum referencial escolhido. Escolha um acima para listar o
       que ele oferece, ou deixe em branco: curso sem referencial é normal.</p>
  {% elif not etapa %}
    <p class="apoio">{{ referencial.nome }} organiza por etapa escolar. Defina o
       público escolar e a etapa para ver o que ele oferece.</p>
  {% else %}
    <p class="apoio">{{ referencial.nome }}, {{ rotulo }} de
       {{ etapa|etapa_legivel }}. Escolha de
       {{ referencial.min_competencias }} a {{ referencial.max_competencias }}.</p>
    {% for grupo in grupos %}
      <fieldset class="grupo-habilidades">
        <legend title="{{ grupo.categoria.descricao }}">{{ grupo.categoria.nome }}</legend>
        {% for item in grupo.itens %}
          <label class="habilidade">
            <input type="checkbox" name="competencias" value="{{ item.pk }}"
                   {% if item.pk in escolhidas %}checked{% endif %}>
            <span class="codigo">{{ item.codigo }}</span>
            {% if item.objeto_conhecimento %}
              <span class="objeto">{{ item.objeto_conhecimento }}</span>
            {% endif %}
            <span class="texto">{{ item.descricao }}</span>
          </label>
        {% endfor %}
      </fieldset>
    {% empty %}
      <p class="apoio">Nada cadastrado para esta etapa ainda.</p>
    {% endfor %}
  {% endif %}
</div>
```

O filtro `etapa_legivel` traduz o código da etapa. Crie-o em
`apps/referenciais/templatetags/referenciais.py`:

```python
from django import template

from apps.referenciais.choices import ETAPAS_REFERENCIAL

register = template.Library()
NOMES = dict(ETAPAS_REFERENCIAL)


@register.filter
def etapa_legivel(codigo):
    return NOMES.get(codigo, codigo)
```

Em `templates/cursos/ficha.html`, tire `competencias` do `{{ form.as_p }}` e ponha
o bloco no lugar. Renderize os demais campos um a um, ou use
`{% for campo in form %}{% if campo.name != "competencias" %}...{% endif %}{% endfor %}`,
seguindo o que o arquivo já faz. Carregue a biblioteca com
`{% load referenciais %}` no topo e inclua
`{% include "cursos/_habilidades.html" %}` logo depois do campo de referencial.

- [ ] **Step 5: A regra no formulário**

Em `apps/cursos/forms.py`, `FichaCursoForm.clean` passa a conferir também a etapa:

```python
        etapa = etapa_do_referencial(dados.get("etapa_ano"))
        fora_da_etapa = [c for c in competencias if etapa and c.etapa != etapa]
        if fora_da_etapa:
            codigos = ", ".join(c.codigo for c in fora_da_etapa)
            raise ValidationError(
                {"competencias": f"Estas não são da etapa escolhida: {codigos}."}
            )
```

logo depois da checagem de referencial que já existe. As duas ficam separadas de
propósito: são regras diferentes (referencial errado, etapa errada), e juntá-las
num `if` só faria uma delas nunca ser exercitada sozinha.

- [ ] **Step 6: Rodar tudo**

Run: `pytest`
Expected: PASS.

- [ ] **Step 7: Provar por deleção, uma de cada vez**

Comite antes. Depois, restaurando entre cada uma:

1. Apague o `permissions.garante` de `ficha_habilidades`: escreva um teste de GET por quem não é da equipe se nenhum ficar vermelho.
2. Apague o `filter(etapa=etapa)` do contexto: `test_bloco_lista_so_as_habilidades_da_etapa` fica vermelho.
3. Apague o `raise` de etapa em `FichaCursoForm.clean`: `test_habilidade_de_outra_etapa_e_recusada` fica vermelho.
4. Troque `etapa_do_referencial(etapa_ano)` por `etapa_ano` no contexto: `test_bloco_do_ensino_medio_aceita_qualquer_um_dos_tres_anos` fica vermelho. É a lição do Plano 3, a regra provada de um lado da fronteira e solta no ponto de chamada.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(cursos): a ficha lista as habilidades do referencial por etapa"
```

---

### Task 4: referencial por etapa exige etapa

**Files:**
- Modify: `apps/cursos/validacoes.py`
- Test: `apps/cursos/tests/test_validacoes.py`

- [ ] **Step 1: Escrever os testes que falham**

```python
@pytest.mark.django_db
def test_referencial_por_etapa_exige_etapa_do_curso(curso_criado, bncc_carregada):
    """Spec 4.2: sem etapa, o curso fica com um referencial cujas habilidades
    nenhuma tela consegue listar."""
    from apps.cursos.choices import TipoPublico

    curso_criado.referencial = bncc_carregada
    curso_criado.tipo_publico = TipoPublico.COMUNITARIO
    curso_criado.etapa_ano = ""
    curso_criado.publico_descricao = "Grupo de convivência"
    curso_criado.save()
    faltas = validacoes.dados_do_curso(curso_criado)
    assert any("etapa" in f.lower() for f in faltas)


@pytest.mark.django_db
def test_referencial_sem_competencias_nao_exige_etapa(curso_criado):
    """Prende o outro lado, e prende a regra certa: a exigencia vem do DADO, nao
    da sigla. Um referencial recem-criado, sem CSV importado, nao pode travar
    curso nenhum (spec 4.2: nenhuma tela pressupoe BNCC)."""
    from apps.cursos.choices import TipoPublico
    from apps.referenciais.models import Referencial

    curso_criado.referencial = Referencial.objects.create(nome="Novo", sigla="NOVO")
    curso_criado.tipo_publico = TipoPublico.COMUNITARIO
    curso_criado.etapa_ano = ""
    curso_criado.publico_descricao = "Grupo de convivência"
    curso_criado.save()
    assert not any("etapa" in f.lower() for f in validacoes.dados_do_curso(curso_criado))
```

- [ ] **Step 2: Rodar, ver falhar, implementar**

Em `apps/cursos/validacoes.py`, dentro de `dados_do_curso`, no bloco que já trata
do referencial:

```python
    if curso.referencial_id:
        if curso.referencial.organiza_por_etapa and not curso.etapa_ano:
            faltas.append(
                f"{curso.referencial.nome} organiza o que oferece por etapa escolar: "
                "defina o público escolar e a etapa, ou deixe o curso sem referencial."
            )
        try:
            curso.referencial.valida_quantidade(curso.competencias.count())
        except ValidationError as erro:
            faltas.append(erro.messages[0])
```

- [ ] **Step 3: Rodar, provar por deleção, commitar**

Run: `pytest`

Comite, apague só o `if curso.referencial.organiza_por_etapa and not
curso.etapa_ano` e confirme que o primeiro teste fica vermelho. Restaure.

```bash
git add -A
git commit -m "feat(cursos): referencial organizado por etapa exige etapa no curso"
```

---

### Task 5: revisão de branch e documentação

- [ ] **Step 1: Enumerar as regras, e só depois olhar os testes**

Lidas da spec e deste documento, não do código:

1. Etapa do Médio agrega os três anos; as demais passam direto.
2. Curso sem etapa devolve etapa vazia.
3. Educação Infantil diz "objetivo de aprendizagem"; o resto, "habilidade".
4. Referencial sem competências não organiza por etapa.
5. Referencial com competências organiza.
6. O CSV tem 120 linhas, com a contagem por etapa do documento.
7. Nenhum código repetido, nenhuma descrição vazia.
8. `EF05CO11`, e não `EF05CO011`.
9. O Ensino Médio pendura em competência específica, não em eixo.
10. Reimportar não duplica.
11. Sem referencial, o bloco de habilidades não lista nada.
12. O bloco lista só a etapa pedida.
13. Habilidade de outra etapa é recusada no formulário.
14. Habilidade da etapa certa é aceita.
15. Referencial que organiza por etapa exige etapa no curso.
16. Referencial sem competências não exige.

Para cada uma: **apagar esta guarda sozinha faria algum teste falhar?**

- [ ] **Step 2: Conferir o que a ordenação do CSV pressupõe**

O agrupamento por categoria na view é sequencial, e depende de a ordenação trazer
as competências de uma mesma categoria juntas. Escreva o teste que prende isso:

```python
@pytest.mark.django_db
def test_habilidades_de_uma_etapa_vem_agrupadas_por_categoria(bncc, habilidades):
    """O agrupamento da view e sequencial: se a ordenacao intercalar categorias, o
    mesmo eixo apareceria duas vezes na tela, com um pedaco em cada lugar."""
    vistas = []
    for competencia in bncc.competencias.filter(etapa="EF05").select_related("categoria"):
        nome = competencia.categoria.nome
        if not vistas or vistas[-1] != nome:
            vistas.append(nome)
    assert len(vistas) == len(set(vistas))
```

- [ ] **Step 3: Percorrer a tela com os olhos**

Suba o servidor, entre como professor, abra a ficha de um curso e:
escolha a BNCC sem etapa (deve pedir a etapa), escolha público escolar e 5º ano
(devem aparecer os três eixos com as 11 habilidades), troque para Educação
Infantil (o texto deve dizer "objetivos de aprendizagem"), troque para 2º ano do
Médio (devem aparecer as competências específicas), tire o referencial (o bloco
deve dizer que nenhum foi escolhido). Salve com uma habilidade marcada e confira
que ela volta marcada ao reabrir.

Defeito visual não aparece em suíte verde: neste projeto, cache de CSS, cor de
botão e `None` interpolado em template foram todos achados por olho humano.

- [ ] **Step 4: Estilo, suíte e CLAUDE.md**

Run: `pytest tests/test_estilo.py -v`
Run: `pytest`

Acrescente à CLAUDE.md, na seção de referenciais pedagógicos:

```markdown
- A BNCC vive em `docs/dados/bncc_computacao_habilidades.csv`, 120 linhas
  transcritas do Complemento à BNCC, importadas por `importar_competencias`. A
  contagem por etapa é teste (`apps/referenciais/tests/test_bncc.py`), com números
  lidos do documento: CSV truncado importa limpo e a falta só apareceria na tela.
- O Ensino Médio da BNCC **não usa os três eixos**: suas 26 habilidades penduram
  em sete competências específicas, gravadas como `Categoria` ao lado dos eixos.
- `Competencia.etapa` tem vocabulário próprio (`EM`, não `EM01`..`EM03`).
  `etapa_do_referencial()` traduz o `etapa_ano` do curso; use-a, não compare
  strings à mão.
- A exigência de etapa vem de `Referencial.organiza_por_etapa`, derivada do dado.
  **Não escreva `if referencial.sigla == "BNCC-COMP"`** em lugar nenhum.
```

- [ ] **Step 5: Commit e fechamento**

```bash
git add -A
git commit -m "docs: convencoes da BNCC por etapa"
```

**REQUIRED SUB-SKILL:** use `superpowers:finishing-a-development-branch`.
