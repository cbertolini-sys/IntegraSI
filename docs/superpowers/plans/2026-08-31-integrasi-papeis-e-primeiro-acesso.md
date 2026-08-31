# IntegraSI — Plano 5: Papéis, Alocação de Aluno e Primeiro Acesso

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coordenador passa a ser um professor com nível de acesso Admin; o professor aloca alunos informando só nome e e-mail; o aluno alocado recebe convite por e-mail e, no primeiro acesso, completa o perfil e define a senha; e a promoção a coordenador ganha tela.

**Architecture:** `e_professor` passa a valer para coordenador — herança por propriedade, sem mexer no `CharField papel`, que continua com um valor por pessoa. CPF e matrícula deixam de ser obrigatórios na criação e passam a ser exigidos pelo próprio conceito de perfil completo, derivado dos campos e não de uma flag paralela. O convite é um modelo próprio com prazo e uso único, e não o gerador de token do reset de senha, cujo prazo é global e compartilhado. O e-mail sai pela fila de `notificacoes`, como todo o resto do sistema.

**Tech Stack:** Django 5.2, PostgreSQL, pytest. Nenhuma dependência nova.

**Spec:** `docs/superpowers/specs/2026-08-25-integrasi-design.md` — a Task 7 deste plano atualiza as seções §2 e §10, que as regras abaixo contradizem.

## Global Constraints

- `save()` chama `full_clean()`, **exceto** quando vem `update_fields` (`CLAUDE.md`, seção Validação).
- Normalização de documentos roda em `full_clean()` **antes** do `validate_unique()`.
- Só `services.py` altera campo de status ou de papel. Nada de lógica de domínio em `post_save`.
- CPF não aparece fora do Django Admin, e mascarado até lá. `search_fields` do admin nunca inclui `cpf`.
- Texto voltado ao usuário em português **acentuado**. Valores gravados (choices, tokens, nomes de rota) sem acento e nunca alterados por passada de texto.
- Nenhum campo de frequência, nota ou certificado (spec §1.1 — fronteira do módulo de produção).
- **Enumere as regras da tarefa antes de conferir os testes contra elas**, e prove cada teste de invariante apagando a guarda que ele prende, **uma de cada vez**, com a árvore commitada antes. O padrão "teste com nome que não exercita a regra" apareceu **dezesseis vezes** nos Planos 2 a 4. Ver `CLAUDE.md`, seção Testes.
- **Teste existente que contradiga uma regra nova não se ajusta em silêncio.** Pare, relate qual teste, o que ele prende hoje e por que a regra nova o invalida.
- Baseline: **697 testes, 0 skips**, `filterwarnings = ["error"]` ativo.

---

### Task 1: Coordenador é professor

**Files:**
- Modify: `apps/contas/models.py`, `apps/cursos/views/professor.py:16-22`, `apps/turmas/forms.py:16-22`
- Test: `apps/contas/tests/test_papeis.py` (criar), `apps/cursos/tests/test_permissoes.py` (modificar)

**Interfaces:**
- Produces: `Usuario.e_professor` passa a devolver `True` para `papel == COORDENADOR`; `Usuario.e_coordenador` inalterado; `Usuario.e_somente_professor` (novo) para onde a distinção importar.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/contas/tests/test_papeis.py`:

```python
import pytest

from apps.contas.models import Usuario


@pytest.mark.django_db
def test_coordenador_tambem_e_professor(coordenador):
    """Regra 1: todo coordenador é, inerentemente, um professor -- com nível de
    acesso Admin por cima. É o que permite a ele criar curso e conduzir turma sem
    uma segunda conta."""
    assert coordenador.e_coordenador is True
    assert coordenador.e_professor is True
    assert coordenador.e_aluno is False


@pytest.mark.django_db
def test_professor_nao_e_coordenador(professor):
    assert professor.e_professor is True
    assert professor.e_coordenador is False


@pytest.mark.django_db
def test_aluno_nao_herda_nada(aluno):
    assert aluno.e_aluno is True
    assert aluno.e_professor is False
    assert aluno.e_coordenador is False


@pytest.mark.django_db
def test_somente_professor_distingue_quem_nao_e_coordenador(professor, coordenador):
    """A herança apaga a distinção em `e_professor`. Onde a regra for mesmo "é
    professor e NÃO é coordenador", existe esta propriedade -- para que ninguém
    reescreva `papel == PROFESSOR` espalhado pelo código."""
    assert professor.e_somente_professor is True
    assert coordenador.e_somente_professor is False


@pytest.mark.django_db
def test_papel_continua_sendo_um_so_valor(coordenador):
    """A herança é de comportamento, não de armazenamento: `papel` segue com um
    valor por pessoa, e o coordenador é COORDENADOR no banco."""
    assert coordenador.papel == Usuario.COORDENADOR
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/contas/tests/test_papeis.py -v`
Expected: FAIL — `assert False is True` em `test_coordenador_tambem_e_professor`, e `AttributeError: 'Usuario' object has no attribute 'e_somente_professor'`.

- [ ] **Step 3: Implementar a herança**

Em `apps/contas/models.py`, substitua as três propriedades:

```python
    @property
    def e_coordenador(self):
        """Nível de acesso Admin: publica curso, organiza turmas e promove
        professores. Ver `apps.cursos.permissions.pode_publicar`."""
        return self.papel == self.COORDENADOR

    @property
    def e_professor(self):
        """Verdadeiro também para o coordenador: todo coordenador é professor
        (regra 1 do Plano 5).

        A herança mora aqui, e não numa segunda coluna, para que exista um lugar
        só onde ela é definida. `papel` continua com um valor por pessoa; quem
        precisa da distinção usa `e_somente_professor`.

        Consequências pretendidas, todas por esta linha: o coordenador cria
        curso (`permissions.pode_criar_curso`), pode ser `professor_responsavel`
        (`Curso.clean`) e pode conduzir turma (`Turma.clean`). As permissões
        escritas como `e_coordenador or (e_professor and ...)` não mudam de
        comportamento -- o `or` já curto-circuitava para o coordenador.
        """
        return self.papel in (self.PROFESSOR, self.COORDENADOR)

    @property
    def e_somente_professor(self):
        """Professor que não é coordenador. Existe para que a distinção tenha um
        nome, em vez de reaparecer como `papel == PROFESSOR` solto pelo código."""
        return self.papel == self.PROFESSOR

    @property
    def e_aluno(self):
        return self.papel == self.ALUNO
```

- [ ] **Step 4: Abrir a porta da proposta e a da turma**

Em `apps/cursos/views/professor.py`, a guarda de `nova_proposta` (linhas 16-22) tem um comentário que a herança torna falso. Substitua o bloco inteiro:

```python
def nova_proposta(request):
    # Coordenador entra aqui a partir do Plano 5: ele é professor (regra 1) e a
    # view sempre cria com professor_responsavel=request.user, então ele fica
    # responsável pelo próprio curso -- não é preciso escolher outra pessoa.
    permissions.garante(
        permissions.pode_criar_curso(request.user), "Somente professor cria proposta de curso."
    )
```

Em `apps/turmas/forms.py`, o queryset do campo `professor` filtra `papel=Usuario.PROFESSOR` e deixaria o coordenador de fora da lista, contradizendo `Turma.clean`, que passa a aceitá-lo:

```python
    professor = forms.ModelChoiceField(
        # Coordenador entra na lista porque `Turma.clean` passou a aceitá-lo
        # (regra 1). Filtrar por papel aqui deixaria o formulário mais estrito
        # que o modelo, e a coordenação não conseguiria designar a si mesma.
        queryset=Usuario.objects.filter(
            papel__in=[Usuario.PROFESSOR, Usuario.COORDENADOR], is_active=True
        ),
        label="professor responsável",
    )
```

- [ ] **Step 5: Rodar a suíte inteira e relatar contradições**

Run: `pytest`

Alguns testes existentes afirmam o comportamento antigo. **Não os altere ainda.** Rode, anote cada falha e relate: o nome do teste, o que ele prende hoje, e por que a regra 1 o invalida. O plano prevê que estes falhem — o gate humano decide caso a caso:

- `apps/cursos/tests/` — qualquer teste de que coordenador **não** cria proposta.
- `apps/turmas/tests/test_turma.py` — `test_quem_nao_e_professor_nao_conduz_turma` usa `aluno`, então continua válido; um teste que use `coordenador` como não-professor, não.

- [ ] **Step 6: Provar a herança quebrando**

Apague `self.COORDENADOR` da tupla em `e_professor`, rode `pytest apps/contas/tests/test_papeis.py`, confirme que `test_coordenador_tambem_e_professor` falha sozinho, restaure. Faça o mesmo com `e_somente_professor`.

- [ ] **Step 7: Commitar**

```bash
git add apps/contas apps/cursos/views/professor.py apps/turmas/forms.py
git commit -m "feat(contas): coordenador herda o papel de professor"
```

---

### Task 2: Perfil incompleto é um estado de primeira classe

**Files:**
- Modify: `apps/contas/models.py`
- Create: `apps/contas/migrations/0002_telefone_e_cpf_opcional.py` (gerada)
- Test: `apps/contas/tests/test_perfil.py`

**Interfaces:**
- Consumes: `Usuario` (Task 1).
- Produces: campo `Usuario.telefone`; `Usuario.cpf` passa a `null=True, blank=True`; `Usuario.perfil_completo` (property, bool).

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/contas/tests/test_perfil.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.contas.models import Usuario


@pytest.mark.django_db
def test_aluno_nasce_sem_documento_e_com_perfil_incompleto():
    """Regra 2: o professor aloca informando só nome e e-mail. CPF, matrícula e
    telefone chegam no primeiro acesso."""
    aluno = Usuario.objects.create_user(
        email="novo@acad.ufsm.br", nome_completo="Novo Aluno",
        cpf=None, papel=Usuario.ALUNO, password=None,
    )
    assert aluno.cpf is None
    assert aluno.matricula is None
    assert aluno.perfil_completo is False


@pytest.mark.django_db
def test_perfil_fica_completo_com_os_tres_campos(aluno):
    assert aluno.perfil_completo is False
    aluno.cpf = "987.654.321-00"
    aluno.matricula = "201910101"
    aluno.telefone = "(55) 99999-1234"
    aluno.save()
    assert aluno.perfil_completo is True


@pytest.mark.django_db
@pytest.mark.parametrize("faltando", ["cpf", "matricula", "telefone"])
def test_falta_de_qualquer_um_deixa_o_perfil_incompleto(aluno, faltando):
    """Três testes, não um: apagar a checagem de um campo sozinho tem de derrubar
    exatamente a sua parametrização."""
    dados = {"cpf": "987.654.321-00", "matricula": "201910101", "telefone": "(55) 99999-1234"}
    dados[faltando] = "" if faltando == "telefone" else None
    for campo, valor in dados.items():
        setattr(aluno, campo, valor)
    assert aluno.perfil_completo is False


@pytest.mark.django_db
def test_professor_nasce_com_perfil_completo(professor):
    """Professor e coordenador são criados pela coordenação com documento na mão:
    nunca passam pelo primeiro acesso do aluno."""
    assert professor.perfil_completo is True


@pytest.mark.django_db
def test_dois_alunos_sem_cpf_convivem():
    """`cpf` continua único. Nulo não colide com nulo no Postgres, e é o que
    permite alocar dois alunos antes de qualquer um deles completar o perfil."""
    for i in (1, 2):
        Usuario.objects.create_user(
            email=f"aluno{i}@acad.ufsm.br", nome_completo=f"Aluno {i}",
            cpf=None, papel=Usuario.ALUNO, password=None,
        )
    assert Usuario.objects.filter(cpf__isnull=True).count() == 2


@pytest.mark.django_db
def test_cpf_repetido_continua_recusado(aluno):
    with pytest.raises(ValidationError):
        Usuario.objects.create_user(
            email="clone@acad.ufsm.br", nome_completo="Clone",
            cpf="987.654.321-00", papel=Usuario.ALUNO,
            matricula="202020202", password=None,
        )


@pytest.mark.django_db
def test_professor_sem_siape_continua_recusado():
    """A regra que sobrevive: aluno pode nascer sem documento, professor não."""
    with pytest.raises(ValidationError):
        Usuario.objects.create_user(
            email="semsiape@ufsm.br", nome_completo="Sem Siape",
            cpf="123.456.789-09", papel=Usuario.PROFESSOR, password=None,
        )
```

Antes de rodar, ajuste a fixture `aluno` em `apps/cursos/tests/conftest.py` para nascer **sem** os três campos, que é o estado que o Plano 5 cria:

```python
@pytest.fixture
def aluno(db):
    """Aluno recém-alocado: sem CPF, sem matrícula, sem telefone. É o estado em
    que o professor o cria a partir do Plano 5, e testes que precisem do perfil
    completo devem preenchê-lo explicitamente."""
    return Usuario.objects.create_user(
        email="aluno@ufsm.br", nome_completo="Ana Alves",
        cpf=None, papel=Usuario.ALUNO, password="senha-de-teste-123",
    )
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/contas/tests/test_perfil.py -v`
Expected: FAIL — `AttributeError: 'Usuario' object has no attribute 'telefone'`.

- [ ] **Step 3: Implementar os campos e a regra**

Em `apps/contas/models.py`, no corpo do modelo:

```python
    cpf = models.CharField(
        "CPF", max_length=11, unique=True, null=True, blank=True, validators=[valida_cpf]
    )
    telefone = models.CharField("telefone", max_length=20, blank=True)
```

E a propriedade, junto das outras:

```python
    @property
    def perfil_completo(self):
        """Tem tudo o que o sistema precisa da pessoa.

        Derivado dos campos, e não de uma coluna `perfil_completo` à parte: uma
        flag paralela é uma segunda fonte de verdade que sai de sincronia na
        primeira edição pelo Admin. Aqui não há o que sincronizar.

        Professor e coordenador nascem completos -- são criados pela coordenação
        com documento na mão -- então o primeiro acesso do Plano 5 só alcança
        aluno, sem precisar de um `if papel` para dizer isso.
        """
        return bool(self.cpf and self.matricula and self.telefone)
```

E em `clean()`, a exigência de matrícula do aluno passa a valer só quando já há CPF — isto é, quando o perfil está sendo completado, e não quando o aluno acaba de ser alocado:

```python
        if self.e_aluno:
            # Aluno recém-alocado não tem documento nenhum (regra 2): quem exige
            # os três campos é a tela de primeiro acesso, via ConviteForm, e não
            # o modelo -- senão a própria alocação seria impossível. O que o
            # modelo continua garantindo é a coerência: com CPF, tem de haver
            # matrícula; e aluno nunca tem SIAPE.
            if self.cpf and not self.matricula:
                erros["matricula"] = "Informe a matrícula junto com o CPF."
            if self.siape:
                erros["siape"] = "Aluno não tem SIAPE."
        else:
            if not self.cpf:
                erros["cpf"] = "CPF é obrigatório para professor e coordenador."
            if not self.siape:
                erros["siape"] = "SIAPE é obrigatório para professor e coordenador."
            if self.matricula:
                erros["matricula"] = "Professor e coordenador não têm matrícula."
```

Em `full_clean()`, a normalização precisa aceitar `None`:

```python
    def full_clean(self, *args, **kwargs):
        # Normaliza antes de qualquer validação: sem isso a unicidade não vale
        # nada, porque 529.982.247-25 e 52998224725 conviveriam no banco
        # (spec 4.1). `or None` nos três: CPF passou a ser opcional no Plano 5, e
        # string vazia colidiria com string vazia no índice único.
        self.cpf = somente_digitos(self.cpf) or None
        self.matricula = somente_digitos(self.matricula) or None
        self.siape = somente_digitos(self.siape) or None
        super().full_clean(*args, **kwargs)
```

E o manager, que hoje exige `cpf` posicionalmente:

```python
    def create_user(self, email, nome_completo, papel, cpf=None, password=None, **extra):
```

- [ ] **Step 4: Migrar e rodar**

```bash
python manage.py makemigrations contas --name telefone_e_cpf_opcional
pytest apps/contas -v
```

Confira que a migração é `AddField` mais `AlterField` — **nenhuma perda de dado**. Se aparecer `RemoveField`, pare e relate.

- [ ] **Step 5: Provar quebrando, uma guarda por vez**

Para cada uma, apague sozinha, rode, confirme que cai só o teste que a nomeia, restaure:
1. `self.cpf` em `perfil_completo` → cai a parametrização `cpf`.
2. `self.matricula` → cai a parametrização `matricula`.
3. `self.telefone` → cai a parametrização `telefone`.
4. `if not self.cpf` no ramo do professor → cai `test_professor_sem_siape_continua_recusado`? **Não deve.** Se cair, o teste está confundido: ele viola duas regras ao mesmo tempo. Nesse caso, dê ao usuário do teste um CPF e relate a correção.

- [ ] **Step 6: Rodar a suíte inteira**

Run: `pytest`

A fixture `aluno` mudou, então testes que dependiam de o aluno ter matrícula podem falhar. **Relate cada um antes de tocar.**

- [ ] **Step 7: Commitar**

```bash
git add apps/contas apps/cursos/tests/conftest.py
git commit -m "feat(contas): perfil incompleto como estado de primeira classe"
```

---

### Task 3: Convite de primeiro acesso

**Files:**
- Create: `apps/contas/models_convite.py`, `apps/contas/services.py`
- Modify: `apps/contas/models.py` (reexportar), `apps/contas/admin.py`
- Test: `apps/contas/tests/test_convite.py`

**Interfaces:**
- Consumes: `Usuario` (Tasks 1-2), `notificacoes.services.enfileirar` (Plano 3).
- Produces: `apps.contas.models.ConviteAluno` (`usuario`, `token`, `criado_por`, `criado_em`, `expira_em`, `usado_em`); `ConviteAluno.PRAZO` (`timedelta(days=7)`); `ConviteAluno.valido` (property); `apps.contas.services.convidar(usuario, por) -> ConviteAluno`; `apps.contas.services.consumir_convite(token, senha, cpf, matricula, telefone) -> Usuario`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/contas/tests/test_convite.py`:

```python
import datetime

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.contas import services
from apps.contas.models import ConviteAluno, Usuario
from apps.notificacoes.models import Notificacao


@pytest.fixture
def recem_alocado(db):
    return Usuario.objects.create_user(
        email="novo@acad.ufsm.br", nome_completo="Novo Aluno",
        cpf=None, papel=Usuario.ALUNO, password=None,
    )


@pytest.mark.django_db
def test_convite_dura_sete_dias(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    esperado = timezone.now() + datetime.timedelta(days=7)
    assert abs((convite.expira_em - esperado).total_seconds()) < 60
    assert convite.valido is True


@pytest.mark.django_db
def test_convite_avisa_o_aluno_por_e_mail(recem_alocado, professor):
    services.convidar(recem_alocado, por=professor)
    fila = Notificacao.objects.filter(evento="CONVITE_ALUNO", destinatario=recem_alocado.email)
    assert fila.count() == 1


@pytest.mark.django_db
def test_o_e_mail_nao_leva_senha(recem_alocado, professor):
    """Token de uso único, e não senha temporária: a fila de notificações fica
    gravada no banco, e senha em texto no corpo do e-mail sobreviveria ali."""
    convite = services.convidar(recem_alocado, por=professor)
    corpo = Notificacao.objects.get(evento="CONVITE_ALUNO").corpo
    assert str(convite.token) in corpo
    assert "senha" not in corpo.lower() or "criar sua senha" in corpo.lower()


@pytest.mark.django_db
def test_consumir_completa_o_perfil_e_define_a_senha(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    aluno = services.consumir_convite(
        convite.token, senha="uma-senha-de-verdade-123",
        cpf="987.654.321-00", matricula="201910101", telefone="(55) 99999-1234",
    )
    aluno.refresh_from_db()
    assert aluno.perfil_completo is True
    assert aluno.check_password("uma-senha-de-verdade-123")


@pytest.mark.django_db
def test_convite_e_de_uso_unico(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    services.consumir_convite(
        convite.token, senha="uma-senha-de-verdade-123",
        cpf="987.654.321-00", matricula="201910101", telefone="(55) 99999-1234",
    )
    with pytest.raises(ValidationError):
        services.consumir_convite(
            convite.token, senha="outra-senha-qualquer-456",
            cpf="987.654.321-00", matricula="201910101", telefone="(55) 99999-1234",
        )


@pytest.mark.django_db
def test_convite_vencido_e_recusado(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    ConviteAluno.objects.filter(pk=convite.pk).update(
        expira_em=timezone.now() - datetime.timedelta(minutes=1)
    )
    with pytest.raises(ValidationError):
        services.consumir_convite(
            convite.token, senha="uma-senha-de-verdade-123",
            cpf="987.654.321-00", matricula="201910101", telefone="(55) 99999-1234",
        )


@pytest.mark.django_db
def test_token_inexistente_e_recusado(db):
    import uuid

    with pytest.raises(ValidationError):
        services.consumir_convite(
            uuid.uuid4(), senha="uma-senha-de-verdade-123",
            cpf="987.654.321-00", matricula="201910101", telefone="(55) 99999-1234",
        )


@pytest.mark.django_db
def test_reenviar_invalida_o_convite_anterior(recem_alocado, professor):
    """Regra 3: o professor reenvia. O convite antigo tem de morrer no reenvio --
    dois links válidos ao mesmo tempo dobram a janela de exposição do token."""
    primeiro = services.convidar(recem_alocado, por=professor)
    segundo = services.convidar(recem_alocado, por=professor)
    primeiro.refresh_from_db()
    assert primeiro.valido is False
    assert segundo.valido is True


@pytest.mark.django_db
def test_consumir_recusa_cpf_invalido(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    with pytest.raises(ValidationError):
        services.consumir_convite(
            convite.token, senha="uma-senha-de-verdade-123",
            cpf="111.111.111-11", matricula="201910101", telefone="(55) 99999-1234",
        )
    recem_alocado.refresh_from_db()
    assert recem_alocado.perfil_completo is False


@pytest.mark.django_db
def test_consumir_e_atomico_quando_a_senha_e_fraca(recem_alocado, professor):
    """Falha depois de a senha ter sido definida em memória: nada pode ficar
    gravado pela metade, nem o convite pode contar como usado."""
    convite = services.convidar(recem_alocado, por=professor)
    with pytest.raises(ValidationError):
        services.consumir_convite(
            convite.token, senha="123",
            cpf="987.654.321-00", matricula="201910101", telefone="(55) 99999-1234",
        )
    convite.refresh_from_db()
    recem_alocado.refresh_from_db()
    assert convite.usado_em is None
    assert recem_alocado.perfil_completo is False
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/contas/tests/test_convite.py -v`
Expected: FAIL — `ImportError: cannot import name 'ConviteAluno'`.

- [ ] **Step 3: Implementar o modelo**

`apps/contas/models_convite.py`:

```python
import datetime
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConviteAluno(models.Model):
    """Convite de primeiro acesso, com prazo e uso único.

    Modelo próprio, e não o `PasswordResetTokenGenerator` do Django: aquele
    gerador tira o prazo de `PASSWORD_RESET_TIMEOUT`, que é global e vale também
    para o "esqueci minha senha". Um convite de sete dias e um reset de três
    horas são coisas diferentes, e amarrá-las na mesma chave faria uma mudança de
    política mexer na outra sem aviso. Aqui o prazo é por registro, e o convite
    fica auditável: quem convidou, quando, e se já foi usado.
    """

    PRAZO = datetime.timedelta(days=7)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="convites"
    )
    token = models.UUIDField("token", default=uuid.uuid4, unique=True, editable=False)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="convites_enviados",
        verbose_name="convidado por",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    expira_em = models.DateTimeField("expira em")
    usado_em = models.DateTimeField("usado em", null=True, blank=True)
    cancelado_em = models.DateTimeField("cancelado em", null=True, blank=True)

    class Meta:
        verbose_name = "convite de aluno"
        verbose_name_plural = "convites de aluno"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["token"])]

    def __str__(self):
        return f"Convite de {self.usuario.nome_completo}"

    @property
    def valido(self):
        return (
            self.usado_em is None
            and self.cancelado_em is None
            and self.expira_em > timezone.now()
        )

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            if not self.expira_em:
                self.expira_em = timezone.now() + self.PRAZO
            self.full_clean()
        super().save(*args, **kwargs)
```

Em `apps/contas/models.py`, ao final, reexporte para que o resto do sistema importe de um lugar só:

```python
from apps.contas.models_convite import ConviteAluno  # noqa: E402,F401
```

- [ ] **Step 4: Implementar os serviços**

`apps/contas/services.py`:

```python
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.contas.models import ConviteAluno
from apps.notificacoes.services import enfileirar

CORPO_CONVITE = """Olá, {nome}.

{quem} incluiu você na equipe de produção de um curso de extensão do IntegraSI,
o sistema do curso de Sistemas de Informação da UFSM em Frederico Westphalen.

Para entrar pela primeira vez, abra o endereço abaixo e complete seu cadastro:
criar sua senha, informar CPF, matrícula e telefone.

{url}

O link vale por 7 dias e só pode ser usado uma vez. Se ele vencer, peça a
{quem} para enviar outro.
"""


@transaction.atomic
def convidar(usuario, por, base_url=""):
    """Cria o convite de primeiro acesso e enfileira o e-mail.

    Invalida os convites anteriores da mesma pessoa: dois links válidos ao mesmo
    tempo dobram a janela em que um token vazado ainda serve.
    """
    ConviteAluno.objects.filter(usuario=usuario, usado_em__isnull=True).update(
        cancelado_em=timezone.now()
    )
    convite = ConviteAluno.objects.create(
        usuario=usuario, criado_por=por, expira_em=timezone.now() + ConviteAluno.PRAZO
    )
    enfileirar(
        evento="CONVITE_ALUNO",
        destinatarios=[usuario.email],
        assunto="Seu acesso ao IntegraSI",
        corpo=CORPO_CONVITE.format(
            nome=usuario.nome_completo,
            quem=por.nome_completo,
            url=f"{base_url}/convite/{convite.token}/",
        ),
    )
    return convite


@transaction.atomic
def consumir_convite(token, senha, cpf, matricula, telefone):
    """Completa o perfil e define a senha, gastando o convite.

    Tudo numa transação: uma senha recusada pelo validador do Django não pode
    deixar o convite marcado como usado, senão a pessoa fica sem link e sem
    conta utilizável.
    """
    convite = ConviteAluno.objects.select_for_update().filter(token=token).first()
    if convite is None or not convite.valido:
        raise ValidationError("Este convite não vale mais. Peça outro ao professor.")

    usuario = convite.usuario
    validate_password(senha, usuario)

    usuario.cpf = cpf
    usuario.matricula = matricula
    usuario.telefone = telefone
    usuario.set_password(senha)
    usuario.save()

    convite.usado_em = timezone.now()
    convite.save(update_fields=["usado_em"])
    return usuario
```

- [ ] **Step 5: Registrar no Admin**

Em `apps/contas/admin.py`:

```python
from apps.contas.models import ConviteAluno, Usuario


@admin.register(ConviteAluno)
class ConviteAlunoAdmin(admin.ModelAdmin):
    """Somente leitura: o convite nasce por `services.convidar` e morre por
    `consumir_convite`. Editar prazo ou marcar como usado pela mão contornaria as
    duas regras que o convite existe para ter."""

    list_display = ["usuario", "criado_por", "criado_em", "expira_em", "usado_em"]
    list_filter = ["usado_em"]
    search_fields = ["usuario__nome_completo", "usuario__email"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
```

- [ ] **Step 6: Migrar, rodar e provar quebrando**

```bash
python manage.py makemigrations contas --name convite_aluno
pytest apps/contas -v
```

Apague uma de cada vez e confirme que cai exatamente o teste que a nomeia: a checagem `usado_em is None` em `valido`; a `cancelado_em is None`; a `expira_em > timezone.now()`; o `update(cancelado_em=...)` em `convidar`; o `validate_password`; o `@transaction.atomic` de `consumir_convite`.

Para o `@transaction.atomic`: o teste que o prende é `test_consumir_e_atomico_quando_a_senha_e_fraca`. Confirme que ele falha sem o decorador — se não falhar, a falha está acontecendo antes de qualquer escrita, e o teste não prova atomicidade nenhuma. Nesse caso, mova a validação da senha para depois do `save()` do usuário e relate a mudança.

- [ ] **Step 7: Commitar**

```bash
git add apps/contas
git commit -m "feat(contas): convite de primeiro acesso com prazo e uso unico"
```

---

### Task 4: Professor aloca aluno por nome e e-mail

**Files:**
- Modify: `apps/cursos/services.py`, `apps/cursos/views/professor.py:44-65`, `templates/cursos/equipe.html`
- Test: `apps/cursos/tests/test_alocacao.py`

**Interfaces:**
- Consumes: `contas.services.convidar` (Task 3), `permissions.pode_gerir_equipe` (Plano 2).
- Produces: `apps.cursos.services.alocar_aluno(curso, nome, email, por, base_url="") -> MembroEquipe`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_alocacao.py`:

```python
import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.contas.models import ConviteAluno, Usuario
from apps.cursos import services
from apps.notificacoes.models import Notificacao


@pytest.mark.django_db
def test_alocar_cria_a_conta_com_nome_e_email(curso, professor):
    """Regra 2: a alocação informa só nome e e-mail."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor
    )
    assert membro.aluno.nome_completo == "Joana Silva"
    assert membro.aluno.papel == Usuario.ALUNO
    assert membro.aluno.cpf is None
    assert membro.aluno.perfil_completo is False


@pytest.mark.django_db
def test_alocar_convida_o_aluno(curso, professor):
    services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor)
    assert ConviteAluno.objects.filter(usuario__email="joana@acad.ufsm.br").count() == 1
    assert Notificacao.objects.filter(
        evento="CONVITE_ALUNO", destinatario="joana@acad.ufsm.br"
    ).count() == 1


@pytest.mark.django_db
def test_a_conta_nasce_sem_senha_utilizavel(curso, professor):
    """Só o convite dá acesso: uma senha vazia que autenticasse seria uma porta
    aberta para toda conta ainda não usada."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor
    )
    assert membro.aluno.has_usable_password() is False


@pytest.mark.django_db
def test_email_ja_cadastrado_e_recusado(curso, professor, aluno):
    """Decisão do coordenador: o sistema recusa em vez de vincular a conta que já
    existe. Vincular em silêncio poria alguém numa equipe por causa de um e-mail
    digitado errado."""
    with pytest.raises(ValidationError):
        services.alocar_aluno(
            curso, nome="Outro Nome", email=aluno.email, por=professor
        )


@pytest.mark.django_db
def test_email_recusado_nao_deixa_conta_nem_convite(curso, professor, aluno):
    antes_usuarios = Usuario.objects.count()
    with pytest.raises(ValidationError):
        services.alocar_aluno(curso, nome="Outro Nome", email=aluno.email, por=professor)
    assert Usuario.objects.count() == antes_usuarios
    assert ConviteAluno.objects.count() == 0


@pytest.mark.django_db
def test_qualquer_dominio_de_email_e_aceito(curso, professor):
    """Decisão do coordenador: sem restrição de domínio -- há aluno de intercâmbio
    e conta pessoal, e uma lista branca deixaria o professor travado."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@gmail.com", por=professor
    )
    assert membro.aluno.email == "joana@gmail.com"


@pytest.mark.django_db
def test_alocar_tira_o_curso_do_rascunho(curso, professor):
    from apps.cursos.choices import StatusCurso

    assert curso.status == StatusCurso.RASCUNHO
    services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO


@pytest.mark.django_db
def test_aluno_nao_aloca(curso, aluno):
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=aluno)


@pytest.mark.django_db
def test_professor_de_outro_curso_nao_aloca(curso, outro_professor):
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(
            curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=outro_professor
        )


@pytest.mark.django_db
def test_alocacao_e_atomica_quando_o_convite_falha(curso, professor, monkeypatch):
    """A conta, o vínculo e o convite nascem juntos ou não nascem. Sem isso, um
    erro no envio deixaria uma conta órfã que ninguém consegue ativar e que
    bloqueia o e-mail para sempre, porque a segunda tentativa bate na regra de
    e-mail já cadastrado."""
    from apps.cursos import services as servicos

    def explode(*args, **kwargs):
        raise RuntimeError("fila fora do ar")

    monkeypatch.setattr(servicos, "convidar", explode)
    with pytest.raises(RuntimeError):
        services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor)
    assert Usuario.objects.filter(email="joana@acad.ufsm.br").exists() is False
    assert curso.membros.count() == 0
```

Acrescente a fixture que falta em `apps/cursos/tests/conftest.py`:

```python
@pytest.fixture
def outro_professor(db):
    return Usuario.objects.create_user(
        email="outro.prof@ufsm.br", nome_completo="Elisa Esteves",
        cpf="111.444.777-35", papel=Usuario.PROFESSOR, siape="9999999",
        password="senha-de-teste-123",
    )
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_alocacao.py -v`
Expected: FAIL — `AttributeError: module 'apps.cursos.services' has no attribute 'alocar_aluno'`.

- [ ] **Step 3: Implementar o serviço**

Ao fim de `apps/cursos/services.py`:

```python
@transaction.atomic
def alocar_aluno(curso, nome, email, por, base_url=""):
    """Cria a conta do aluno, vincula à equipe e envia o convite (regras 2 e 3).

    Os três acontecem juntos: uma conta criada sem convite fica inalcançável --
    ninguém consegue ativá-la, e o e-mail fica queimado, porque a segunda
    tentativa bate na recusa de e-mail já cadastrado.
    """
    # Importes adiados, e nao no topo: `contas.services` nao pode ser importado
    # na carga deste modulo sem fechar um ciclo, e o arquivo ja usa esse padrao
    # para `Usuario` (ver `definir_temas`). A dependencia e de mao unica --
    # cursos conhece contas, contas nao conhece cursos (CLAUDE.md, Arquitetura).
    from apps.contas.models import Usuario
    from apps.contas.services import convidar

    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    email = (email or "").strip().lower()
    if Usuario.objects.filter(email__iexact=email).exists():
        raise ValidationError(
            "Já existe conta com este e-mail. Confira o endereço ou peça à "
            "coordenação para vincular a conta existente."
        )
    aluno = Usuario.objects.create_user(
        email=email, nome_completo=(nome or "").strip(), papel=Usuario.ALUNO, password=None
    )
    # Sem senha utilizável: só o convite abre a conta.
    aluno.set_unusable_password()
    aluno.save(update_fields=["password"])

    membro = adicionar_membro(curso, aluno, por=por)
    convidar(aluno, por=por, base_url=base_url)
    return membro
```

Note que o teste `test_alocacao_e_atomica_quando_o_convite_falha` faz
`monkeypatch.setattr(servicos, "convidar", explode)`. Com o import adiado, o nome
`convidar` não existe no módulo `apps.cursos.services`, e o `monkeypatch` falharia
com `AttributeError`. **Ajuste o teste** para adiar o patch na origem:

```python
    monkeypatch.setattr("apps.contas.services.convidar", explode)
```

É a forma correta de qualquer maneira: patcha onde a função mora, e não onde ela
foi importada.

- [ ] **Step 4: Trocar a tela**

Em `apps/cursos/views/professor.py`, a view `equipe` deixa de escolher num `select` de contas existentes:

```python
@login_required
@require_http_methods(["GET", "POST"])
def equipe(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(permissions.pode_gerir_equipe(request.user, curso), "Curso de outro professor.")
    if request.method == "POST":
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
                f"{membro.aluno.nome_completo} entrou na equipe. "
                "Enviamos o convite de primeiro acesso por e-mail.",
            )
        return redirect("equipe", pk=curso.pk)
    return render(request, "cursos/equipe.html", {"curso": curso})
```

Em `templates/cursos/equipe.html`, troque o bloco do `<aside>` inteiro:

```html
    <aside class="lateral">
      <h2>Alocar estudante</h2>
      <p>Informe nome e e-mail. A pessoa recebe um convite para criar a senha e
         completar o cadastro.</p>
      <form method="post">
        {% csrf_token %}
        <div class="campo">
          <label for="id_nome">Nome</label>
          <input type="text" name="nome" id="id_nome" required>
        </div>
        <div class="campo">
          <label for="id_email">E-mail</label>
          <input type="email" name="email" id="id_email" required>
        </div>
        <button type="submit" class="botao-largo">Alocar e convidar</button>
      </form>
    </aside>
```

- [ ] **Step 5: Rodar tudo e provar quebrando**

Run: `pytest`

Apague uma de cada vez: a checagem de e-mail existente; o `set_unusable_password()`; o `@transaction.atomic`; a chamada a `convidar`. Cada uma deve derrubar exatamente o seu teste.

Atenção ao `@transaction.atomic`: `test_alocacao_e_atomica_quando_o_convite_falha` só prova alguma coisa se a exceção vier **depois** de a conta ser criada. Confirme.

- [ ] **Step 6: Commitar**

```bash
git add apps/cursos templates/cursos/equipe.html
git commit -m "feat(cursos): professor aloca aluno por nome e e-mail"
```

---

### Task 5: Tela de primeiro acesso e o portão do perfil incompleto

**Files:**
- Create: `apps/contas/forms_convite.py`, `templates/contas/primeiro_acesso.html`, `templates/contas/convite_invalido.html`, `apps/contas/middleware.py`
- Modify: `apps/contas/urls.py`, `apps/contas/views.py`, `config/settings.py`
- Test: `apps/contas/tests/test_primeiro_acesso.py`

**Interfaces:**
- Consumes: `contas.services.consumir_convite` (Task 3).
- Produces: rota `primeiro_acesso` (`convite/<uuid:token>/`); `apps.contas.middleware.PerfilCompletoMiddleware`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/contas/tests/test_primeiro_acesso.py`:

```python
import pytest
from django.urls import reverse

from apps.contas import services
from apps.contas.models import Usuario


@pytest.fixture
def convite(db, professor):
    aluno = Usuario.objects.create_user(
        email="novo@acad.ufsm.br", nome_completo="Novo Aluno",
        cpf=None, papel=Usuario.ALUNO, password=None,
    )
    aluno.set_unusable_password()
    aluno.save(update_fields=["password"])
    return services.convidar(aluno, por=professor)


def dados_validos():
    return {
        "senha": "uma-senha-de-verdade-123",
        "confirmacao": "uma-senha-de-verdade-123",
        "cpf": "987.654.321-00",
        "matricula": "201910101",
        "telefone": "(55) 99999-1234",
    }


@pytest.mark.django_db
def test_pagina_do_convite_abre_sem_login(client, convite):
    resposta = client.get(reverse("primeiro_acesso", args=[convite.token]))
    assert resposta.status_code == 200


@pytest.mark.django_db
def test_completar_o_perfil_e_entrar(client, convite):
    resposta = client.post(
        reverse("primeiro_acesso", args=[convite.token]), dados_validos(), follow=True
    )
    assert resposta.status_code == 200
    convite.usuario.refresh_from_db()
    assert convite.usuario.perfil_completo is True
    assert resposta.context["user"].is_authenticated


@pytest.mark.django_db
def test_senhas_diferentes_sao_recusadas(client, convite):
    dados = dados_validos()
    dados["confirmacao"] = "outra-coisa-completamente"
    client.post(reverse("primeiro_acesso", args=[convite.token]), dados)
    convite.usuario.refresh_from_db()
    assert convite.usuario.perfil_completo is False


@pytest.mark.django_db
def test_token_invalido_mostra_pagina_propria(client):
    import uuid

    resposta = client.get(reverse("primeiro_acesso", args=[uuid.uuid4()]))
    assert resposta.status_code == 200
    assert "convite" in resposta.content.decode().lower()


@pytest.mark.django_db
def test_metodo_errado_e_rejeitado(client, convite):
    resposta = client.delete(reverse("primeiro_acesso", args=[convite.token]))
    assert resposta.status_code == 405


@pytest.mark.django_db
def test_perfil_incompleto_so_alcanca_a_propria_tela(client, convite):
    """Decisão do coordenador: enquanto não completa, o aluno é levado de volta.
    Meio-estado -- produzir material sem CPF -- não existe."""
    aluno = convite.usuario
    client.force_login(aluno)
    resposta = client.get(reverse("meus_cursos"))
    assert resposta.status_code == 302
    assert str(convite.token) in resposta.url


@pytest.mark.django_db
def test_perfil_completo_circula_normalmente(client, aluno):
    aluno.cpf = "987.654.321-00"
    aluno.matricula = "201910101"
    aluno.telefone = "(55) 99999-1234"
    aluno.save()
    client.force_login(aluno)
    assert client.get(reverse("meus_cursos")).status_code == 200


@pytest.mark.django_db
def test_o_portao_nao_prende_o_logout(client, convite):
    """Sem esta exceção, quem entra com perfil incompleto não consegue nem sair."""
    client.force_login(convite.usuario)
    assert client.post(reverse("logout")).status_code in (200, 302)
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/contas/tests/test_primeiro_acesso.py -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'primeiro_acesso' not found`.

- [ ] **Step 3: Escrever o formulário**

`apps/contas/forms_convite.py`:

```python
from django import forms

from apps.contas.validators import valida_cpf


class PrimeiroAcessoForm(forms.Form):
    senha = forms.CharField(label="Crie sua senha", widget=forms.PasswordInput, strip=False)
    confirmacao = forms.CharField(
        label="Repita a senha", widget=forms.PasswordInput, strip=False
    )
    cpf = forms.CharField(label="CPF", max_length=14)
    matricula = forms.CharField(label="Matrícula", max_length=20)
    telefone = forms.CharField(label="Telefone", max_length=20)

    def clean_cpf(self):
        cpf = self.cleaned_data["cpf"]
        # Valida aqui além do modelo porque o modelo devolveria o erro no campo
        # errado depois do save(); aqui a pessoa vê no campo do CPF.
        valida_cpf("".join(c for c in cpf if c.isdigit()))
        return cpf

    def clean(self):
        dados = super().clean()
        if dados.get("senha") and dados.get("senha") != dados.get("confirmacao"):
            self.add_error("confirmacao", "As duas senhas precisam ser iguais.")
        return dados
```

- [ ] **Step 4: Escrever a view e a rota**

Em `apps/contas/views.py`:

```python
from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.contas import services
from apps.contas.forms_convite import PrimeiroAcessoForm
from apps.contas.models import ConviteAluno


@require_http_methods(["GET", "POST"])
def primeiro_acesso(request, token):
    """Aberta sem login de propósito: quem chega aqui ainda não tem senha."""
    convite = ConviteAluno.objects.filter(token=token).first()
    if convite is None or not convite.valido:
        return render(request, "contas/convite_invalido.html", status=200)

    form = PrimeiroAcessoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            usuario = services.consumir_convite(
                token,
                senha=form.cleaned_data["senha"],
                cpf=form.cleaned_data["cpf"],
                matricula=form.cleaned_data["matricula"],
                telefone=form.cleaned_data["telefone"],
            )
        except ValidationError as erro:
            for mensagem in erro.messages:
                form.add_error(None, mensagem)
        else:
            login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("painel")

    return render(request, "contas/primeiro_acesso.html", {"form": form, "convite": convite})
```

Em `apps/contas/urls.py`:

```python
    path("convite/<uuid:token>/", views.primeiro_acesso, name="primeiro_acesso"),
```

- [ ] **Step 5: Escrever os templates**

`templates/contas/primeiro_acesso.html`:

```html
{% extends "base.html" %}
{% block titulo %}Primeiro acesso &mdash; IntegraSI{% endblock %}

{% block conteudo %}
<div class="trabalho">
  <div class="faixa pagina-estreita">
    <h1>Bem-vindo ao IntegraSI</h1>
    <p class="abertura">Olá, {{ convite.usuario.nome_completo }}. Crie sua senha e
       complete seu cadastro para começar.</p>
    <div class="cartao">
      {% if form.non_field_errors %}
        <p class="erro-acesso">{{ form.non_field_errors|join:" " }}</p>
      {% endif %}
      <form method="post">
        {% csrf_token %}
        {{ form.as_p }}
        <button type="submit" class="botao-largo">Criar senha e entrar</button>
      </form>
    </div>
  </div>
</div>
{% endblock %}
```

`templates/contas/convite_invalido.html`:

```html
{% extends "base.html" %}
{% block titulo %}Convite vencido &mdash; IntegraSI{% endblock %}

{% block conteudo %}
<div class="trabalho">
  <div class="faixa pagina-estreita">
    <h1>Este convite não vale mais</h1>
    <p class="abertura">O link expira em sete dias e só pode ser usado uma vez.
       Peça ao professor responsável pelo curso para enviar outro.</p>
    <a class="botao" href="{% url 'catalogo' %}">Ir para o catálogo</a>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Escrever o portão**

`apps/contas/middleware.py`:

```python
from django.shortcuts import redirect
from django.urls import reverse


class PerfilCompletoMiddleware:
    """Quem entrou e ainda não completou o perfil só alcança a própria tela.

    Middleware, e não decorador em cada view: uma view nova nasceria desprotegida
    e ninguém perceberia. Aqui o padrão é fechado e as exceções são explícitas.
    """

    # Nomes de rota que continuam abertos: a própria tela de completar, sair, e
    # o catálogo público. Sem `logout` aqui, quem tem perfil incompleto não
    # consegue nem sair da conta.
    LIBERADAS = {"primeiro_acesso", "logout", "login", "catalogo", "catalogo_curso", "solicitar"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if (
            usuario is not None
            and usuario.is_authenticated
            and not usuario.perfil_completo
            and getattr(request.resolver_match, "url_name", None) not in self.LIBERADAS
            and not request.path.startswith("/admin/")
            and not request.path.startswith("/static/")
        ):
            convite = usuario.convites.filter(usado_em__isnull=True).first()
            if convite is not None:
                return redirect("primeiro_acesso", token=convite.token)
        return self.get_response(request)
```

Como `resolver_match` só existe depois da resolução da URL, o middleware precisa
agir em `process_view`. Substitua o `__call__` acima por:

```python
    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        usuario = getattr(request, "user", None)
        if usuario is None or not usuario.is_authenticated or usuario.perfil_completo:
            return None
        if request.resolver_match and request.resolver_match.url_name in self.LIBERADAS:
            return None
        if request.path.startswith("/admin/"):
            return None
        convite = usuario.convites.filter(usado_em__isnull=True, cancelado_em__isnull=True).first()
        if convite is None:
            return None
        return redirect("primeiro_acesso", token=convite.token)
```

Em `config/settings.py`, depois de `AuthenticationMiddleware`:

```python
    "apps.contas.middleware.PerfilCompletoMiddleware",
```

- [ ] **Step 7: Rodar tudo e provar quebrando**

Run: `pytest`

Apague uma de cada vez: `"logout"` do conjunto `LIBERADAS` (cai `test_o_portao_nao_prende_o_logout`); a checagem `usuario.perfil_completo` (cai `test_perfil_completo_circula_normalmente`); o `return redirect(...)` (cai `test_perfil_incompleto_so_alcanca_a_propria_tela`).

- [ ] **Step 8: Commitar**

```bash
git add apps/contas config/settings.py templates/contas
git commit -m "feat(contas): tela de primeiro acesso e portao de perfil incompleto"
```

---

### Task 6: Promover e rebaixar coordenador

**Files:**
- Modify: `apps/contas/services.py`, `apps/contas/urls.py`, `apps/contas/views.py`
- Create: `templates/contas/pessoas.html`
- Test: `apps/contas/tests/test_promocao.py`

**Interfaces:**
- Consumes: `Usuario.e_coordenador` (Task 1). **Não** importa `cursos.permissions`: fecharia o ciclo com o import de `alocar_aluno` da Task 4.
- Produces: `apps.contas.services.promover_a_coordenador(usuario, por)`, `apps.contas.services.rebaixar_a_professor(usuario, por)`; rota `pessoas` (`coordenacao/pessoas/`).

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/contas/tests/test_promocao.py`:

```python
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.contas import services
from apps.contas.models import Usuario


@pytest.mark.django_db
def test_coordenador_promove_professor(professor, coordenador):
    services.promover_a_coordenador(professor, por=coordenador)
    professor.refresh_from_db()
    assert professor.papel == Usuario.COORDENADOR
    assert professor.e_coordenador is True
    assert professor.e_professor is True


@pytest.mark.django_db
def test_coordenador_rebaixa_outro_coordenador(coordenador, outro_coordenador):
    services.rebaixar_a_professor(outro_coordenador, por=coordenador)
    outro_coordenador.refresh_from_db()
    assert outro_coordenador.papel == Usuario.PROFESSOR


@pytest.mark.django_db
def test_ninguem_rebaixa_a_si_mesmo(coordenador):
    """Decisão do coordenador. Também é a rede de segurança do sistema: o último
    coordenador rebaixando a si mesmo deixaria o IntegraSI sem quem publique
    curso, aceite solicitação ou promova alguém de volta."""
    with pytest.raises(ValidationError):
        services.rebaixar_a_professor(coordenador, por=coordenador)
    coordenador.refresh_from_db()
    assert coordenador.papel == Usuario.COORDENADOR


@pytest.mark.django_db
def test_professor_nao_promove(professor, outro_professor):
    with pytest.raises(PermissionDenied):
        services.promover_a_coordenador(outro_professor, por=professor)


@pytest.mark.django_db
def test_aluno_nao_vira_coordenador(aluno, coordenador):
    """Promoção é de professor para coordenador. Um aluno viraria coordenador sem
    SIAPE, e `Usuario.clean` recusaria -- mas a mensagem sairia sobre o SIAPE, e
    não sobre a regra."""
    with pytest.raises(ValidationError):
        services.promover_a_coordenador(aluno, por=coordenador)


@pytest.mark.django_db
def test_promocao_fica_no_admin_do_django(professor, coordenador):
    """A promoção passa por services, e não por edição direta do campo `papel`
    no Admin: é mudança de nível de acesso, e o Admin não tem como recusar o
    auto-rebaixamento."""
    services.promover_a_coordenador(professor, por=coordenador)
    professor.refresh_from_db()
    assert professor.is_staff is True


@pytest.mark.django_db
def test_tela_de_pessoas_e_so_da_coordenacao(client, professor):
    client.force_login(professor)
    assert client.get(reverse("pessoas")).status_code == 403


@pytest.mark.django_db
def test_coordenador_ve_a_tela_de_pessoas(client, coordenador, professor):
    client.force_login(coordenador)
    conteudo = client.get(reverse("pessoas")).content.decode()
    assert professor.nome_completo in conteudo


@pytest.mark.django_db
def test_promover_pela_tela(client, coordenador, professor):
    client.force_login(coordenador)
    client.post(reverse("pessoas"), {"usuario": professor.pk, "acao": "PROMOVER"}, follow=True)
    professor.refresh_from_db()
    assert professor.papel == Usuario.COORDENADOR


@pytest.mark.django_db
def test_metodo_errado_na_tela_de_pessoas(client, coordenador):
    client.force_login(coordenador)
    assert client.delete(reverse("pessoas")).status_code == 405
```

Acrescente a fixture em `apps/cursos/tests/conftest.py`:

```python
@pytest.fixture
def outro_coordenador(db):
    return Usuario.objects.create_user(
        email="coord2@ufsm.br", nome_completo="Rita Rocha",
        cpf="071.620.218-24", papel=Usuario.COORDENADOR,
        siape="8888888", password="senha-de-teste-123",
    )
```

O CPF acima é válido pelo dígito verificador e não colide com nenhum já usado nas
fixturas — conferido contra `valida_cpf` e contra o banco. Não o troque por um
número inventado: `Usuario.full_clean` reprova, e o teste falharia pela razão errada.

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/contas/tests/test_promocao.py -v`
Expected: FAIL — `AttributeError: module 'apps.contas.services' has no attribute 'promover_a_coordenador'`.

- [ ] **Step 3: Implementar os serviços**

Ao fim de `apps/contas/services.py`:

```python
from django.core.exceptions import PermissionDenied

from apps.contas.models import Usuario


def _garante_coordenacao(por, mensagem):
    """Checagem local, e não `cursos.permissions.pode_publicar`.

    Duas razões. A dependência é de mão única -- `cursos` conhece `contas`, e o
    contrário fecharia um ciclo com o import de `alocar_aluno`. E a regra é outra:
    `pode_publicar` responde "quem leva um curso ao catálogo"; aqui a pergunta é
    "quem administra pessoas". Coincidem hoje e podem divergir amanhã.
    """
    if not (por is not None and por.e_coordenador):
        raise PermissionDenied(mensagem)


@transaction.atomic
def promover_a_coordenador(usuario, por):
    """Dá nível de acesso Admin a um professor (regra 1)."""
    _garante_coordenacao(por, "Somente a coordenação promove.")
    if not usuario.e_somente_professor:
        raise ValidationError("Só professor vira coordenador.")
    usuario.papel = Usuario.COORDENADOR
    usuario.is_staff = True
    usuario.save(update_fields=["papel", "is_staff"])
    return usuario


@transaction.atomic
def rebaixar_a_professor(usuario, por):
    """Tira o nível Admin, deixando a pessoa como professor.

    Ninguém rebaixa a si mesmo: além da decisão registrada no Plano 5, é o que
    impede o último coordenador de deixar o sistema sem quem publique curso,
    aceite solicitação ou promova alguém de volta.
    """
    _garante_coordenacao(por, "Somente a coordenação rebaixa.")
    if usuario.pk == por.pk:
        raise ValidationError("Você não pode rebaixar a si mesmo.")
    if not usuario.e_coordenador:
        raise ValidationError("Esta pessoa não é coordenadora.")
    usuario.papel = Usuario.PROFESSOR
    usuario.is_staff = False
    usuario.save(update_fields=["papel", "is_staff"])
    return usuario
```

Note que `save(update_fields=[...])` pula o `full_clean()` pela guarda do modelo — aqui isso é o que se quer: os campos mudados são exatamente dois, e o objeto já era válido.

- [ ] **Step 4: Escrever a tela**

Em `apps/contas/views.py`:

```python
@login_required
@require_http_methods(["GET", "POST"])
def pessoas(request):
    # `contas` nao importa `cursos`: a checagem e a mesma de `_garante_coordenacao`,
    # escrita aqui para a view poder devolver 403 antes de tocar no servico.
    if not request.user.e_coordenador:
        raise PermissionDenied("Área da coordenação.")
    if request.method == "POST":
        alvo = get_object_or_404(Usuario, pk=request.POST.get("usuario"))
        acao = request.POST.get("acao")
        try:
            if acao == "PROMOVER":
                services.promover_a_coordenador(alvo, por=request.user)
                messages.success(request, f"{alvo.nome_completo} agora é coordenador.")
            elif acao == "REBAIXAR":
                services.rebaixar_a_professor(alvo, por=request.user)
                messages.success(request, f"{alvo.nome_completo} voltou a ser professor.")
            else:
                messages.error(request, "Ação não reconhecida.")
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        return redirect("pessoas")

    equipe = Usuario.objects.filter(
        papel__in=[Usuario.PROFESSOR, Usuario.COORDENADOR]
    ).order_by("nome_completo")
    return render(request, "contas/pessoas.html", {"equipe": equipe})
```

Em `apps/contas/urls.py`:

```python
    path("coordenacao/pessoas/", views.pessoas, name="pessoas"),
```

`templates/contas/pessoas.html`:

```html
{% extends "base.html" %}
{% block titulo %}Pessoas &mdash; IntegraSI{% endblock %}

{% block conteudo %}
<div class="trabalho">
  <div class="cabecalho-pagina">
    <div class="faixa">
      <div>
        <h1>Professores e coordenação</h1>
        <p class="sub">Todo coordenador é também professor, com nível de acesso Admin.</p>
      </div>
    </div>
  </div>

  <div class="faixa corpo-trabalho">
    <ul class="registros">
      {% for pessoa in equipe %}
        <li class="registro">
          <div>
            <h3>{{ pessoa.nome_completo }}</h3>
            <p class="detalhe"><span>{{ pessoa.email }}</span></p>
          </div>
          <form method="post">
            {% csrf_token %}
            <input type="hidden" name="usuario" value="{{ pessoa.pk }}">
            {% if pessoa.e_coordenador %}
              <span class="estado ok">Coordenador</span>
              {% if pessoa.pk != user.pk %}
                <button type="submit" name="acao" value="REBAIXAR" class="botao-linha">Rebaixar a professor</button>
              {% endif %}
            {% else %}
              <span class="estado">Professor</span>
              <button type="submit" name="acao" value="PROMOVER">Promover a coordenador</button>
            {% endif %}
          </form>
        </li>
      {% endfor %}
    </ul>
  </div>
</div>
{% endblock %}
```

Acrescente o atalho em `templates/painel.html`, dentro do `{% if user.e_coordenador %}`:

```html
        <li class="atalho">
          <h3><a href="{% url 'pessoas' %}">Pessoas</a></h3>
          <p>Professores e coordenação. Promova um professor a coordenador ou tire o acesso.</p>
        </li>
```

- [ ] **Step 5: Rodar tudo e provar quebrando**

Run: `pytest`

Apague uma de cada vez: a checagem `usuario.pk == por.pk` (cai `test_ninguem_rebaixa_a_si_mesmo`); o `pode_publicar` de `promover_a_coordenador` (cai `test_professor_nao_promove`); o `e_somente_professor` (cai `test_aluno_nao_vira_coordenador`).

Cuidado com o último: se `test_aluno_nao_vira_coordenador` continuar passando sem a guarda, é porque o `Usuario.clean` recusou por falta de SIAPE — duas regras recusando a mesma entrada. Nesse caso o teste não prende nada, e a correção é afirmar a **mensagem**, não só o tipo da exceção.

- [ ] **Step 6: Commitar**

```bash
git add apps/contas templates/contas templates/painel.html
git commit -m "feat(contas): promover e rebaixar coordenador pela tela"
```

---

### Task 7: Atualizar a spec, a CLAUDE.md e a documentação

**Files:**
- Modify: `docs/superpowers/specs/2026-08-25-integrasi-design.md` (§2 e §10), `CLAUDE.md`, `docs/onde-mora-a-validacao.md`, `docs/operacao.md`
- Test: `tests/test_documentacao.py` (criar)

**Interfaces:**
- Consumes: tudo o que as Tasks 1-6 construíram.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`tests/test_documentacao.py`:

```python
from pathlib import Path

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)
SPEC = RAIZ / "docs" / "superpowers" / "specs" / "2026-08-25-integrasi-design.md"


def test_a_spec_registra_que_coordenador_e_professor():
    """A spec é a autoridade do projeto (CLAUDE.md). Uma regra que vale no código
    e não vale na spec vira contradição silenciosa para quem ler depois."""
    texto = SPEC.read_text()
    assert "todo coordenador é também professor" in texto.lower()


def test_a_spec_registra_a_alocacao_por_nome_e_email():
    texto = SPEC.read_text().lower()
    assert "nome e e-mail" in texto
    assert "primeiro acesso" in texto


def test_a_spec_nao_afirma_mais_que_o_coordenador_cadastra_todos():
    """A frase antiga contradiz a regra 2 e precisa sair, não apenas ganhar uma
    ressalva em outro lugar."""
    texto = SPEC.read_text()
    assert "criadas pelo coordenador via Django Admin" not in texto


def test_claude_md_documenta_o_primeiro_acesso():
    texto = (RAIZ / "CLAUDE.md").read_text().lower()
    assert "primeiro acesso" in texto
    assert "convite" in texto
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest tests/test_documentacao.py -v`
Expected: FAIL — as quatro, porque a spec ainda tem o texto antigo.

- [ ] **Step 3: Atualizar a spec**

Em `docs/superpowers/specs/2026-08-25-integrasi-design.md`, §2, substitua a tabela de atores e o parágrafo seguinte:

```markdown
| Ator | Quem é | O que faz |
|---|---|---|
| Coordenador | Coordenador do curso de SI | Tudo o que um professor faz, mais: aprova e publica cursos, organiza turmas, recebe solicitações e promove professores a coordenador |
| Professor | Professor do curso de SI | Cria a proposta, aloca a equipe, aprova ou devolve entregáveis, submete ao coordenador, conduz turmas |
| Aluno | Aluno de SI, membro de uma equipe | Produz seções e anexos, envia entregáveis para revisão, corrige devolutivas |
| Visitante | Escola, professor da rede, grupo comunitário | Navega o catálogo público e solicita a realização de um curso |

**Todo coordenador é também professor**, com nível de acesso Admin por cima: ele
cria curso, é responsável por curso e conduz turma como qualquer professor. O
papel continua sendo um valor só por pessoa (`Usuario.papel`); a herança está em
`Usuario.e_professor`, e quem precisa da distinção usa `e_somente_professor`.

Contas de professor e de coordenador são criadas pela coordenação. **Contas de
aluno são criadas pelo professor ao alocá-lo numa equipe, informando apenas nome
e e-mail**; o aluno recebe um convite por e-mail e, no primeiro acesso, cria a
senha e completa o cadastro com CPF, matrícula e telefone. O convite vale sete
dias, serve uma vez só, e o professor pode reenviá-lo. Enquanto o cadastro não
estiver completo, o aluno só alcança a tela de primeiro acesso. O visitante não
tem conta e nunca precisa de uma.
```

Em §10, acrescente ao final da seção:

```markdown
**Promoção e rebaixamento.** Só a coordenação promove um professor a coordenador
ou tira esse acesso, pela tela `coordenacao/pessoas/`. Ninguém rebaixa a si
mesmo: é a regra que impede o último coordenador de deixar o sistema sem quem
publique curso, aceite solicitação ou promova alguém de volta.

**O convite de primeiro acesso** carrega um token de uso único com prazo, e nunca
uma senha. A fila de notificações fica gravada no banco: uma senha em texto no
corpo do e-mail sobreviveria ali, legível por quem tem acesso ao Admin.
```

- [ ] **Step 4: Atualizar a CLAUDE.md**

Acrescente uma seção, depois de "Arquitetura":

```markdown
## Papéis e primeiro acesso (Plano 5)

- `papel` é um valor só por pessoa. A herança está em `Usuario.e_professor`, que
  vale para coordenador; `e_somente_professor` é para quem precisa da distinção.
  **Não reescreva `papel == PROFESSOR` solto pelo código.**
- Aluno é criado pelo professor com nome e e-mail, sem CPF e sem matrícula.
  `Usuario.perfil_completo` é derivado dos campos — não existe flag paralela, e
  não crie uma.
- O convite (`ConviteAluno`) vale 7 dias, serve uma vez e leva token, **nunca
  senha**: a fila de notificações persiste no banco.
- `PerfilCompletoMiddleware` prende quem não completou o cadastro na própria
  tela. As exceções são explícitas em `LIBERADAS`; `logout` está entre elas de
  propósito, senão a pessoa não consegue nem sair.
- Promoção e rebaixamento passam por `contas.services`, nunca por edição do campo
  `papel` no Admin: o Admin não tem como recusar o auto-rebaixamento.
```

- [ ] **Step 5: Atualizar os outros documentos**

Em `docs/onde-mora-a-validacao.md`, acrescente à tabela de casos:

```markdown
| Perfil de aluno incompleto | Middleware | `PerfilCompletoMiddleware`. Não é validação de modelo: o objeto é válido, o que falta é o cadastro estar terminado. Modelo recusando salvaria a alocação inteira. |
| Senha do primeiro acesso | `validate_password` no serviço | Os validadores do Django, dentro de `consumir_convite`, na mesma transação que grava o perfil. |
```

Em `docs/operacao.md`, na seção "Quando algo dá errado":

```markdown
- **Aluno não recebeu o convite:** confira a fila em `/admin/notificacoes/` pelo
  evento `CONVITE_ALUNO`. Se `ultimo_erro` estiver preenchido, é SMTP. O
  professor reenvia pela tela da equipe — o convite antigo é cancelado no ato.
- **Convite vencido:** sete dias. O professor reenvia; não há como estender o
  prazo de um convite existente, de propósito.
```

- [ ] **Step 6: Rodar tudo**

Run: `pytest`
Expected: PASS, com o total acima de 697 e **0 skips**.

- [ ] **Step 7: Commitar**

```bash
git add docs CLAUDE.md tests/test_documentacao.py
git commit -m "docs: papeis, alocacao e primeiro acesso na spec e na CLAUDE.md"
```

---

## Entregue ao fim deste plano

- Coordenador é professor com nível Admin, e a herança tem um lugar só onde é definida.
- Professor aloca aluno com nome e e-mail; a conta nasce sem senha utilizável e sem documento.
- Convite de sete dias, uso único, reenviável, sem senha no corpo do e-mail.
- Primeiro acesso completa CPF, matrícula e telefone e define a senha, em transação.
- Quem não completou o cadastro só alcança a própria tela.
- Coordenação promove e rebaixa pela tela, e ninguém rebaixa a si mesmo.
- Spec, `CLAUDE.md`, `onde-mora-a-validacao.md` e `operacao.md` atualizados — e um teste que reprova se a spec voltar a contradizer o código.

## O que este plano NÃO faz

- Não mexe em `Turma`/`Participante` além do queryset do formulário: frequência, nota e certificado continuam fora (spec §1.1).
- Não cria fluxo de "esqueci minha senha" — o convite é para primeiro acesso, não para recuperação.
- Não permite ao coordenador escolher outro professor como responsável ao criar curso: ele fica responsável pelo próprio. Tela nova, não conserto.
