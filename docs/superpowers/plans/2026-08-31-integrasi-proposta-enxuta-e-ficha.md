# Plano 6: proposta enxuta, equipe mista e ficha do curso

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O professor cria a proposta digitando só o título, monta uma equipe que
aceita alunos e outros professores, e a própria equipe preenche a ficha do curso
numa tela nova.

**Architecture:** Nada de portão novo. `validacoes.dados_do_curso()` já roda na
revisão do Plano de Ensino e outra vez na submissão à coordenação, e é ele que
impede curso incompleto de avançar; este plano apenas tira a obrigatoriedade do
formulário de criação e acrescenta `resumo` a esse portão. A equipe deixa de ser
lista de alunos e passa a ser lista de pessoas (`MembroEquipe.pessoa`), com o
professor responsável dentro dela desde a criação.

**Tech Stack:** Django 5.2, Python 3.13, PostgreSQL, pytest + pytest-django, HTMX.

**Spec:** `docs/superpowers/specs/2026-08-25-integrasi-design.md`, seções 3, 4.1,
4.3, 5, 7.3, 10 e 15 (atualizadas nos commits `70d46c5` e `25ec4d7`).

## Global Constraints

- `save()` chama `full_clean()`, **exceto** quando vem `update_fields`.
- Só `services.py` altera campo de status. Nada de lógica de domínio em `post_save`.
- Checagem de permissão em `cursos/permissions.py`, chamada pelos serviços; nunca
  `if` de permissão em template.
- Texto de interface em português acentuado. Valores gravados (choices, slugs)
  sem acento e nunca alterados por passada de texto.
- **Nada de travessão** em lugar nenhum do repositório: nem o caractere em-dash
  (U+2014), nem a entidade HTML equivalente. `tests/test_estilo.py` reprova, e
  reprovaria este próprio arquivo se a regra fosse escrita mostrando o símbolo. Use dois pontos, parênteses, vírgula
  ou traço simples com espaços.
- `Curso.referencial` continua `PROTECT`. `Curso.edicao` continua `PROTECT` e
  **não nula**.
- TDD: o teste que falha vem primeiro.
- CPF não aparece fora do Django Admin.
- Nenhum campo de frequência, nota ou certificado (fronteira do módulo, spec 1.1).

## Como provar que uma regra está presa

Este projeto já perdeu nove regras para o padrão "teste com nome que não exercita
a regra". Ao terminar cada tarefa, **comite**, depois apague **uma guarda de cada
vez** e rode a suíte. Se nada ficar vermelho, a regra não está presa: escreva o
teste que a prende antes de restaurar. Dois avisos que valem em particular aqui:

- **Guarda de view mascarada pelo serviço.** As views desta tarefa chamam serviços
  que também conferem permissão. Afrouxar a guarda da view não quebra teste de
  POST nenhum, porque o serviço recusa igual e o teste vê o mesmo 403. Toda guarda
  de view precisa de um teste por **GET**, que não chama o serviço.
- **Regra provada de um lado da fronteira de função.** Testar `pode_editar_ficha()`
  isolada não prova que a view a chama. Prenda no ponto de chamada também.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Tarefa |
|---|---|---|
| `apps/cursos/models/equipe.py` | `MembroEquipe.pessoa`, unicidade por (curso, pessoa) | 1 |
| `apps/cursos/models/curso.py` | `tem_membro`, campos da ficha opcionais no banco | 1, 3 |
| `apps/cursos/permissions.py` | `pode_ver_curso` para membro, `pode_editar_ficha` | 1, 4 |
| `apps/cursos/services.py` | responsável na equipe, edição corrente, `atualizar_ficha`, `alocar_professor`, `remover_membro` | 2, 3, 4, 5, 6 |
| `apps/cursos/forms.py` | `PropostaForm` (só título) e `FichaCursoForm` (o resto) | 3, 4 |
| `apps/cursos/validacoes.py` | `resumo` no portão de completude | 3 |
| `apps/cursos/choices.py` | `STATUS_EDITAVEIS` | 4 |
| `apps/cursos/views/professor.py` | proposta, equipe, ficha, remoção | 3, 4, 5, 6 |
| `templates/cursos/ficha.html` | tela nova da ficha | 4 |
| `templates/cursos/equipe.html` | alocar aluno, alocar professor, remover | 5, 6 |

---

### Task 1: a equipe aceita professor (`MembroEquipe.pessoa`)

Hoje `MembroEquipe.aluno` tem a guarda `"Só aluno pode compor a equipe de
produção."`. A equipe passa a receber professor, então o campo muda de nome (uma
coluna chamada `aluno` guardando professor é mentira de esquema) e a guarda cai.

**Atenção à guarda que some.** Todo `Usuario` é `ALUNO`, `PROFESSOR` ou
`COORDENADOR`. Se a equipe aceita aluno e professor, uma guarda de papel em
`MembroEquipe.clean()` **não consegue mais falhar**, e guarda que não falha não é
guarda. `clean()` é removido inteiro, não reescrito. A unicidade continua presa
pela `UniqueConstraint` e por `full_clean()` dentro de `save()`.

**Files:**
- Modify: `apps/cursos/models/equipe.py`
- Modify: `apps/cursos/models/curso.py:225` (`tem_membro`)
- Modify: `apps/cursos/permissions.py` (`pode_ver_curso`)
- Modify: `apps/cursos/services.py:70` (`adicionar_membro`), `:169` (`_emails_da_equipe`)
- Modify: `apps/cursos/views/aluno.py:19,29`, `apps/cursos/views/professor.py:64`
- Modify: `apps/contas/views.py:75`
- Modify: `templates/cursos/equipe.html:20`, `templates/cursos/curso.html:45`
- Create: `apps/cursos/migrations/0012_membroequipe_pessoa.py`
- Test: `apps/cursos/tests/test_equipe.py`, `apps/cursos/tests/test_permissions.py`

**Interfaces:**
- Produces: `MembroEquipe.pessoa` (FK para `AUTH_USER_MODEL`, `related_name="equipes"`);
  `Curso.tem_membro(usuario) -> bool`;
  `services.adicionar_membro(curso, pessoa, por) -> MembroEquipe`;
  `permissions.pode_ver_curso(usuario, curso) -> bool`.

- [ ] **Step 1: Inverter o teste que hoje proíbe professor na equipe**

Em `apps/cursos/tests/test_equipe.py`, o teste
`test_professor_nao_pode_ser_membro_da_equipe` afirma o contrário da regra nova.
Substitua o arquivo inteiro por:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.cursos.models import MembroEquipe


@pytest.mark.django_db
def test_membro_e_vinculado_ao_curso(curso, aluno):
    MembroEquipe.objects.create(curso=curso, pessoa=aluno)
    assert curso.membros.count() == 1
    assert curso.tem_membro(aluno)


@pytest.mark.django_db
def test_mesma_pessoa_duas_vezes_e_recusada(curso, aluno):
    MembroEquipe.objects.create(curso=curso, pessoa=aluno)
    with pytest.raises(ValidationError):
        MembroEquipe.objects.create(curso=curso, pessoa=aluno)


@pytest.mark.django_db
def test_professor_pode_ser_membro_da_equipe(curso, outro_professor):
    """A regra que este plano inverte: a equipe de producao passa a aceitar
    professor, que produz material como qualquer membro (spec 4.1)."""
    MembroEquipe.objects.create(curso=curso, pessoa=outro_professor)
    assert curso.tem_membro(outro_professor)


@pytest.mark.django_db
def test_coordenador_pode_ser_membro_da_equipe(curso, coordenador):
    """Coordenador e professor (regra 1 do Plano 5), entao entra pela mesma porta."""
    MembroEquipe.objects.create(curso=curso, pessoa=coordenador)
    assert curso.tem_membro(coordenador)


@pytest.mark.django_db
def test_quem_nao_e_membro_nao_e_reconhecido(curso, aluno, outro_aluno):
    MembroEquipe.objects.create(curso=curso, pessoa=aluno)
    assert curso.tem_membro(outro_aluno) is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/cursos/tests/test_equipe.py -v`
Expected: FAIL. Os cinco testes quebram com
`TypeError: MembroEquipe() got unexpected keyword arguments: 'pessoa'`.

- [ ] **Step 3: Renomear o campo e remover a guarda que não falha mais**

Substitua `apps/cursos/models/equipe.py` por:

```python
from django.conf import settings
from django.db import models


class MembroEquipe(models.Model):
    """Quem produz um curso: alunos e professores, inclusive o responsavel.

    O campo se chama `pessoa`, e nao `aluno`, porque guarda professor tambem
    (spec 4.1). Nao ha `clean()`: com a equipe aceitando aluno e professor, e
    todo Usuario sendo um dos dois, qualquer guarda de papel aqui seria uma
    guarda incapaz de falhar. A unicidade por (curso, pessoa) fica com a
    UniqueConstraint, que vale tambem para escrita em massa.
    """

    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.CASCADE, related_name="membros", verbose_name="curso"
    )
    pessoa = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="equipes", verbose_name="pessoa"
    )
    adicionado_em = models.DateTimeField("adicionado em", auto_now_add=True)

    class Meta:
        verbose_name = "membro da equipe"
        verbose_name_plural = "membros da equipe"
        ordering = ["pessoa__nome_completo"]
        constraints = [
            models.UniqueConstraint(fields=["curso", "pessoa"], name="membro_unico_por_curso")
        ]

    def __str__(self):
        return f"{self.pessoa.nome_completo} em {self.curso.titulo}"

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
```

Em `apps/cursos/models/curso.py`, `tem_membro`:

```python
    def tem_membro(self, usuario):
        return self.membros.filter(pessoa=usuario).exists()
```

- [ ] **Step 4: Gerar a migração**

Run: `python manage.py makemigrations cursos --name membroequipe_pessoa`

Responda **`y`** quando o Django perguntar se `aluno` foi renomeado para `pessoa`;
responder `n` criaria uma coluna nova e **apagaria a equipe de todos os cursos**.

Abra `apps/cursos/migrations/0012_membroequipe_pessoa.py` e confira que as
operações são, nesta ordem: `RemoveConstraint`, `RenameField`,
`AlterModelOptions` e `AddConstraint`. Se `RenameField` não estiver lá, desfaça
(`rm` o arquivo) e repita respondendo `y`.

Run: `python manage.py migrate`

- [ ] **Step 5: Atualizar os pontos que liam `.aluno`**

`apps/cursos/services.py`, em `adicionar_membro`, o parâmetro e a criação:

```python
@transaction.atomic
def adicionar_membro(curso, pessoa, por):
    """Vincula alguem a equipe. O primeiro membro tira o curso do rascunho."""
    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    membro = MembroEquipe.objects.create(curso=curso, pessoa=pessoa)
    if curso.status == StatusCurso.RASCUNHO:
        curso.status = StatusCurso.EM_PRODUCAO
        curso.save(update_fields=["status", "atualizado_em"])
    return membro
```

`apps/cursos/services.py`, `_emails_da_equipe`:

```python
def _emails_da_equipe(curso):
    return [m.pessoa.email for m in curso.membros.select_related("pessoa")]
```

`apps/cursos/views/aluno.py:19` e `:29`: troque `membros__aluno` por
`membros__pessoa` e `select_related("aluno")` por `select_related("pessoa")`.

`apps/cursos/views/professor.py:64`: `membro.aluno.nome_completo` vira
`membro.pessoa.nome_completo`.

`apps/contas/views.py:75`: `membros__aluno=usuario` vira `membros__pessoa=usuario`.

`templates/cursos/equipe.html:20` e `templates/cursos/curso.html:45`:
`membro.aluno.nome_completo` vira `membro.pessoa.nome_completo`.

`apps/cursos/tests/test_alocacao.py`: `membro.aluno` vira `membro.pessoa` nas sete
asserções (linhas 16, 17, 18, 19, 41, 83, 152).

- [ ] **Step 6: Deixar o professor membro enxergar o curso**

Sem isto, um professor alocado na equipe leva 403 na página do próprio curso: o
ramo do professor em `pode_ver_curso` devolve só `e_responsavel`. Em
`apps/cursos/permissions.py`:

```python
def pode_ver_curso(usuario, curso):
    """Coordenacao ve tudo; os demais veem o curso que respondem ou que produzem.

    O ramo do professor nao pode ser so `e_responsavel`: a partir deste plano um
    professor pode estar na equipe de um curso de outro (spec 10, professor
    colaborador), e produzir sem enxergar nao existe.
    """
    if usuario.e_coordenador:
        return True
    if e_responsavel(usuario, curso):
        return True
    return curso.tem_membro(usuario)
```

Acrescente a `apps/cursos/tests/test_permissions.py`:

```python
@pytest.mark.django_db
def test_professor_colaborador_ve_o_curso(curso, outro_professor):
    from apps.cursos.models import MembroEquipe

    MembroEquipe.objects.create(curso=curso, pessoa=outro_professor)
    assert permissions.pode_ver_curso(outro_professor, curso) is True


@pytest.mark.django_db
def test_professor_de_fora_nao_ve_o_curso(curso, outro_professor):
    """Prende o outro lado: sem vinculo nenhum, professor nao entra em curso alheio."""
    assert permissions.pode_ver_curso(outro_professor, curso) is False
```

- [ ] **Step 7: Rodar a suíte inteira**

Run: `pytest`
Expected: PASS. Se algum teste falhar por `aluno=`, é referência que escapou do
Step 5; corrija a referência, não o teste.

- [ ] **Step 8: Provar por deleção**

Comite primeiro (`git add -A && git commit`), depois apague **só** o `if
e_responsavel(usuario, curso): return True` de `pode_ver_curso` e rode `pytest`.
Algum teste precisa ficar vermelho. Restaure com `git checkout apps/cursos/permissions.py`.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(cursos): a equipe de producao aceita professor

MembroEquipe.aluno vira MembroEquipe.pessoa: a coluna passa a guardar
professor, e mante-la chamada de aluno seria mentira de esquema.

clean() sai inteiro em vez de ser reescrito. Com a equipe aceitando aluno e
professor, e todo Usuario sendo um dos dois, uma guarda de papel ali nao
conseguiria mais falhar - e guarda que nao falha nao prende nada. A unicidade
continua com a UniqueConstraint.

pode_ver_curso ganha o ramo de membro: sem ele o professor colaborador levava
403 na pagina do curso que ele proprio produz."
```

---

### Task 2: o professor responsável entra na equipe

Ser responsável é formalidade que atribui a revisão, e não dispensa de produzir
(spec 4.1). Ele passa a ser membro desde a criação. Três consequências que esta
tarefa fecha junto, porque separá-las deixaria o sistema incoerente no meio:

1. **`RASCUNHO` não pode morrer.** `adicionar_membro` tira o curso de `RASCUNHO`
   no primeiro membro. Se a criação usasse esse serviço, todo curso nasceria
   `EM_PRODUCAO` e o estado `RASCUNHO` nunca seria observado. A criação grava o
   `MembroEquipe` **direto**, sem passar por `adicionar_membro`.
2. **`abrir_nova_versao` cria `Curso` direto** e de propósito não copia a equipe
   (spec 4.5). Sem tratamento, a v2 nasceria sem o responsável.
3. **Um duplicado que a fila já absorve.** `publicar_curso` monta
   `_emails_da_equipe(curso) + [curso.professor_responsavel.email]`, e com o
   responsável dentro da equipe o endereço dele passa a aparecer duas vezes nessa
   lista. Isso **não** vira e-mail repetido: `notificacoes.services.enfileirar`
   faz `sorted({d for d in destinatarios if d})` e colapsa a repetição antes de
   gravar. Não mexa em `publicar_curso`, e não escreva um `_destinatarios_do_curso`:
   seria uma segunda deduplicação por cima da primeira, e duas guardas para a
   mesma coisa não se distinguem por teste. O que falta é prender a que existe:
   essa deduplicação não tem teste nenhum hoje.

E os cursos que já existem no banco têm o responsável fora da equipe: precisam de
migração de dados.

**Files:**
- Modify: `apps/cursos/services.py` (`criar_curso`, `abrir_nova_versao`, destinatários)
- Create: `apps/cursos/migrations/0013_responsavel_na_equipe.py`
- Test: `apps/cursos/tests/test_criacao.py`, `apps/cursos/tests/test_versoes.py`,
  `apps/cursos/tests/test_publicacao.py`

**Interfaces:**
- Consumes: `MembroEquipe.pessoa` e `Curso.tem_membro` (Task 1).
- Produces: nada de novo em `services.py` além do vínculo do responsável. A
  deduplicação de destinatário já mora em `notificacoes.services.enfileirar`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescente a `apps/cursos/tests/test_criacao.py`:

```python
@pytest.mark.django_db
def test_responsavel_entra_na_equipe_ao_criar(dados_curso, professor):
    curso = services.criar_curso(**dados_curso)
    assert curso.tem_membro(professor)


@pytest.mark.django_db
def test_curso_recem_criado_continua_em_rascunho(dados_curso):
    """O responsavel na equipe nao pode tirar o curso do rascunho: proposta com
    uma pessoa so ainda e proposta. Se isto falhar, alguem trocou a escrita direta
    do MembroEquipe por adicionar_membro, que transiciona o status."""
    curso = services.criar_curso(**dados_curso)
    assert curso.status == StatusCurso.RASCUNHO


@pytest.mark.django_db
def test_primeiro_aluno_alocado_tira_o_curso_do_rascunho(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO
```

Acrescente a `apps/cursos/tests/test_versoes.py`:

```python
@pytest.mark.django_db
def test_nova_versao_nasce_com_o_responsavel_na_equipe(curso_publicado, professor):
    nova = services.abrir_nova_versao(curso_publicado, por=professor, motivo="Atualizar dados")
    assert nova.tem_membro(professor)


@pytest.mark.django_db
def test_nova_versao_nao_herda_a_equipe_de_alunos(curso_publicado, professor, aluno):
    """Spec 4.5: a nova versao e produzida por outra equipe. So o responsavel vem."""
    services.adicionar_membro(curso_publicado, aluno, por=professor)
    nova = services.abrir_nova_versao(curso_publicado, por=professor, motivo="Atualizar dados")
    assert nova.tem_membro(aluno) is False
```

Use nesses dois testes a fixture de curso publicado que `test_versoes.py` já
utiliza; abra o arquivo e reaproveite o nome exato dela em vez de criar outra.

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/cursos/tests/test_criacao.py apps/cursos/tests/test_versoes.py -v`
Expected: FAIL. `test_responsavel_entra_na_equipe_ao_criar` e
`test_nova_versao_nasce_com_o_responsavel_na_equipe` falham em `assert False`;
os outros três passam desde já (são as regras que **não** podem quebrar).

- [ ] **Step 3: Pôr o responsável na equipe na criação**

Em `apps/cursos/services.py`, no fim de `criar_curso`, antes do `return`:

```python
    # MembroEquipe direto, e nao adicionar_membro: aquele servico tira o curso de
    # RASCUNHO no primeiro membro, e o responsavel entrando na criacao faria todo
    # curso nascer EM_PRODUCAO, matando um estado que a spec 5 usa. Proposta com
    # uma pessoa so ainda e proposta.
    MembroEquipe.objects.create(curso=curso, pessoa=curso.professor_responsavel)
    return curso
```

Em `abrir_nova_versao`, logo depois do `definir_temas(nova, ...)`:

```python
    # A equipe de alunos nao vem (spec 4.5), mas o responsavel vem: ele e membro
    # de todo curso que responde (spec 4.1), e a v2 nasceria sem ninguem.
    MembroEquipe.objects.create(curso=nova, pessoa=nova.professor_responsavel)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest apps/cursos/tests/test_criacao.py apps/cursos/tests/test_versoes.py -v`
Expected: PASS.

- [ ] **Step 5: Prender a deduplicação da fila**

`enfileirar` deduplica desde sempre e nunca teve teste. Com o responsável entrando
na equipe, ela passa a ser o que impede o aviso de publicação de chegar duas vezes
na caixa de quem aprovou o curso, então é hora de prendê-la.

Acrescente a `apps/notificacoes/tests/test_fila.py`:

```python
@pytest.mark.django_db
def test_enfileirar_nao_repete_destinatario():
    """A mesma pessoa em duas listas somadas (a equipe e o responsavel, em
    publicar_curso) nao pode virar dois e-mails iguais na caixa dela."""
    enfileirar(
        evento="TESTE",
        destinatarios=["ana@ufsm.br", "bruno@ufsm.br", "ana@ufsm.br"],
        assunto="Assunto",
        corpo="Corpo",
    )
    assert Notificacao.objects.filter(destinatario="ana@ufsm.br").count() == 1
    assert Notificacao.objects.count() == 2


@pytest.mark.django_db
def test_enfileirar_ignora_destinatario_vazio():
    """Prende a outra metade do mesmo `if d`: sem ela, um curso sem responsavel
    gravaria uma notificacao para endereco vazio, que o cron tentaria para sempre."""
    enfileirar(evento="TESTE", destinatarios=["ana@ufsm.br", "", None], assunto="A", corpo="C")
    assert Notificacao.objects.count() == 1
```

Confira no topo de `test_fila.py` como `enfileirar` e `Notificacao` já são
importados ali e siga o mesmo import, em vez de acrescentar outro.

- [ ] **Step 6: Rodar e provar por deleção**

Run: `pytest apps/notificacoes/tests/test_fila.py -v`
Expected: PASS desde já. Estes dois testes não corrigem defeito: eles prendem
comportamento que existe e estava solto.

Comite, depois troque `sorted({d for d in destinatarios if d})` por
`sorted(destinatarios)` em `apps/notificacoes/services.py` e rode: os dois testes
precisam ficar vermelhos, cada um pelo seu motivo. Restaure.

Deixe `publicar_curso` como está. A lista somada continua tendo o endereço
repetido, e é a fila que resolve, num lugar só.

- [ ] **Step 7: Migração de dados para os cursos que já existem**

Run: `python manage.py makemigrations cursos --empty --name responsavel_na_equipe`

Escreva `apps/cursos/migrations/0013_responsavel_na_equipe.py`:

```python
from django.db import migrations


def por_o_responsavel_na_equipe(apps, schema_editor):
    """Cursos criados antes do Plano 6 tem o responsavel fora da equipe.

    Sem esta migracao a invariante "o responsavel e membro" valeria so para curso
    novo, e todo codigo que confia nela (a consulta de `meus_cursos`, a listagem
    de equipe) trataria os cursos antigos como excecao silenciosa.
    """
    Curso = apps.get_model("cursos", "Curso")
    MembroEquipe = apps.get_model("cursos", "MembroEquipe")
    for curso in Curso.objects.all().iterator():
        MembroEquipe.objects.get_or_create(curso=curso, pessoa_id=curso.professor_responsavel_id)


def tirar_o_responsavel_da_equipe(apps, schema_editor):
    """Reversa: desfaz exatamente o que a de ida criou, e nada alem disso.

    Nao apaga membro nenhum que nao seja o responsavel; a equipe de alunos nao
    tem por que sumir porque alguem voltou uma migracao.
    """
    Curso = apps.get_model("cursos", "Curso")
    MembroEquipe = apps.get_model("cursos", "MembroEquipe")
    for curso in Curso.objects.all().iterator():
        MembroEquipe.objects.filter(curso=curso, pessoa_id=curso.professor_responsavel_id).delete()


class Migration(migrations.Migration):
    dependencies = [("cursos", "0012_membroequipe_pessoa")]
    operations = [migrations.RunPython(por_o_responsavel_na_equipe, tirar_o_responsavel_da_equipe)]
```

`get_or_create` e não `create`: a migração precisa poder rodar num banco onde
alguém já tenha vinculado o responsável à mão, sem estourar a unicidade.

Run: `python manage.py migrate`
Run: `python manage.py migrate cursos 0012 && python manage.py migrate`
(prova que a reversa funciona; sem isso ela é código que ninguém nunca executou)

- [ ] **Step 8: Simplificar a consulta de "meus cursos"**

`apps/cursos/views/aluno.py:19` filtra
`Q(membros__pessoa=request.user) | Q(professor_responsavel=request.user)`. Com o
responsável sempre na equipe, e com a migração do Step 7 valendo para os cursos
antigos, o segundo termo é morto.

Antes de apagá-lo, prove que é mesmo morto: apague só ele, rode `pytest`, e
confira que continua verde. Se algum teste falhar, existe caminho que cria `Curso`
sem membro e a invariante não vale; nesse caso **não** apague, e anote qual
caminho é para tratá-lo. Se ficar verde, deixe apagado e escreva o teste que
prende a regra nova:

```python
@pytest.mark.django_db
def test_responsavel_ve_o_proprio_curso_em_meus_cursos(client, dados_curso, professor):
    """Depois que o `Q(professor_responsavel=...)` saiu da consulta, e o vinculo
    de equipe que poe o curso nesta tela. Se alguem criar Curso sem membro, este
    teste e quem avisa."""
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.get(reverse("meus_cursos"))
    assert curso.titulo in resposta.content.decode()
```

- [ ] **Step 9: Suíte inteira e commit**

Run: `pytest`
Expected: PASS.

```bash
git add -A
git commit -m "feat(cursos): o responsavel e membro da equipe do curso que responde

Ser responsavel e formalidade que atribui a revisao, nao dispensa de produzir
(spec 4.1). Ele entra na equipe na criacao e na abertura de nova versao.

Tres armadilhas fechadas junto:

- a criacao grava MembroEquipe direto, sem adicionar_membro, senao todo curso
  nasceria EM_PRODUCAO e o estado RASCUNHO nunca seria observado;
- abrir_nova_versao cria Curso direto e nao copia equipe (spec 4.5), entao a v2
  nascia sem o responsavel;
- publicar_curso soma a equipe ao e-mail do responsavel, que agora esta nos dois
  lados. Nao virou e-mail repetido porque enfileirar ja deduplica; o que faltava
  era teste dessa deduplicacao, e ele entra aqui.

A migracao de dados poe o responsavel na equipe dos cursos que ja existiam; sem
ela a invariante valeria so para curso novo."
```

---

### Task 3: a proposta nasce só com o título

**Files:**
- Modify: `apps/cursos/models/curso.py` (campos da ficha aceitam vazio)
- Modify: `apps/cursos/forms.py` (`PropostaForm`)
- Modify: `apps/cursos/services.py` (`criar_curso` e a edição corrente)
- Modify: `apps/cursos/validacoes.py` (`resumo` no portão)
- Modify: `apps/cursos/views/professor.py` (`nova_proposta`)
- Modify: `templates/cursos/nova_proposta.html`
- Create: `apps/cursos/migrations/0014_ficha_opcional.py`
- Test: `apps/cursos/tests/test_criacao.py`, `apps/cursos/tests/test_validacoes.py`

**Interfaces:**
- Produces: `forms.PropostaForm` (campo único `titulo`);
  `services.criar_curso(**dados)` preenchendo `edicao` quando ausente.

**Nota sobre `Curso.clean()`:** ele **não** precisa mudar. As regras cruzadas são
`if self.tipo_publico == ESCOLAR: ... elif == COMUNITARIO: ...`; com
`tipo_publico` vazio nenhum ramo roda. Não acrescente um `if self.tipo_publico:`
por fora: seria um envelope que nunca altera resultado nenhum.

- [ ] **Step 1: Escrever os testes que falham**

Acrescente a `apps/cursos/tests/test_criacao.py`:

```python
@pytest.mark.django_db
def test_proposta_nasce_so_com_titulo(edicao, professor):
    curso = services.criar_curso(titulo="Robotica com sucata", professor_responsavel=professor)
    assert curso.pk is not None
    assert curso.edicao == edicao
    assert curso.resumo == ""
    assert curso.carga_horaria is None


@pytest.mark.django_db
def test_proposta_sem_edicao_aberta_e_recusada(professor, db):
    """Curso.edicao continua PROTECT e nao nula (restricao entre planos). Sem
    edicao corrente a proposta precisa recusar com mensagem, nunca gravar nulo."""
    from apps.edicoes.models import Edicao

    Edicao.objects.filter(ativa=True).update(ativa=False)
    with pytest.raises(ValidationError) as erro:
        services.criar_curso(titulo="Robotica com sucata", professor_responsavel=professor)
    assert "edição" in str(erro.value).lower()
```

Acrescente a `apps/cursos/tests/test_validacoes.py`:

```python
@pytest.mark.django_db
def test_resumo_vazio_e_pendencia_do_curso(curso):
    """O resumo deixou de ser obrigatorio na criacao, entao alguem precisa cobra-lo
    antes do catalogo. O portao e onde isso mora."""
    curso.resumo = ""
    curso.save()
    faltas = validacoes.dados_do_curso(curso)
    assert any("resumo" in f.lower() for f in faltas)


@pytest.mark.django_db
def test_curso_completo_nao_tem_pendencia_de_resumo(curso):
    """Prende o outro lado: com resumo preenchido a cobranca some. Sem este par, um
    `faltas.append` incondicional passaria no teste de cima."""
    assert not any("resumo" in f.lower() for f in validacoes.dados_do_curso(curso))
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/cursos/tests/test_criacao.py apps/cursos/tests/test_validacoes.py -v`
Expected: FAIL. A criação falha em `ValidationError` de campos obrigatórios; o
teste do resumo falha porque `dados_do_curso` ainda não o cobra.

- [ ] **Step 3: Deixar os campos da ficha aceitarem vazio**

Em `apps/cursos/models/curso.py`:

```python
    resumo = models.TextField("resumo", blank=True)
    tipo_publico = models.CharField(
        "tipo de público", max_length=20, choices=TipoPublico.choices, blank=True
    )
    carga_horaria = models.PositiveSmallIntegerField(
        "carga horária (horas)", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    formato = models.CharField("formato", max_length=20, choices=Formato.choices, blank=True)
```

`carga_horaria` ganha `null=True` porque é numérico: em campo numérico o vazio do
banco é `NULL`, e `blank=True` sozinho só afeta formulário. `MinValueValidator(1)`
fica: ele não roda sobre `None`, então continua barrando carga horária zero.

Run: `python manage.py makemigrations cursos --name ficha_opcional && python manage.py migrate`

- [ ] **Step 4: Formulário só com o título**

Em `apps/cursos/forms.py`, substitua `CursoForm` por:

```python
class PropostaForm(forms.ModelForm):
    """A criacao pede o titulo e mais nada (spec 4.3). O resto e trabalho da
    equipe, cobrado no portao de completude."""

    class Meta:
        model = Curso
        fields = ["titulo"]
```

- [ ] **Step 5: A edição corrente entra sozinha**

Em `apps/cursos/services.py`, no começo de `criar_curso`, depois do `garante`:

```python
    if "edicao" not in dados:
        # Import adiado, como abrir_nova_versao ja faz neste arquivo.
        from apps.edicoes.models import Edicao

        corrente = Edicao.objects.corrente()
        if corrente is None:
            raise ValidationError(
                "Nenhuma edição da disciplina está aberta. Peça à coordenação para "
                "abrir a edição corrente antes de propor um curso."
            )
        dados["edicao"] = corrente
```

- [ ] **Step 6: `resumo` no portão de completude**

Em `apps/cursos/validacoes.py`, dentro de `dados_do_curso`, como primeira falta:

```python
    if not (curso.resumo or "").strip():
        faltas.append("Escreva o resumo do curso.")
```

- [ ] **Step 7: A view e o template**

Em `apps/cursos/views/professor.py`, `nova_proposta` passa a usar `PropostaForm`
e some com o tratamento de `temas` (o formulário não tem mais esse campo):

```python
@login_required
@require_http_methods(["GET", "POST"])
def nova_proposta(request):
    permissions.garante(
        permissions.pode_criar_curso(request.user), "Somente professor cria proposta de curso."
    )
    form = PropostaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            curso = services.criar_curso(
                professor_responsavel=request.user, **form.cleaned_data
            )
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        else:
            messages.success(
                request, "Proposta criada. Monte a equipe e preencha a ficha do curso."
            )
            return redirect("equipe", pk=curso.pk)
    return render(request, "cursos/nova_proposta.html", {"form": form})
```

O `try` é necessário: sem edição aberta, `criar_curso` levanta `ValidationError` e
a view devolveria 500.

Troque o import `from apps.cursos.forms import CursoForm` por
`from apps.cursos.forms import PropostaForm`.

Em `templates/cursos/nova_proposta.html`, deixe o texto de apoio dizendo o que
mudou. Abra o arquivo, mantenha a estrutura que já existe e ajuste a explicação
para: "Dê um título à proposta. Ele pode ser ajustado depois. O resto da ficha
(resumo, público-alvo, carga horária e formato) é preenchido pela equipe."

- [ ] **Step 8: Rodar tudo**

Run: `pytest`
Expected: PASS. Testes antigos que criavam curso passando `resumo`/`carga_horaria`
continuam válidos: os campos ficaram opcionais, não sumiram.

- [ ] **Step 9: Provar por deleção**

Comite, depois apague **só** o `raise ValidationError` da edição ausente
(Step 5) e rode `pytest`: `test_proposta_sem_edicao_aberta_e_recusada` precisa
ficar vermelho. Restaure. Depois apague **só** o `faltas.append` do resumo e
confirme que `test_resumo_vazio_e_pendencia_do_curso` fica vermelho. Restaure.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat(cursos): a proposta nasce so com o titulo

CursoForm vira PropostaForm com um campo. resumo, tipo_publico, carga_horaria e
formato passam a aceitar vazio no banco, e a edicao vem de Edicao.corrente().

O que impede curso incompleto de avancar nao muda de lugar: dados_do_curso ja
rodava na revisao do Plano de Ensino e na submissao a coordenacao. So o resumo
precisou entrar nessa lista, porque deixou de ser cobrado na criacao.

Curso.clean() nao mudou de proposito: com tipo_publico vazio nenhum dos dois
ramos roda, e envolve-lo num if seria envelope que nao altera resultado."
```

---

### Task 4: a tela da ficha do curso

Hoje `CursoForm` só aparece na criação: depois de proposto, os campos do curso não
têm tela nenhuma, e o comentário de `submeter_ao_coordenador` já dizia "o curso
pode ser editado depois do plano aprovado" sobre uma edição que não existia.

**Files:**
- Modify: `apps/cursos/choices.py` (`STATUS_EDITAVEIS`)
- Modify: `apps/cursos/permissions.py` (`pode_editar_ficha`)
- Modify: `apps/cursos/forms.py` (`FichaCursoForm`)
- Modify: `apps/cursos/services.py` (`atualizar_ficha`)
- Modify: `apps/cursos/views/professor.py`, `apps/cursos/views/__init__.py`, `apps/cursos/urls.py`
- Create: `templates/cursos/ficha.html`
- Modify: `templates/cursos/curso.html` (link para a ficha)
- Test: `apps/cursos/tests/test_ficha.py` (novo)

**Interfaces:**
- Consumes: `permissions.garante`, `services.definir_temas(curso, temas, por)`.
- Produces: `permissions.pode_editar_ficha(usuario, curso) -> bool`;
  `services.atualizar_ficha(curso, dados, por) -> Curso`;
  url `ficha` em `cursos/<int:pk>/ficha/`.

- [ ] **Step 1: Escrever `apps/cursos/tests/test_ficha.py`**

```python
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.cursos import permissions, services
from apps.cursos.choices import Formato, StatusCurso, TipoPublico
from apps.cursos.models import MembroEquipe


@pytest.fixture
def proposta(edicao, professor):
    return services.criar_curso(titulo="Robotica com sucata", professor_responsavel=professor)


@pytest.mark.django_db
def test_membro_da_equipe_edita_a_ficha(proposta, professor, aluno):
    services.adicionar_membro(proposta, aluno, por=professor)
    services.atualizar_ficha(
        proposta,
        {"titulo": "Robotica com sucata reciclada", "resumo": "Oficina de montagem.",
         "tipo_publico": TipoPublico.ESCOLAR, "etapa_ano": "EF05", "publico_descricao": "",
         "referencial": None, "competencias": [], "carga_horaria": 8,
         "formato": Formato.PRESENCIAL, "pre_requisitos": "", "temas": [], "palavras_chave": ""},
        por=aluno,
    )
    proposta.refresh_from_db()
    assert proposta.titulo == "Robotica com sucata reciclada"
    assert proposta.carga_horaria == 8


@pytest.mark.django_db
def test_quem_nao_e_da_equipe_nao_edita_a_ficha(proposta, outro_aluno):
    with pytest.raises(PermissionDenied):
        services.atualizar_ficha(proposta, {"titulo": "Invadido"}, por=outro_aluno)


@pytest.mark.django_db
def test_ficha_de_curso_publicado_nao_e_editavel(proposta, professor):
    """Curso publicado muda por nova versao (spec 4.5), nunca por edicao no lugar:
    editar direto trocaria embaixo do catalogo um curso que alguem ja solicitou."""
    proposta.status = StatusCurso.PUBLICADO
    proposta.save(update_fields=["status"])
    assert permissions.pode_editar_ficha(professor, proposta) is False


@pytest.mark.django_db
def test_ficha_em_producao_e_editavel(proposta, professor, aluno):
    """Prende o outro lado do teste acima: se STATUS_EDITAVEIS ficasse vazio, so
    aquele passaria."""
    services.adicionar_membro(proposta, aluno, por=professor)
    proposta.refresh_from_db()
    assert proposta.status == StatusCurso.EM_PRODUCAO
    assert permissions.pode_editar_ficha(aluno, proposta) is True


@pytest.mark.django_db
def test_get_da_ficha_recusa_quem_nao_e_da_equipe(client, proposta, outro_aluno):
    """Por GET de proposito. A view chama atualizar_ficha, que confere permissao
    tambem; num POST, afrouxar a guarda da view nao quebraria nada, porque o
    servico recusaria igual e o teste veria o mesmo 403. So o GET isola a view."""
    client.force_login(outro_aluno)
    resposta = client.get(reverse("ficha", args=[proposta.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_get_da_ficha_abre_para_membro(client, proposta, professor):
    client.force_login(professor)
    resposta = client.get(reverse("ficha", args=[proposta.pk]))
    assert resposta.status_code == 200


@pytest.mark.django_db
def test_competencia_de_outro_referencial_e_recusada(proposta, professor, referencial_alheio):
    """A ficha nao filtra o select por referencial: quem escolhe competencia de
    outro referencial e barrado na validacao, com mensagem."""
    from apps.cursos.forms import FichaCursoForm

    form = FichaCursoForm(
        {"titulo": "T", "resumo": "R", "tipo_publico": TipoPublico.ESCOLAR, "etapa_ano": "EF05",
         "carga_horaria": 8, "formato": Formato.PRESENCIAL,
         "competencias": [referencial_alheio.competencias.first().pk]},
        instance=proposta,
    )
    assert form.is_valid() is False
    assert "competencias" in form.errors
```

A fixture `referencial_alheio` precisa criar um `Referencial` com ao menos uma
`Competencia`, diferente do referencial do curso. Veja em
`apps/referenciais/tests/` como os testes de lá montam esses objetos e siga o
mesmo formato, colocando a fixture no topo de `test_ficha.py`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/cursos/tests/test_ficha.py -v`
Expected: FAIL, com `AttributeError` em `permissions.pode_editar_ficha` e
`services.atualizar_ficha`, e `NoReverseMatch` para `ficha`.

- [ ] **Step 3: `STATUS_EDITAVEIS` e a permissão**

Em `apps/cursos/choices.py`, no fim:

```python
# Onde a ficha do curso ainda pode mudar. Publicado nao entra: curso no catalogo
# muda por nova versao (spec 4.5). Vive aqui, e nao em services.py, porque
# permissions.py precisa dele e nao pode importar services (services importa
# permissions, e o ciclo fecharia).
STATUS_EDITAVEIS = (StatusCurso.RASCUNHO, StatusCurso.EM_PRODUCAO, StatusCurso.DEVOLVIDO)
```

Em `apps/cursos/permissions.py`:

```python
def pode_editar_ficha(usuario, curso):
    """Quem preenche a ficha do curso (spec 10): qualquer membro da equipe, o
    professor responsavel e o coordenador, enquanto o curso esta em producao.

    Escrita por extenso, e nao como alias de pode_ver_curso, porque as duas regras
    sao diferentes: ver um curso e ler; a ficha e o que vai ao catalogo publico.
    """
    from apps.cursos.choices import STATUS_EDITAVEIS

    if curso.status not in STATUS_EDITAVEIS:
        return False
    if usuario.e_coordenador:
        return True
    return e_responsavel(usuario, curso) or curso.tem_membro(usuario)
```

- [ ] **Step 4: O formulário completo**

Em `apps/cursos/forms.py`:

```python
class FichaCursoForm(forms.ModelForm):
    """A ficha que a equipe preenche depois da proposta (spec 4.3)."""

    class Meta:
        model = Curso
        fields = [
            "titulo", "resumo", "tipo_publico", "etapa_ano", "publico_descricao",
            "referencial", "competencias", "carga_horaria", "formato", "pre_requisitos",
            "temas", "palavras_chave",
        ]
        widgets = {"resumo": forms.Textarea(attrs={"rows": 4})}

    def clean(self):
        dados = super().clean()
        referencial = dados.get("referencial")
        competencias = dados.get("competencias") or []
        # O select mostra todas as competencias, sem filtro por referencial: filtrar
        # no cliente exigiria JS de dependencia entre campos, e este projeto so
        # aceita JS proprio onde HTMX nao alcanca. A regra fica na validacao, onde
        # tem mensagem e teste.
        fora = [c for c in competencias if c.referencial_id != getattr(referencial, "pk", None)]
        if fora:
            codigos = ", ".join(c.codigo for c in fora)
            raise ValidationError(
                {"competencias": f"Estas competências não são do referencial escolhido: {codigos}."}
            )
        return dados
```

- [ ] **Step 5: O serviço**

Em `apps/cursos/services.py`:

```python
@transaction.atomic
def atualizar_ficha(curso, dados, por):
    """Grava a ficha preenchida pela equipe (spec 4.3 e 10).

    `temas` sai por definir_temas, e nao por curso.temas.set(): coluna gerada nao
    alcanca M2M, e e aquele servico que reindexa vetor_temas. Foi uma tela
    escrevendo `temas` direto que sumiu com cursos da busca no Plano 2.
    """
    permissions.garante(
        permissions.pode_editar_ficha(por, curso),
        "Somente a equipe do curso edita a ficha, e apenas enquanto ele está em produção.",
    )
    dados = dict(dados)
    temas = dados.pop("temas", None)
    competencias = dados.pop("competencias", None)
    for campo, valor in dados.items():
        setattr(curso, campo, valor)
    curso.save()
    if competencias is not None:
        curso.competencias.set(competencias)
    if temas is not None:
        definir_temas(curso, temas, por=por)
    return curso
```

- [ ] **Step 6: View, url e template**

Em `apps/cursos/views/professor.py`:

```python
@login_required
@require_http_methods(["GET", "POST"])
def ficha(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    # Guarda propria da view, alem da do servico: e ela que responde ao GET, onde
    # o servico nem e chamado.
    permissions.garante(
        permissions.pode_editar_ficha(request.user, curso),
        "Somente a equipe do curso edita a ficha, e apenas enquanto ele está em produção.",
    )
    form = FichaCursoForm(request.POST or None, instance=curso)
    if request.method == "POST" and form.is_valid():
        services.atualizar_ficha(curso, form.cleaned_data, por=request.user)
        messages.success(request, "Ficha do curso atualizada.")
        return redirect("curso", pk=curso.pk)
    return render(request, "cursos/ficha.html", {"curso": curso, "form": form})
```

Em `apps/cursos/urls.py`, depois da linha de `equipe`:

```python
    path("cursos/<int:pk>/ficha/", views.ficha, name="ficha"),
```

Em `apps/cursos/views/__init__.py`, acrescente `ficha` ao import de
`apps.cursos.views.professor` e à lista `__all__`, mantendo a ordem alfabética
que o arquivo já usa.

Crie `templates/cursos/ficha.html` seguindo a estrutura de
`templates/cursos/nova_proposta.html` (mesmos blocos `titulo` e `conteudo`,
mesmas classes `trabalho`, `cabecalho-pagina`, `faixa`). O formulário renderiza
`{{ form.as_p }}` dentro de `<form method="post">` com `{% csrf_token %}` e um
botão "Salvar ficha". Acrescente, acima do formulário, a lista do que ainda falta:

```html
{% if pendencias %}
  <ul class="pendencias">
    {% for falta in pendencias %}<li>{{ falta }}</li>{% endfor %}
  </ul>
{% endif %}
```

e passe `"pendencias": validacoes.dados_do_curso(curso)` no contexto da view.
É a mesma lista que o portão vai cobrar; mostrá-la aqui evita a ida e volta.

Em `templates/cursos/curso.html`, junto dos botões de ação já existentes,
acrescente o link, visível só para quem pode editar:

```html
{% if pode_editar_ficha %}
  <a class="botao botao-linha" href="{% url 'ficha' curso.pk %}">Editar ficha</a>
{% endif %}
```

e passe `"pode_editar_ficha": permissions.pode_editar_ficha(request.user, curso)`
no contexto da view `curso`, em `apps/cursos/views/aluno.py`. A decisão fica no
Python; o template só pergunta pelo resultado.

- [ ] **Step 7: Rodar e ver passar**

Run: `pytest apps/cursos/tests/test_ficha.py -v`
Expected: PASS.

Run: `pytest`
Expected: PASS.

- [ ] **Step 8: Provar por deleção, uma guarda de cada vez**

Comite antes. Depois, um por vez, restaurando entre cada um:

1. Apague o `permissions.garante` **da view** `ficha`. `test_get_da_ficha_recusa_quem_nao_e_da_equipe` precisa ficar vermelho.
2. Apague o `permissions.garante` **do serviço** `atualizar_ficha`. `test_quem_nao_e_da_equipe_nao_edita_a_ficha` precisa ficar vermelho.
3. Apague o `if curso.status not in STATUS_EDITAVEIS` de `pode_editar_ficha`. `test_ficha_de_curso_publicado_nao_e_editavel` precisa ficar vermelho.
4. Apague o `raise ValidationError` de competências em `FichaCursoForm.clean`. `test_competencia_de_outro_referencial_e_recusada` precisa ficar vermelho.

Se algum deles ficar verde, escreva o teste que falta antes de restaurar.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(cursos): tela da ficha do curso, editavel pela equipe

Fecha uma divida antiga: submeter_ao_coordenador ja dizia em comentario que o
curso podia ser editado depois do plano aprovado, e nao existia tela nenhuma de
edicao. CursoForm so aparecia na criacao.

pode_editar_ficha e escrita por extenso em vez de alias de pode_ver_curso: ver e
ler, e a ficha e o que vai ao catalogo publico. Curso publicado fica de fora, que
e a regra da spec 4.5 - no catalogo se muda por nova versao, nunca no lugar.

A guarda da view existe alem da do servico e tem teste por GET, que e o unico
caminho onde ela responde sozinha."
```

---

### Task 5: alocar professor na equipe

**Files:**
- Modify: `apps/cursos/services.py` (`alocar_professor`)
- Modify: `apps/cursos/views/professor.py` (`equipe`)
- Modify: `templates/cursos/equipe.html`
- Test: `apps/cursos/tests/test_alocacao.py`

**Interfaces:**
- Consumes: `services.adicionar_membro(curso, pessoa, por)`.
- Produces: `services.alocar_professor(curso, professor, por) -> MembroEquipe`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescente a `apps/cursos/tests/test_alocacao.py`:

```python
@pytest.mark.django_db
def test_professor_e_alocado_na_equipe(curso, professor, outro_professor):
    membro = services.alocar_professor(curso, outro_professor, por=professor)
    assert membro.pessoa == outro_professor
    assert curso.tem_membro(outro_professor)


@pytest.mark.django_db
def test_alocar_professor_nao_manda_convite(curso, professor, outro_professor):
    """Professor ja tem conta: quem cria conta de professor e a coordenacao. Um
    convite aqui seria primeiro acesso para quem ja entra no sistema."""
    from apps.notificacoes.models import Notificacao

    antes = Notificacao.objects.count()
    services.alocar_professor(curso, outro_professor, por=professor)
    assert Notificacao.objects.count() == antes


@pytest.mark.django_db
def test_alocar_aluno_pelo_caminho_de_professor_e_recusado(curso, professor, aluno):
    with pytest.raises(ValidationError):
        services.alocar_professor(curso, aluno, por=professor)


@pytest.mark.django_db
def test_professor_de_fora_nao_aloca_ninguem(curso, outro_professor, coordenador):
    with pytest.raises(PermissionDenied):
        services.alocar_professor(curso, coordenador, por=outro_professor)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/cursos/tests/test_alocacao.py -v`
Expected: FAIL, `AttributeError: module 'apps.cursos.services' has no attribute 'alocar_professor'`.

- [ ] **Step 3: O serviço**

Em `apps/cursos/services.py`, ao lado de `alocar_aluno`:

```python
def alocar_professor(curso, professor, por):
    """Poe um professor que ja tem conta na equipe de producao (spec 4.1).

    Sem convite, ao contrario de alocar_aluno: quem cria conta de professor e a
    coordenacao, e mandar primeiro acesso para quem ja entra no sistema seria
    convite que nao serve para nada.
    """
    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    if professor is None or not professor.e_professor:
        raise ValidationError("Escolha um professor ou coordenador para a equipe.")
    return adicionar_membro(curso, professor, por=por)
```

- [ ] **Step 4: A view aceita os dois formulários**

Em `apps/cursos/views/professor.py`, `equipe` passa a distinguir a origem do POST
por um campo escondido `acao`:

```python
@login_required
@require_http_methods(["GET", "POST"])
def equipe(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(permissions.pode_gerir_equipe(request.user, curso), "Curso de outro professor.")
    if request.method == "POST":
        if request.POST.get("acao") == "professor":
            _alocar_professor(request, curso)
        else:
            _alocar_aluno(request, curso)
        return redirect("equipe", pk=curso.pk)
    return render(
        request,
        "cursos/equipe.html",
        {"curso": curso, "professores": _professores_disponiveis(curso)},
    )


def _professores_disponiveis(curso):
    """Professores e coordenadores que ainda nao estao na equipe deste curso."""
    return Usuario.objects.filter(
        papel__in=(Usuario.PROFESSOR, Usuario.COORDENADOR), is_active=True
    ).exclude(equipes__curso=curso).order_by("nome_completo")


def _alocar_professor(request, curso):
    escolhido = Usuario.objects.filter(pk=request.POST.get("professor") or 0).first()
    try:
        membro = services.alocar_professor(curso, escolhido, por=request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, f"{membro.pessoa.nome_completo} entrou na equipe.")


def _alocar_aluno(request, curso):
    try:
        membro = services.alocar_aluno(
            curso,
            nome=request.POST.get("nome", ""),
            email=request.POST.get("email", ""),
            por=request.user,
            base_url=request.build_absolute_uri("/").rstrip("/"),
        )
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(
            request,
            f"{membro.pessoa.nome_completo} entrou na equipe. "
            "Enviamos o convite de primeiro acesso por e-mail.",
        )
```

`_professores_disponiveis` exclui quem já está na equipe usando o `related_name`
`equipes` de `MembroEquipe.pessoa`, então o responsável também some da lista: ele
é membro desde a criação.

- [ ] **Step 5: O template**

Em `templates/cursos/equipe.html`, dentro do `<aside class="lateral">`,
acrescente ao formulário existente o campo escondido que o identifica:

```html
<input type="hidden" name="acao" value="aluno">
```

e, depois dele, o segundo formulário:

```html
<h2>Alocar professor</h2>
<p>Professores e coordenadores já cadastrados. Quem entra por aqui produz material
   como qualquer membro, mas quem aprova os entregáveis continua sendo o professor
   responsável.</p>
<form method="post">
  {% csrf_token %}
  <input type="hidden" name="acao" value="professor">
  <div class="campo">
    <label for="id_professor">Professor</label>
    <select name="professor" id="id_professor" required>
      {% for pessoa in professores %}
        <option value="{{ pessoa.pk }}">{{ pessoa.nome_completo }}</option>
      {% empty %}
        <option value="" disabled>Nenhum professor disponível</option>
      {% endfor %}
    </select>
  </div>
  <button type="submit" class="botao-largo">Alocar professor</button>
</form>
```

Na listagem "Na equipe", marque o responsável:

```html
{% for membro in curso.membros.all %}
  <li>{{ membro.pessoa.nome_completo }}
    {% if membro.pessoa_id == curso.professor_responsavel_id %}<span class="etiqueta">responsável</span>{% endif %}
  </li>
{% empty %}<li>Equipe vazia.</li>{% endfor %}
```

- [ ] **Step 6: Rodar tudo e commitar**

Run: `pytest`
Expected: PASS.

Comite, apague **só** o `if professor is None or not professor.e_professor` e
confirme que `test_alocar_aluno_pelo_caminho_de_professor_e_recusado` fica
vermelho. Restaure.

```bash
git add -A
git commit -m "feat(cursos): alocar professor na equipe de producao

Sem convite, ao contrario de alocar_aluno: professor ja tem conta, e quem cria
conta de professor e a coordenacao. Convite de primeiro acesso para quem ja
entra no sistema nao serviria para nada.

A lista exclui quem ja esta na equipe pelo related_name `equipes`, o que tira o
responsavel junto: ele e membro desde a criacao."
```

---

### Task 6: remover alguém da equipe

**Files:**
- Modify: `apps/cursos/services.py` (`remover_membro`)
- Modify: `apps/cursos/views/professor.py`, `apps/cursos/views/__init__.py`, `apps/cursos/urls.py`
- Modify: `templates/cursos/equipe.html`
- Test: `apps/cursos/tests/test_alocacao.py`

**Interfaces:**
- Produces: `services.remover_membro(curso, membro, por) -> None`;
  url `remover_da_equipe` em `cursos/<int:pk>/equipe/remover/<int:membro_pk>/`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescente a `apps/cursos/tests/test_alocacao.py`:

```python
@pytest.mark.django_db
def test_membro_e_removido_da_equipe(curso, professor, aluno):
    membro = services.adicionar_membro(curso, aluno, por=professor)
    services.remover_membro(curso, membro, por=professor)
    assert curso.tem_membro(aluno) is False


@pytest.mark.django_db
def test_remover_membro_preserva_o_que_ele_produziu(dados_curso, professor, aluno, arquivo_qualquer):
    """Remover tira o acesso, nao apaga o trabalho (spec 4.1).

    O anexo precisa estar pendurado no curso, e nao solto: um Arquivo avulso
    sobreviveria a qualquer coisa, e o teste passaria mesmo com a regra quebrada.
    E o vinculo com o entregavel que faz a pergunta valer a pena.
    """
    from apps.cursos.choices import TipoEntregavel, TipoMidia
    from apps.cursos.models import Anexo

    curso = services.criar_curso(**dados_curso)
    membro = services.adicionar_membro(curso, aluno, por=professor)
    anexo = Anexo.objects.create(
        entregavel=curso.entregaveis.get(tipo=TipoEntregavel.CARDS),
        tipo_midia=TipoMidia.ARQUIVO,
        arquivo=arquivo_qualquer,
        titulo="Atividade da oficina",
        enviado_por=aluno,
    )
    services.remover_membro(curso, membro, por=professor)
    anexo.refresh_from_db()
    assert anexo.enviado_por == aluno


@pytest.mark.django_db
def test_responsavel_nao_pode_ser_removido(edicao, professor):
    """Sem ele o curso fica sem quem revisa (spec 4.1)."""
    proposta = services.criar_curso(titulo="Robotica", professor_responsavel=professor)
    membro = proposta.membros.get(pessoa=professor)
    with pytest.raises(ValidationError):
        services.remover_membro(proposta, membro, por=professor)


@pytest.mark.django_db
def test_nao_se_remove_membro_de_curso_ja_submetido(curso, professor, aluno):
    """Depois de submetido a coordenacao, quem compoe a equipe e parte do que
    esta sendo julgado (spec 4.1).

    O status e posto na mao, e nao por submeter_ao_coordenador: aquele servico
    exige os cinco entregaveis aprovados e a ficha completa, e montar tudo isso
    aqui faria o teste falhar por meia duzia de motivos que nada tem a ver com a
    regra que ele existe para prender.
    """
    from apps.cursos.choices import StatusCurso

    membro = services.adicionar_membro(curso, aluno, por=professor)
    curso.status = StatusCurso.AGUARDANDO_COORDENADOR
    curso.save(update_fields=["status"])
    with pytest.raises(ValidationError):
        services.remover_membro(curso, membro, por=professor)


@pytest.mark.django_db
def test_aluno_da_equipe_nao_remove_ninguem(curso, professor, aluno, outro_aluno):
    membro = services.adicionar_membro(curso, outro_aluno, por=professor)
    services.adicionar_membro(curso, aluno, por=professor)
    with pytest.raises(PermissionDenied):
        services.remover_membro(curso, membro, por=aluno)


@pytest.mark.django_db
def test_get_da_equipe_recusa_aluno(client, curso, aluno, professor):
    """A guarda da view de equipe, isolada por GET."""
    services.adicionar_membro(curso, aluno, por=professor)
    client.force_login(aluno)
    resposta = client.get(reverse("equipe", args=[curso.pk]))
    assert resposta.status_code == 403
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest apps/cursos/tests/test_alocacao.py -v`
Expected: FAIL, `AttributeError: ... has no attribute 'remover_membro'`.

- [ ] **Step 3: O serviço**

Em `apps/cursos/services.py`:

```python
def remover_membro(curso, membro, por):
    """Tira alguem da equipe. Tira o acesso, nao apaga o trabalho (spec 4.1).

    Anexo, Secao e Revisao guardam quem fez cada coisa por FK propria; apagar o
    vinculo de equipe nao toca nessas linhas, e o material continua com o nome de
    quem o produziu. Nao ha cascata a temer: MembroEquipe nao e pai de nada.
    """
    from apps.cursos.choices import STATUS_EDITAVEIS

    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    if membro.curso_id != curso.pk:
        raise ValidationError("Este membro não é da equipe deste curso.")
    if membro.pessoa_id == curso.professor_responsavel_id:
        raise ValidationError(
            "O professor responsável não sai da equipe: o curso ficaria sem quem revisa."
        )
    if curso.status not in STATUS_EDITAVEIS:
        raise ValidationError(
            "A equipe só muda enquanto o curso está em produção."
        )
    membro.delete()
```

A checagem `membro.curso_id != curso.pk` não é zelo excessivo: a url traz os dois
ids, e sem ela um `membro_pk` de outro curso seria apagado por quem tem permissão
neste.

- [ ] **Step 4: View, url e botão**

Em `apps/cursos/views/professor.py`:

```python
@login_required
@require_POST
def remover_da_equipe(request, pk, membro_pk):
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(permissions.pode_gerir_equipe(request.user, curso), "Curso de outro professor.")
    membro = get_object_or_404(MembroEquipe, pk=membro_pk)
    try:
        services.remover_membro(curso, membro, por=request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, f"{membro.pessoa.nome_completo} saiu da equipe.")
    return redirect("equipe", pk=curso.pk)
```

Acrescente `MembroEquipe` ao import de `apps.cursos.models` no topo do arquivo.

Em `apps/cursos/urls.py`:

```python
    path(
        "cursos/<int:pk>/equipe/remover/<int:membro_pk>/",
        views.remover_da_equipe,
        name="remover_da_equipe",
    ),
```

Em `apps/cursos/views/__init__.py`, acrescente `remover_da_equipe` ao import e ao
`__all__`.

Em `templates/cursos/equipe.html`, na listagem "Na equipe", o botão para quem não
é o responsável:

```html
{% for membro in curso.membros.all %}
  <li>{{ membro.pessoa.nome_completo }}
    {% if membro.pessoa_id == curso.professor_responsavel_id %}
      <span class="etiqueta">responsável</span>
    {% else %}
      <form method="post" action="{% url 'remover_da_equipe' curso.pk membro.pk %}">
        {% csrf_token %}
        <button type="submit" class="botao-linha">Remover</button>
      </form>
    {% endif %}
  </li>
{% empty %}<li>Equipe vazia.</li>{% endfor %}
```

- [ ] **Step 5: Rodar tudo**

Run: `pytest`
Expected: PASS.

- [ ] **Step 6: Provar por deleção, uma de cada vez**

Comite antes. Depois, restaurando entre cada um, apague só:

1. o `if membro.pessoa_id == curso.professor_responsavel_id` (`test_responsavel_nao_pode_ser_removido` fica vermelho);
2. o `if curso.status not in STATUS_EDITAVEIS` (`test_nao_se_remove_membro_de_curso_ja_submetido` fica vermelho);
3. o `if membro.curso_id != curso.pk` (nenhum teste cobre: **escreva** um que remova um membro de outro curso pela url deste e espere `ValidationError`);
4. o `permissions.garante` da view `remover_da_equipe` (`test_get_da_equipe_recusa_aluno` não cobre esta view; confira se algum teste fica vermelho e, se não, escreva o que falta).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(cursos): o responsavel remove alguem da equipe

Remover tira o acesso e preserva a autoria: anexo, secao e revisao guardam quem
fez cada coisa por FK propria, e MembroEquipe nao e pai de nada, entao nao ha
cascata. O teste prende isso conferindo que o Arquivo enviado sobrevive.

Duas recusas alem da permissao: o responsavel nao sai (o curso ficaria sem quem
revisa) e a equipe so muda enquanto o curso esta em producao. E a conferencia de
que o membro e deste curso, porque a url traz os dois ids e sem ela um membro de
outro curso seria apagado por quem tem permissao neste."
```

---

### Task 7: revisão de branch e documentação

As tarefas 1 a 6 foram revisadas uma a uma. Esta olha as costuras entre elas, que
é onde os planos anteriores acharam os defeitos que a revisão por tarefa não pega
(um estado sem saída, um serviço sem chamador, um upload vazando gigabytes).

**Files:**
- Modify: `CLAUDE.md`
- Test: a suíte inteira

- [ ] **Step 1: Enumerar as regras, e só depois olhar os testes**

Escreva a lista das regras que este plano introduz, lida **da spec e deste
documento**, não do código. São ao menos estas dezoito:

1. A equipe aceita professor.
2. `MembroEquipe` não tem mais guarda de papel (e não deve ganhar uma).
3. O responsável é membro desde a criação.
4. A criação não tira o curso de `RASCUNHO`.
5. O primeiro outro membro tira.
6. `abrir_nova_versao` põe o responsável na equipe da v2.
7. `abrir_nova_versao` não copia a equipe de alunos.
8. `enfileirar` não grava o mesmo destinatário duas vezes (regra que já existia e
   passou a ter teste), e ignora endereço vazio.
9. Cursos antigos ganharam o responsável na equipe (migração).
10. A proposta nasce só com o título.
11. Sem edição corrente, a proposta é recusada.
12. `resumo` é cobrado no portão de completude.
13. Professor colaborador enxerga o curso.
14. Professor de fora não enxerga.
15. A ficha é editável por membro, responsável e coordenador.
16. A ficha não é editável em curso publicado.
17. Competência de outro referencial é recusada.
18. O responsável não é removível.

Para cada uma, aponte o teste que a prende e responda: **apagar esta guarda
sozinha faria algum teste falhar?** Onde a resposta for não, escreva o teste.

- [ ] **Step 2: Conferir o que ficou órfão**

Run: `grep -rn "aluno=" apps templates --include="*.py" --include="*.html" | grep -v migrations | grep -v "alocar_aluno\|views/aluno"`
Expected: nenhuma linha referente a `MembroEquipe`.

Run: `grep -rn "CursoForm" apps templates`
Expected: só `FichaCursoForm`. `CursoForm` não pode ter sobrado em lugar nenhum.

Confira, um a um, que todo serviço novo (`atualizar_ficha`, `alocar_professor`,
`remover_membro`) tem chamador fora dos testes:

```bash
for s in atualizar_ficha alocar_professor remover_membro; do
  echo "== $s =="; grep -rn "$s" apps --include="*.py" | grep -v "tests/\|def $s"
done
```

Serviço sem chamador foi defeito real no Plano 3.

- [ ] **Step 3: Conferir a fronteira do módulo e o estilo**

Run: `pytest tests/test_estilo.py -v`
Expected: PASS. Nenhum travessão entrou pelos textos novos de interface.

Run: `pytest`
Expected: PASS, suíte inteira.

- [ ] **Step 4: Rodar o servidor e percorrer o fluxo com os olhos**

```bash
python manage.py runserver
```

Entre como `ana.kirchner@ufsm.br` (senha `senha-de-desenvolvimento`) e percorra:
criar proposta só com título, ver a equipe já com o próprio nome marcado como
responsável, alocar um aluno, alocar um professor, abrir a ficha, salvar com
campos faltando e ver as pendências, preencher, remover o professor alocado,
tentar remover a si mesmo e ver a recusa.

Defeito visual não aparece em suíte verde: neste projeto, cache de CSS, cor de
texto de botão e comentário de template vazando como texto foram todos achados
por olho humano, nunca por teste.

- [ ] **Step 5: Atualizar a CLAUDE.md**

Acrescente à seção de convenções, depois do bloco de papéis do Plano 5:

```markdown
## Equipe de produção (Plano 6)

- `MembroEquipe.pessoa`, não `aluno`: a equipe tem alunos e professores. O modelo
  **não tem `clean()`**, e não deve ganhar um: com a equipe aceitando aluno e
  professor, e todo `Usuario` sendo um dos dois, qualquer guarda de papel ali
  seria incapaz de falhar.
- O professor responsável é membro do curso que responde, desde a criação. Quem
  cria `Curso` fora de `criar_curso` (uma migração, um comando, um `abrir_nova_versao`
  futuro) precisa criar o `MembroEquipe` junto, senão a invariante cai calada.
- A criação grava o `MembroEquipe` **direto**, sem `adicionar_membro`: aquele
  serviço tira o curso de `RASCUNHO`, e o responsável entrando na criação faria
  todo curso nascer `EM_PRODUCAO`.
- A proposta nasce só com o título. O que impede curso incompleto de avançar é
  `validacoes.dados_do_curso`, chamado na revisão do Plano de Ensino e na
  submissão à coordenação. **Campo novo da ficha entra nessa função**, não como
  obrigatoriedade no formulário de criação.
- `STATUS_EDITAVEIS` mora em `choices.py`, e não em `services.py`, porque
  `permissions.py` precisa dele e não pode importar `services` (o ciclo fecharia).
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: convencoes da equipe de producao do Plano 6"
```

- [ ] **Step 7: Fechar a branch**

**REQUIRED SUB-SKILL:** use `superpowers:finishing-a-development-branch`.
