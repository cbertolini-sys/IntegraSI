# IntegraSI - Plano 2: Produção de Cursos

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O professor cria a proposta de um curso, monta a equipe de alunos, e a equipe produz os cinco entregáveis obrigatórios dentro do sistema, com o professor aprovando ou devolvendo cada um.

**Architecture:** `apps/cursos` vira o núcleo do sistema. Toda transição de estado passa por `services.py`; toda checagem de acesso por `permissions.py`; as regras do roteiro da disciplina ficam em `validacoes.py`, que devolve a lista do que falta em vez de um sim/não. Modelos separados em módulos por responsabilidade dentro de `models/`.

**Tech Stack:** Django 5.x, PostgreSQL 16, pytest + pytest-django, HTMX, nh3 (sanitização de HTML).

**Spec:** `docs/superpowers/specs/2026-08-25-integrasi-design.md`

**Depende de:** Plano 1 (`docs/superpowers/plans/2026-08-25-integrasi-fundacao.md`) completo - `Usuario`, `Edicao`, `Referencial`, `Competencia`, `Tema`.

## Global Constraints

- Módulo de produção apenas. Nenhum campo de frequência, nota ou certificado (spec §1.1).
- Só `services.py` altera campo de status. Nenhum sinal `post_save` para lógica de domínio (spec §7.2).
- Toda transição roda em `transaction.atomic`: muda o estado e grava o histórico, ou nada acontece (spec §5).
- Cursos sem referencial são de primeira classe; nenhuma validação pode pressupor BNCC (spec §4.2).
- Público-alvo é obrigatório em todo curso (spec §4.3).
- Aluno edita apenas entregável em `RASCUNHO` ou `DEVOLVIDO`; devolver exige comentário não vazio (spec §5).
- Limites de upload: PDF 20 MB, imagem 10 MB, slides 50 MB. Tipo conferido pelo conteúdo do arquivo, não pela extensão (spec §8).
- Vídeo não é enviado neste plano: o `Anexo` de vídeo existe, o upload de 1 GB é o Plano 4.
- Textos de interface em português.

---

### Task 1: Enumerações e reorganização dos modelos

**Files:**
- Create: `apps/cursos/choices.py`, `apps/cursos/models/__init__.py`, `apps/cursos/models/tema.py`
- Delete: `apps/cursos/models.py` (vira pacote)
- Test: `apps/cursos/tests/test_choices.py`

**Interfaces:**
- Consumes: `Tema` (Plano 1, Task 9).
- Produces: `apps.cursos.choices` com `StatusCurso`, `StatusEntregavel`, `TipoEntregavel`, `TipoPublico`, `Formato`, `TipoMidia`, `Rotulo`, `TipoPratica`; `apps.cursos.models` como pacote que reexporta todos os modelos, de modo que `from apps.cursos.models import X` continue funcionando em qualquer tarefa.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_choices.py`:

```python
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel


def test_os_cinco_entregaveis_do_roteiro():
    assert [t.value for t in TipoEntregavel] == [
        "PLANO_ENSINO",
        "CARDS",
        "CADERNO",
        "VIDEOS",
        "SLIDES",
    ]


def test_estados_do_entregavel():
    assert set(StatusEntregavel.values) == {"RASCUNHO", "EM_REVISAO", "APROVADO", "DEVOLVIDO"}


def test_estados_do_curso_incluem_substituido():
    assert "SUBSTITUIDO" in StatusCurso.values


def test_tema_continua_importavel_do_pacote_de_modelos():
    from apps.cursos.models import Tema

    assert Tema._meta.model_name == "tema"
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_choices.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'apps.cursos.choices'`.

- [ ] **Step 3: Escrever as enumerações**

`apps/cursos/choices.py`:

```python
from django.db import models


class StatusCurso(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    EM_PRODUCAO = "EM_PRODUCAO", "Em producao"
    AGUARDANDO_COORDENADOR = "AGUARDANDO_COORDENADOR", "Aguardando coordenador"
    DEVOLVIDO = "DEVOLVIDO", "Devolvido pelo coordenador"
    PUBLICADO = "PUBLICADO", "Publicado"
    DESPUBLICADO = "DESPUBLICADO", "Despublicado"
    SUBSTITUIDO = "SUBSTITUIDO", "Substituido por nova versao"


class StatusEntregavel(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    EM_REVISAO = "EM_REVISAO", "Em revisao"
    APROVADO = "APROVADO", "Aprovado"
    DEVOLVIDO = "DEVOLVIDO", "Devolvido"


class TipoEntregavel(models.TextChoices):
    PLANO_ENSINO = "PLANO_ENSINO", "A - Plano de Ensino e Mapeamento Pedagogico"
    CARDS = "CARDS", "B - Infograficos e Cards Educativos"
    CADERNO = "CADERNO", "C - Caderno de Exercicios e Atividades Praticas"
    VIDEOS = "VIDEOS", "D - Video-Aulas"
    SLIDES = "SLIDES", "E - Slides e Apresentacoes"


class TipoPublico(models.TextChoices):
    ESCOLAR = "ESCOLAR", "Etapa escolar"
    COMUNITARIO = "COMUNITARIO", "Publico da comunidade"


class Formato(models.TextChoices):
    PRESENCIAL = "PRESENCIAL", "Presencial"
    HIBRIDO = "HIBRIDO", "Hibrido"
    ONLINE = "ONLINE", "Online"


class TipoMidia(models.TextChoices):
    ARQUIVO = "ARQUIVO", "Arquivo"
    VIDEO = "VIDEO", "Video"
    LINK = "LINK", "Link externo"


class Rotulo(models.TextChoices):
    NENHUM = "NENHUM", "Sem rotulo"
    SEM_GABARITO = "SEM_GABARITO", "Versao sem gabarito"
    COM_GABARITO = "COM_GABARITO", "Versao com gabarito"


class TipoPratica(models.TextChoices):
    NENHUM = "NENHUM", "Nao se aplica"
    PLUGADA = "PLUGADA", "Atividade plugada"
    DESPLUGADA = "DESPLUGADA", "Atividade desplugada"
    AMBAS = "AMBAS", "Plugada e desplugada"
```

- [ ] **Step 4: Transformar `models.py` em pacote**

```bash
mkdir -p apps/cursos/models
git mv apps/cursos/models.py apps/cursos/models/tema.py
```

`apps/cursos/models/__init__.py`:

```python
from apps.cursos.models.tema import Tema

__all__ = ["Tema"]
```

Ao mover o arquivo, acrescente a `Tema.save()` o mesmo guarda de `update_fields` que `contas`, `edicoes` e `referenciais` ja tem - `full_clean()` so quando a gravacao nao e dirigida. `Tema` ficou de fora daquela correcao no Plano 1, e os servicos deste plano gravam com `update_fields`:

```python
    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
```

- [ ] **Step 5: Rodar a suíte inteira e commitar**

```bash
pytest -v
git add apps/cursos
git commit -m "refactor(cursos): enumeracoes do dominio e models como pacote"
```

Expected: PASS - inclusive os testes de `Tema` do Plano 1, que continuam importando de `apps.cursos.models`.

---

### Task 2: Modelo Curso

**Files:**
- Create: `apps/cursos/models/curso.py`
- Modify: `apps/cursos/models/__init__.py`
- Test: `apps/cursos/tests/conftest.py`, `apps/cursos/tests/test_curso.py`

**Interfaces:**
- Consumes: `Usuario`, `Edicao`, `Referencial`, `Competencia`, `ETAPAS` (Plano 1); `choices` (Task 1).
- Produces: `apps.cursos.models.Curso` com `titulo`, `resumo`, `edicao`, `professor_responsavel`, `tipo_publico`, `etapa_ano`, `publico_descricao`, `referencial`, `competencias` (M2M), `carga_horaria`, `formato`, `pre_requisitos`, `temas` (M2M), `palavras_chave`, `status`, `criado_em`, `atualizado_em`, `publicado_em`; propriedade `publico_alvo` devolvendo o texto legível do público. Fixtures de teste `professor`, `aluno`, `coordenador`, `edicao`, `curso` em `apps/cursos/tests/conftest.py`, usadas por todas as tarefas seguintes.

- [ ] **Step 1: Escrever as fixtures compartilhadas**

`apps/cursos/tests/conftest.py`:

```python
import datetime

import pytest

from apps.contas.models import Usuario
from apps.cursos.choices import Formato, TipoPublico
from apps.cursos.models import Curso
from apps.edicoes.models import Edicao


@pytest.fixture
def coordenador(db):
    return Usuario.objects.create_user(
        email="coord@ufsm.br", nome_completo="Carla Costa",
        cpf="529.982.247-25", papel=Usuario.COORDENADOR, siape="7654321",
        password="senha-de-teste-123",
    )


@pytest.fixture
def professor(db):
    return Usuario.objects.create_user(
        email="prof@ufsm.br", nome_completo="Bruno Barros",
        cpf="123.456.789-09", papel=Usuario.PROFESSOR, siape="1234567",
        password="senha-de-teste-123",
    )


@pytest.fixture
def aluno(db):
    return Usuario.objects.create_user(
        email="aluno@ufsm.br", nome_completo="Ana Alves",
        cpf="987.654.321-00", papel=Usuario.ALUNO, matricula="201910101",
        password="senha-de-teste-123",
    )


@pytest.fixture
def outro_aluno(db):
    return Usuario.objects.create_user(
        email="outro@ufsm.br", nome_completo="Davi Dias",
        cpf="111.444.777-35", papel=Usuario.ALUNO, matricula="201910202",
        password="senha-de-teste-123",
    )


@pytest.fixture
def edicao(db):
    return Edicao.objects.create(
        codigo="2026/2", descricao="TICs para Inclusao Digital",
        data_inicio=datetime.date(2026, 8, 1), data_fim=datetime.date(2026, 12, 20),
        ativa=True,
    )


@pytest.fixture
def dados_curso(edicao, professor):
    return {
        "titulo": "Pensamento Computacional Desplugado",
        "resumo": "Oficina de logica sem telas para o 5o ano.",
        "edicao": edicao,
        "professor_responsavel": professor,
        "tipo_publico": TipoPublico.ESCOLAR,
        "etapa_ano": "EF05",
        "carga_horaria": 12,
        "formato": Formato.PRESENCIAL,
    }


@pytest.fixture
def curso(dados_curso):
    return Curso.objects.create(**dados_curso)
```

O CPF `111.444.777-35` é válido e é o quarto documento distinto de que os testes precisam.

- [ ] **Step 2: Escrever o teste do modelo (vai falhar)**

`apps/cursos/tests/test_curso.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.cursos.choices import StatusCurso, TipoPublico
from apps.cursos.models import Curso


@pytest.mark.django_db
def test_curso_nasce_em_rascunho(curso):
    assert curso.status == StatusCurso.RASCUNHO
    assert curso.publicado_em is None


@pytest.mark.django_db
def test_publico_escolar_exige_etapa(dados_curso):
    dados_curso["etapa_ano"] = ""
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)


@pytest.mark.django_db
def test_publico_escolar_nao_aceita_descricao_comunitaria(dados_curso):
    dados_curso["publico_descricao"] = "Professores da rede"
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)


@pytest.mark.django_db
def test_publico_comunitario_exige_descricao(dados_curso):
    dados_curso["tipo_publico"] = TipoPublico.COMUNITARIO
    dados_curso["etapa_ano"] = ""
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)


@pytest.mark.django_db
def test_publico_comunitario_nao_aceita_etapa(dados_curso):
    dados_curso["tipo_publico"] = TipoPublico.COMUNITARIO
    dados_curso["publico_descricao"] = "Adultos em vulnerabilidade digital"
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)


@pytest.mark.django_db
def test_publico_alvo_legivel(curso, dados_curso):
    assert curso.publico_alvo == "5o ano do Ensino Fundamental"
    dados_curso.update(
        tipo_publico=TipoPublico.COMUNITARIO,
        etapa_ano="",
        publico_descricao="Adultos em vulnerabilidade digital",
        titulo="Outro curso",
    )
    comunitario = Curso.objects.create(**dados_curso)
    assert comunitario.publico_alvo == "Adultos em vulnerabilidade digital"


@pytest.mark.django_db
def test_carga_horaria_zero_e_recusada(dados_curso):
    dados_curso["carga_horaria"] = 0
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)


@pytest.mark.django_db
def test_curso_sem_referencial_e_valido(curso):
    assert curso.referencial is None
    assert curso.competencias.count() == 0


@pytest.mark.django_db
def test_professor_responsavel_precisa_ser_professor(dados_curso, aluno):
    dados_curso["professor_responsavel"] = aluno
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_curso.py -v`
Expected: FAIL - `ImportError: cannot import name 'Curso' from 'apps.cursos.models'`.

- [ ] **Step 4: Implementar o modelo**

`apps/cursos/models/curso.py`:

```python
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.cursos.choices import Formato, StatusCurso, TipoPublico
from apps.referenciais.choices import ETAPAS


class Curso(models.Model):
    titulo = models.CharField("titulo", max_length=200)
    resumo = models.TextField("resumo")
    edicao = models.ForeignKey(
        "edicoes.Edicao", on_delete=models.PROTECT, related_name="cursos", verbose_name="edicao"
    )
    professor_responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cursos_como_responsavel",
        verbose_name="professor responsavel",
    )

    tipo_publico = models.CharField("tipo de publico", max_length=20, choices=TipoPublico.choices)
    etapa_ano = models.CharField("etapa ou ano escolar", max_length=4, choices=ETAPAS, blank=True)
    publico_descricao = models.CharField("descricao do publico", max_length=200, blank=True)

    referencial = models.ForeignKey(
        "referenciais.Referencial",
        on_delete=models.PROTECT,
        related_name="cursos",
        null=True,
        blank=True,
        verbose_name="referencial pedagogico",
    )
    competencias = models.ManyToManyField(
        "referenciais.Competencia", related_name="cursos", blank=True, verbose_name="competencias"
    )

    carga_horaria = models.PositiveSmallIntegerField("carga horaria (horas)", validators=[MinValueValidator(1)])
    formato = models.CharField("formato", max_length=20, choices=Formato.choices)
    pre_requisitos = models.TextField("pre-requisitos", blank=True)

    temas = models.ManyToManyField("cursos.Tema", related_name="cursos", blank=True, verbose_name="temas")
    palavras_chave = models.CharField("palavras-chave", max_length=300, blank=True)

    status = models.CharField(
        "situacao", max_length=30, choices=StatusCurso.choices, default=StatusCurso.RASCUNHO
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)
    publicado_em = models.DateTimeField("publicado em", null=True, blank=True)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["-criado_em"]

    def __str__(self):
        return self.titulo

    @property
    def publico_alvo(self):
        """Texto legivel do publico, seja etapa escolar ou grupo comunitario."""
        if self.tipo_publico == TipoPublico.ESCOLAR:
            return self.get_etapa_ano_display()
        return self.publico_descricao

    def clean(self):
        super().clean()
        erros = {}
        if self.tipo_publico == TipoPublico.ESCOLAR:
            if not self.etapa_ano:
                erros["etapa_ano"] = "Informe a etapa ou ano escolar."
            if self.publico_descricao:
                erros["publico_descricao"] = "Deixe vazio quando o publico e escolar."
        elif self.tipo_publico == TipoPublico.COMUNITARIO:
            if not self.publico_descricao:
                erros["publico_descricao"] = "Descreva o publico da comunidade."
            if self.etapa_ano:
                erros["etapa_ano"] = "Deixe vazio quando o publico e comunitario."
        if self.professor_responsavel_id and not self.professor_responsavel.e_professor:
            erros["professor_responsavel"] = "O responsavel precisa ter papel de professor."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
```

`apps/cursos/models/__init__.py`:

```python
from apps.cursos.models.curso import Curso
from apps.cursos.models.tema import Tema

__all__ = ["Curso", "Tema"]
```

- [ ] **Step 5: Migrar, rodar e commitar**

```bash
python manage.py makemigrations cursos
pytest apps/cursos/tests -v
git add apps/cursos
git commit -m "feat(cursos): modelo Curso com publico-alvo obrigatorio e referencial opcional"
```

Expected: PASS (9 testes de curso).

---

### Task 3: Equipe do curso

**Files:**
- Create: `apps/cursos/models/equipe.py`
- Modify: `apps/cursos/models/__init__.py`
- Test: `apps/cursos/tests/test_equipe.py`

**Interfaces:**
- Consumes: `Curso` (Task 2), `Usuario` (Plano 1).
- Produces: `apps.cursos.models.MembroEquipe` (`curso`, `aluno`, `adicionado_em`), único por (curso, aluno); `Curso.membros` como `related_name`; método `Curso.tem_membro(usuario) -> bool`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_equipe.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.cursos.models import MembroEquipe


@pytest.mark.django_db
def test_membro_e_vinculado_ao_curso(curso, aluno):
    MembroEquipe.objects.create(curso=curso, aluno=aluno)
    assert curso.membros.count() == 1
    assert curso.tem_membro(aluno)


@pytest.mark.django_db
def test_mesmo_aluno_duas_vezes_e_recusado(curso, aluno):
    MembroEquipe.objects.create(curso=curso, aluno=aluno)
    with pytest.raises(ValidationError):
        MembroEquipe.objects.create(curso=curso, aluno=aluno)


@pytest.mark.django_db
def test_professor_nao_pode_ser_membro_da_equipe(curso, professor):
    with pytest.raises(ValidationError):
        MembroEquipe.objects.create(curso=curso, aluno=professor)


@pytest.mark.django_db
def test_quem_nao_e_membro_nao_e_reconhecido(curso, aluno, outro_aluno):
    MembroEquipe.objects.create(curso=curso, aluno=aluno)
    assert curso.tem_membro(outro_aluno) is False
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_equipe.py -v`
Expected: FAIL - `ImportError: cannot import name 'MembroEquipe'`.

- [ ] **Step 3: Implementar**

`apps/cursos/models/equipe.py`:

```python
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class MembroEquipe(models.Model):
    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.CASCADE, related_name="membros", verbose_name="curso"
    )
    aluno = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="equipes", verbose_name="aluno"
    )
    adicionado_em = models.DateTimeField("adicionado em", auto_now_add=True)

    class Meta:
        verbose_name = "membro da equipe"
        verbose_name_plural = "membros da equipe"
        ordering = ["aluno__nome_completo"]
        constraints = [
            models.UniqueConstraint(fields=["curso", "aluno"], name="membro_unico_por_curso")
        ]

    def __str__(self):
        return f"{self.aluno.nome_completo} em {self.curso.titulo}"

    def clean(self):
        super().clean()
        if self.aluno_id and not self.aluno.e_aluno:
            raise ValidationError({"aluno": "So aluno pode compor a equipe de producao."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
```

Acrescente a `Curso` (em `apps/cursos/models/curso.py`, ao fim da classe):

```python
    def tem_membro(self, usuario):
        return self.membros.filter(aluno=usuario).exists()
```

E a `apps/cursos/models/__init__.py`:

```python
from apps.cursos.models.curso import Curso
from apps.cursos.models.equipe import MembroEquipe
from apps.cursos.models.tema import Tema

__all__ = ["Curso", "MembroEquipe", "Tema"]
```

- [ ] **Step 4: Migrar, rodar e commitar**

```bash
python manage.py makemigrations cursos
pytest apps/cursos/tests/test_equipe.py -v
git add apps/cursos
git commit -m "feat(cursos): equipe de producao vinculada ao curso"
```

Expected: PASS (4 testes).

---

### Task 4: Entregáveis, seções e o serviço de criação do curso

**Files:**
- Create: `apps/cursos/models/producao.py`, `apps/cursos/services.py`
- Modify: `apps/cursos/models/__init__.py`
- Test: `apps/cursos/tests/test_criacao.py`

**Interfaces:**
- Consumes: `Curso`, `MembroEquipe` (Tasks 2-3); `choices` (Task 1).
- Produces: `apps.cursos.models.Entregavel` (`curso`, `tipo`, `status`, `responsavel`, `atualizado_em`), `apps.cursos.models.Secao` (`entregavel`, `titulo`, `ordem`, `conteudo`, `atualizado_por`, `atualizado_em`); `apps.cursos.services.criar_curso(**dados) -> Curso` e `apps.cursos.services.adicionar_membro(curso, aluno, por) -> MembroEquipe`; constante `services.SECOES_PLANO_ENSINO`.

- [ ] **Step 1: Instalar o sanitizador de HTML**

```bash
pip install nh3
```

Acrescente `nh3` à lista de dependências no `pyproject.toml` (seção `[project] dependencies`, ou o arquivo `requirements.txt` se estiver usando um).

- [ ] **Step 2: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_criacao.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel
from apps.cursos.models import Entregavel, Secao


@pytest.mark.django_db
def test_criar_curso_gera_os_cinco_entregaveis(dados_curso):
    curso = services.criar_curso(**dados_curso)
    tipos = list(curso.entregaveis.values_list("tipo", flat=True))
    assert sorted(tipos) == sorted([t.value for t in TipoEntregavel])
    assert all(e.status == StatusEntregavel.RASCUNHO for e in curso.entregaveis.all())


@pytest.mark.django_db
def test_criar_curso_gera_as_secoes_do_plano_de_ensino(dados_curso):
    curso = services.criar_curso(**dados_curso)
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    titulos = list(plano.secoes.order_by("ordem").values_list("titulo", flat=True))
    assert titulos == services.SECOES_PLANO_ENSINO
    assert all(secao.conteudo == "" for secao in plano.secoes.all())


@pytest.mark.django_db
def test_apenas_o_plano_de_ensino_nasce_com_secoes(dados_curso):
    curso = services.criar_curso(**dados_curso)
    outros = curso.entregaveis.exclude(tipo=TipoEntregavel.PLANO_ENSINO)
    assert Secao.objects.filter(entregavel__in=outros).count() == 0


@pytest.mark.django_db
def test_adicionar_o_primeiro_membro_leva_o_curso_para_producao(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    assert curso.status == StatusCurso.RASCUNHO
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO


@pytest.mark.django_db
def test_entregavel_repetido_no_mesmo_curso_e_recusado(dados_curso):
    curso = services.criar_curso(**dados_curso)
    with pytest.raises(ValidationError):
        Entregavel.objects.create(curso=curso, tipo=TipoEntregavel.SLIDES)


@pytest.mark.django_db
def test_conteudo_da_secao_e_sanitizado(dados_curso):
    curso = services.criar_curso(**dados_curso)
    secao = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO).secoes.first()
    secao.conteudo = "<p>Texto</p><script>alert(1)</script>"
    secao.save()
    secao.refresh_from_db()
    assert "<p>Texto</p>" in secao.conteudo
    assert "script" not in secao.conteudo


@pytest.mark.django_db
def test_criar_curso_e_atomico(dados_curso):
    dados_curso["carga_horaria"] = 0
    from apps.cursos.models import Curso

    with pytest.raises(ValidationError):
        services.criar_curso(**dados_curso)
    assert Curso.objects.count() == 0
    assert Entregavel.objects.count() == 0
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_criacao.py -v`
Expected: FAIL - `ImportError: cannot import name 'Entregavel'`.

- [ ] **Step 4: Implementar os modelos de produção**

`apps/cursos/models/producao.py`:

```python
import nh3
from django.conf import settings
from django.db import models

from apps.cursos.choices import StatusEntregavel, TipoEntregavel

TAGS_PERMITIDAS = {
    "p", "br", "strong", "em", "u", "ul", "ol", "li",
    "h2", "h3", "h4", "blockquote", "a", "table", "thead",
    "tbody", "tr", "th", "td",
}


class Entregavel(models.Model):
    """Um dos cinco pacotes obrigatorios do roteiro. E a unidade de revisao:
    o professor aprova ou devolve o entregavel, nunca item por item (spec 4.6)."""

    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.CASCADE, related_name="entregaveis", verbose_name="curso"
    )
    tipo = models.CharField("tipo", max_length=20, choices=TipoEntregavel.choices)
    status = models.CharField(
        "situacao", max_length=20, choices=StatusEntregavel.choices, default=StatusEntregavel.RASCUNHO
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entregaveis_sob_responsabilidade",
        verbose_name="aluno responsavel",
    )
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "entregavel"
        verbose_name_plural = "entregaveis"
        ordering = ["curso", "tipo"]
        constraints = [
            models.UniqueConstraint(fields=["curso", "tipo"], name="entregavel_unico_por_curso")
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.curso.titulo}"

    @property
    def editavel(self):
        return self.status in (StatusEntregavel.RASCUNHO, StatusEntregavel.DEVOLVIDO)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Secao(models.Model):
    entregavel = models.ForeignKey(
        Entregavel, on_delete=models.CASCADE, related_name="secoes", verbose_name="entregavel"
    )
    titulo = models.CharField("titulo", max_length=120)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)
    conteudo = models.TextField("conteudo", blank=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secoes_atualizadas",
        verbose_name="atualizado por",
    )
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "secao"
        verbose_name_plural = "secoes"
        ordering = ["entregavel", "ordem", "id"]

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        # Sanitiza sempre, inclusive quando o texto vem de um servico e nao de um form:
        # e a unica barreira entre o editor de texto rico e um script no navegador do professor.
        self.conteudo = nh3.clean(self.conteudo or "", tags=TAGS_PERMITIDAS)
        self.full_clean()
        super().save(*args, **kwargs)
```

- [ ] **Step 5: Implementar o serviço de criação**

`apps/cursos/services.py`:

```python
from django.db import transaction

from apps.cursos.choices import StatusCurso, TipoEntregavel
from apps.cursos.models import Curso, Entregavel, MembroEquipe, Secao

SECOES_PLANO_ENSINO = [
    "Ementa",
    "Objetivos",
    "Conteudo programatico",
    "Metodologia",
    "Cronograma",
    "Avaliacao",
    "Referencias",
]


@transaction.atomic
def criar_curso(**dados):
    """Cria o curso, seus cinco entregaveis e as secoes iniciais do Plano de Ensino.

    Feito aqui, e nao por sinal post_save: sinal e invisivel no fluxo, dificil de
    testar e nao dispara de forma confiavel em fixtures e criacoes em lote (spec 4.6).
    """
    curso = Curso.objects.create(**dados)
    for tipo in TipoEntregavel:
        entregavel = Entregavel.objects.create(curso=curso, tipo=tipo)
        if tipo == TipoEntregavel.PLANO_ENSINO:
            for ordem, titulo in enumerate(SECOES_PLANO_ENSINO, start=1):
                Secao.objects.create(entregavel=entregavel, titulo=titulo, ordem=ordem)
    return curso


@transaction.atomic
def adicionar_membro(curso, aluno, por):
    """Vincula um aluno a equipe. O primeiro membro tira o curso do rascunho."""
    membro = MembroEquipe.objects.create(curso=curso, aluno=aluno)
    if curso.status == StatusCurso.RASCUNHO:
        curso.status = StatusCurso.EM_PRODUCAO
        curso.save()
    return membro
```

O parâmetro `por` ainda não é usado; ele existe porque a Task 8 vai fazer a checagem de permissão dentro do serviço, e mudar a assinatura depois obrigaria a mexer em todas as chamadas.

- [ ] **Step 6: Atualizar o pacote de modelos, migrar e commitar**

`apps/cursos/models/__init__.py`:

```python
from apps.cursos.models.curso import Curso
from apps.cursos.models.equipe import MembroEquipe
from apps.cursos.models.producao import Entregavel, Secao
from apps.cursos.models.tema import Tema

__all__ = ["Curso", "Entregavel", "MembroEquipe", "Secao", "Tema"]
```

```bash
python manage.py makemigrations cursos
pytest apps/cursos/tests/test_criacao.py -v
git add apps/cursos pyproject.toml
git commit -m "feat(cursos): entregaveis, secoes e servico de criacao do curso"
```

Expected: PASS (7 testes).

---

### Task 5: Arquivos e anexos

**Files:**
- Create: `apps/cursos/models/anexo.py`, `apps/cursos/arquivos.py`
- Modify: `apps/cursos/models/__init__.py`, `config/settings.py` (limites de upload)
- Test: `apps/cursos/tests/test_anexo.py`

**Interfaces:**
- Consumes: `Entregavel`, `Secao` (Task 4).
- Produces: `apps.cursos.models.Arquivo` (`identificador`, `arquivo`, `nome_original`, `tamanho`, `mime`, `hash_conteudo`, `enviado_por`, `enviado_em`), `apps.cursos.models.Anexo` (`entregavel`, `secao`, `tipo_midia`, `arquivo`, `url`, `titulo`, `descricao`, `referencia_bibliografica`, `rotulo`, `tipo_pratica`, `duracao_minutos`, `enviado_por`, `enviado_em`); `apps.cursos.arquivos.detecta_mime(cabecalho: bytes) -> str | None`, `LIMITES: dict[str, int]`, `valida_upload(nome, tamanho, cabecalho) -> str`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_anexo.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.cursos.arquivos import detecta_mime, valida_upload
from apps.cursos.choices import TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo

PDF = b"%PDF-1.7\n%..."
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
ZIP = b"PK\x03\x04" + b"\x00" * 8


def test_detecta_pdf_png_e_zip():
    assert detecta_mime(PDF) == "application/pdf"
    assert detecta_mime(PNG) == "image/png"
    assert detecta_mime(ZIP) == "application/zip"


def test_conteudo_desconhecido_nao_e_detectado():
    assert detecta_mime(b"nao sou arquivo conhecido") is None


def test_extensao_mentirosa_e_recusada():
    with pytest.raises(ValidationError):
        valida_upload("relatorio.pdf", tamanho=100, cabecalho=b"MZ\x90\x00 executavel")


def test_pdf_acima_do_limite_e_recusado():
    with pytest.raises(ValidationError):
        valida_upload("plano.pdf", tamanho=21 * 1024 * 1024, cabecalho=PDF)


def test_pdf_dentro_do_limite_devolve_o_mime():
    assert valida_upload("plano.pdf", tamanho=19 * 1024 * 1024, cabecalho=PDF) == "application/pdf"


def test_imagem_acima_do_limite_e_recusada():
    with pytest.raises(ValidationError):
        valida_upload("card.png", tamanho=11 * 1024 * 1024, cabecalho=PNG)


@pytest.fixture
def entregavel_cards(dados_curso):
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    return curso.entregaveis.get(tipo=TipoEntregavel.CARDS)


@pytest.mark.django_db
def test_anexo_de_link_nao_aceita_arquivo(entregavel_cards, aluno):
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.LINK,
        titulo="Atividade no Scratch",
        url="",
        enviado_por=aluno,
    )
    with pytest.raises(ValidationError):
        anexo.full_clean()


@pytest.mark.django_db
def test_anexo_de_arquivo_exige_arquivo(entregavel_cards, aluno):
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.ARQUIVO,
        titulo="Card 1",
        enviado_por=aluno,
    )
    with pytest.raises(ValidationError):
        anexo.full_clean()


@pytest.mark.django_db
def test_video_exige_duracao(entregavel_cards, aluno, arquivo_qualquer):
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.VIDEO,
        titulo="Aula 1",
        arquivo=arquivo_qualquer,
        enviado_por=aluno,
    )
    with pytest.raises(ValidationError):
        anexo.full_clean()
```

Acrescente ao `apps/cursos/tests/conftest.py`:

```python
@pytest.fixture
def arquivo_qualquer(aluno, db):
    from django.core.files.base import ContentFile

    from apps.cursos.models import Arquivo

    registro = Arquivo(
        nome_original="material.pdf",
        tamanho=12,
        mime="application/pdf",
        hash_conteudo="0" * 64,
        enviado_por=aluno,
    )
    registro.arquivo.save("material.pdf", ContentFile(b"%PDF-1.7\n..."), save=False)
    registro.save()
    return registro
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_anexo.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'apps.cursos.arquivos'`.

- [ ] **Step 3: Implementar a detecção de tipo por conteúdo**

`apps/cursos/arquivos.py`:

```python
from pathlib import Path

from django.core.exceptions import ValidationError

MEGA = 1024 * 1024

# Assinatura no inicio do arquivo -> mime. Conferir o conteudo, e nao a extensao,
# e o que impede um executavel renomeado para .pdf de entrar no sistema (spec 8).
ASSINATURAS = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"PK\x03\x04", "application/zip"),  # pptx, odp e docx sao zip
]

LIMITES = {
    "application/pdf": 20 * MEGA,
    "image/png": 10 * MEGA,
    "image/jpeg": 10 * MEGA,
    "application/zip": 50 * MEGA,
}

EXTENSOES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pptx": "application/zip",
    ".odp": "application/zip",
    ".docx": "application/zip",
}


def detecta_mime(cabecalho):
    """Devolve o mime pela assinatura do arquivo, ou None se nao reconhecer."""
    for assinatura, mime in ASSINATURAS:
        if cabecalho.startswith(assinatura):
            return mime
    return None


def valida_upload(nome, tamanho, cabecalho):
    """Confere tipo e tamanho e devolve o mime. Levanta ValidationError se recusar."""
    mime = detecta_mime(cabecalho)
    if mime is None:
        raise ValidationError("Tipo de arquivo nao reconhecido ou nao permitido.")
    esperado = EXTENSOES.get(Path(nome).suffix.lower())
    if esperado != mime:
        raise ValidationError(
            f"O conteudo do arquivo nao corresponde a extensao {Path(nome).suffix}."
        )
    limite = LIMITES[mime]
    if tamanho > limite:
        raise ValidationError(f"Arquivo acima do limite de {limite // MEGA} MB para este tipo.")
    return mime
```

- [ ] **Step 4: Implementar os modelos**

`apps/cursos/models/anexo.py`:

```python
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.cursos.choices import Rotulo, TipoMidia, TipoPratica


def caminho_do_arquivo(instance, filename):
    """Nome em disco por UUID: o nome original e so metadado exibido (spec 8)."""
    return f"materiais/{instance.identificador.hex[:2]}/{instance.identificador.hex}"


class Arquivo(models.Model):
    """O conteudo binario, separado do anexo que o referencia. Versoes diferentes de
    um curso apontam para o MESMO Arquivo: clonar um curso nao pode clonar 3 GB de
    video (spec 4.6). Imutavel apos a criacao."""

    identificador = models.UUIDField("identificador", default=uuid.uuid4, unique=True, editable=False)
    arquivo = models.FileField("arquivo", upload_to=caminho_do_arquivo, max_length=255)
    nome_original = models.CharField("nome original", max_length=255)
    tamanho = models.PositiveBigIntegerField("tamanho em bytes")
    mime = models.CharField("tipo", max_length=100)
    hash_conteudo = models.CharField("hash do conteudo", max_length=64)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="arquivos_enviados"
    )
    enviado_em = models.DateTimeField("enviado em", auto_now_add=True)

    class Meta:
        verbose_name = "arquivo"
        verbose_name_plural = "arquivos"
        ordering = ["-enviado_em"]
        indexes = [models.Index(fields=["hash_conteudo"])]

    def __str__(self):
        return self.nome_original


class Anexo(models.Model):
    entregavel = models.ForeignKey(
        "cursos.Entregavel", on_delete=models.CASCADE, related_name="anexos", verbose_name="entregavel"
    )
    secao = models.ForeignKey(
        "cursos.Secao",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anexos",
        verbose_name="secao",
    )
    tipo_midia = models.CharField("tipo", max_length=20, choices=TipoMidia.choices)
    arquivo = models.ForeignKey(
        Arquivo, on_delete=models.PROTECT, null=True, blank=True, related_name="anexos"
    )
    url = models.URLField("link", blank=True)
    titulo = models.CharField("titulo", max_length=200)
    descricao = models.TextField("descricao", blank=True)
    referencia_bibliografica = models.TextField("referencia bibliografica", blank=True)
    rotulo = models.CharField("rotulo", max_length=20, choices=Rotulo.choices, default=Rotulo.NENHUM)
    tipo_pratica = models.CharField(
        "tipo de pratica", max_length=20, choices=TipoPratica.choices, default=TipoPratica.NENHUM
    )
    duracao_minutos = models.PositiveSmallIntegerField("duracao em minutos", null=True, blank=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="anexos_enviados"
    )
    enviado_em = models.DateTimeField("enviado em", auto_now_add=True)

    class Meta:
        verbose_name = "anexo"
        verbose_name_plural = "anexos"
        ordering = ["entregavel", "id"]

    def __str__(self):
        return self.titulo

    def clean(self):
        super().clean()
        erros = {}
        if self.tipo_midia == TipoMidia.LINK:
            if not self.url:
                erros["url"] = "Informe o endereco do link."
            if self.arquivo_id:
                erros["arquivo"] = "Anexo de link nao tem arquivo."
        else:
            if not self.arquivo_id:
                erros["arquivo"] = "Envie o arquivo."
            if self.url:
                erros["url"] = "Anexo de arquivo nao tem link."
        if self.tipo_midia == TipoMidia.VIDEO and not self.duracao_minutos:
            erros["duracao_minutos"] = "Informe a duracao do video em minutos."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
```

- [ ] **Step 5: Configurar os limites no Django**

Em `config/settings.py`, depois de `MEDIA_ROOT`:

```python
# Acima disto o upload vai para arquivo temporario em vez de ficar na memoria.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
# Teto geral do corpo da requisicao nesta etapa; o Plano 4 sobe o limite so na
# rota de upload de video em blocos.
DATA_UPLOAD_MAX_MEMORY_SIZE = 55 * 1024 * 1024
```

- [ ] **Step 6: Atualizar o pacote, migrar, rodar e commitar**

`apps/cursos/models/__init__.py`:

```python
from apps.cursos.models.anexo import Anexo, Arquivo
from apps.cursos.models.curso import Curso
from apps.cursos.models.equipe import MembroEquipe
from apps.cursos.models.producao import Entregavel, Secao
from apps.cursos.models.tema import Tema

__all__ = ["Anexo", "Arquivo", "Curso", "Entregavel", "MembroEquipe", "Secao", "Tema"]
```

```bash
python manage.py makemigrations cursos
pytest apps/cursos/tests/test_anexo.py -v
git add apps/cursos config/settings.py
git commit -m "feat(cursos): arquivos com tipo conferido pelo conteudo e anexos"
```

Expected: PASS (9 testes).

---

### Task 6: Validações do roteiro

**Files:**
- Create: `apps/cursos/validacoes.py`
- Test: `apps/cursos/tests/test_validacoes.py`

**Interfaces:**
- Consumes: `Entregavel`, `Anexo`, `Secao`, `Curso` (Tasks 2-5); `Referencial.valida_quantidade` (Plano 1).
- Produces: `apps.cursos.validacoes.pendencias(entregavel) -> list[str]` - a lista do que falta, vazia quando o entregável pode ser enviado. Usada pelo serviço da Task 7 e pelas telas da Task 9 (é o que mostra ao aluno o que falta antes de ele clicar em enviar).

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_validacoes.py`:

```python
import pytest

from apps.cursos import services, validacoes
from apps.cursos.choices import Rotulo, TipoEntregavel, TipoMidia, TipoPratica
from apps.cursos.models import Anexo


@pytest.fixture
def curso_criado(dados_curso):
    return services.criar_curso(**dados_curso)


def anexa(entregavel, aluno, arquivo, **extra):
    dados = {
        "entregavel": entregavel,
        "tipo_midia": TipoMidia.ARQUIVO,
        "titulo": "Material",
        "arquivo": arquivo,
        "enviado_por": aluno,
    }
    dados.update(extra)
    return Anexo.objects.create(**dados)


@pytest.mark.django_db
def test_plano_de_ensino_sem_anexo_e_sem_conteudo_lista_as_duas_faltas(curso_criado):
    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    faltas = validacoes.pendencias(plano)
    assert any("PDF" in f for f in faltas)
    assert any("secao" in f.lower() for f in faltas)


@pytest.mark.django_db
def test_plano_de_ensino_completo_nao_tem_pendencia(curso_criado, aluno, arquivo_qualquer):
    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    anexa(plano, aluno, arquivo_qualquer)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa da oficina.</p>"
    secao.save()
    assert validacoes.pendencias(plano) == []


@pytest.mark.django_db
def test_cards_sem_referencia_bibliografica_sao_apontados(curso_criado, aluno, arquivo_qualquer):
    cards = curso_criado.entregaveis.get(tipo=TipoEntregavel.CARDS)
    anexa(cards, aluno, arquivo_qualquer, titulo="Card 1")
    faltas = validacoes.pendencias(cards)
    assert len(faltas) == 1
    assert "Card 1" in faltas[0]


@pytest.mark.django_db
def test_cards_com_referencia_passam(curso_criado, aluno, arquivo_qualquer):
    cards = curso_criado.entregaveis.get(tipo=TipoEntregavel.CARDS)
    anexa(cards, aluno, arquivo_qualquer, referencia_bibliografica="BRASIL, 2022.")
    assert validacoes.pendencias(cards) == []


@pytest.mark.django_db
def test_caderno_exige_as_duas_versoes_e_as_duas_praticas(curso_criado, aluno, arquivo_qualquer):
    caderno = curso_criado.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    anexa(caderno, aluno, arquivo_qualquer, rotulo=Rotulo.SEM_GABARITO, tipo_pratica=TipoPratica.PLUGADA)
    faltas = validacoes.pendencias(caderno)
    assert any("gabarito" in f for f in faltas)
    assert any("desplugada" in f for f in faltas)


@pytest.mark.django_db
def test_caderno_completo_passa(curso_criado, aluno, arquivo_qualquer):
    caderno = curso_criado.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    anexa(caderno, aluno, arquivo_qualquer, rotulo=Rotulo.SEM_GABARITO, tipo_pratica=TipoPratica.PLUGADA)
    anexa(caderno, aluno, arquivo_qualquer, rotulo=Rotulo.COM_GABARITO, tipo_pratica=TipoPratica.DESPLUGADA)
    assert validacoes.pendencias(caderno) == []


@pytest.mark.django_db
@pytest.mark.parametrize("quantidade,tem_falta", [(1, True), (2, False), (3, False), (4, True)])
def test_videos_de_dois_a_tres(curso_criado, aluno, arquivo_qualquer, quantidade, tem_falta):
    videos = curso_criado.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    for numero in range(quantidade):
        anexa(videos, aluno, arquivo_qualquer, tipo_midia=TipoMidia.VIDEO,
              titulo=f"Aula {numero}", duracao_minutos=7)
    assert bool(validacoes.pendencias(videos)) is tem_falta


@pytest.mark.django_db
@pytest.mark.parametrize("duracao", [4, 11])
def test_video_fora_da_faixa_de_duracao(curso_criado, aluno, arquivo_qualquer, duracao):
    videos = curso_criado.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    for numero in range(2):
        anexa(videos, aluno, arquivo_qualquer, tipo_midia=TipoMidia.VIDEO,
              titulo=f"Aula {numero}", duracao_minutos=duracao)
    assert any("minutos" in f for f in validacoes.pendencias(videos))


@pytest.mark.django_db
def test_link_nao_conta_como_video(curso_criado, aluno):
    videos = curso_criado.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    for numero in range(2):
        Anexo.objects.create(
            entregavel=videos, tipo_midia=TipoMidia.LINK, titulo=f"Video {numero}",
            url="https://exemplo.org/video", enviado_por=aluno,
        )
    assert validacoes.pendencias(videos) != []


@pytest.mark.django_db
def test_curso_com_referencial_fora_da_faixa_e_apontado(curso_criado, aluno, arquivo_qualquer, db):
    from apps.referenciais.models import Categoria, Competencia, Referencial

    referencial = Referencial.objects.create(
        nome="BNCC da Computacao", sigla="BNCC-COMP", min_competencias=2, max_competencias=5
    )
    categoria = Categoria.objects.create(referencial=referencial, nome="Mundo Digital", ordem=1)
    competencia = Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="EF05CO01",
        descricao="Descricao", etapa="EF05", ordem=1,
    )
    curso_criado.referencial = referencial
    curso_criado.save()
    curso_criado.competencias.add(competencia)

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    anexa(plano, aluno, arquivo_qualquer)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()

    assert any("competencias" in f for f in validacoes.pendencias(plano))


@pytest.mark.django_db
def test_slides_exigem_ao_menos_um_arquivo(curso_criado, aluno, arquivo_qualquer):
    slides = curso_criado.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    assert validacoes.pendencias(slides) != []
    anexa(slides, aluno, arquivo_qualquer)
    assert validacoes.pendencias(slides) == []
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_validacoes.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'apps.cursos.validacoes'`.

- [ ] **Step 3: Implementar as validações**

`apps/cursos/validacoes.py`:

```python
from django.core.exceptions import ValidationError

from apps.cursos.choices import Rotulo, TipoEntregavel, TipoMidia, TipoPratica

DURACAO_MINIMA = 5
DURACAO_MAXIMA = 10


def pendencias(entregavel):
    """Lista o que falta para o entregavel poder ir a revisao (spec 6).

    Devolve textos prontos para mostrar ao aluno. Lista vazia significa que pode
    enviar. E lista, e nao um sim/nao, porque a mensagem e o produto: e ela que
    evita a ida e volta com o professor.
    """
    regras = {
        TipoEntregavel.PLANO_ENSINO: _plano_de_ensino,
        TipoEntregavel.CARDS: _cards,
        TipoEntregavel.CADERNO: _caderno,
        TipoEntregavel.VIDEOS: _videos,
        TipoEntregavel.SLIDES: _slides,
    }
    return regras[entregavel.tipo](entregavel)


def _arquivos(entregavel):
    return entregavel.anexos.exclude(tipo_midia=TipoMidia.LINK)


def _plano_de_ensino(entregavel):
    faltas = []
    if not _arquivos(entregavel).filter(arquivo__mime="application/pdf").exists():
        faltas.append("Anexe o plano de ensino em PDF.")
    if not entregavel.secoes.exclude(conteudo="").exists():
        faltas.append("Preencha ao menos uma secao do plano de ensino.")
    faltas.extend(_dados_do_curso(entregavel.curso))
    return faltas


def _dados_do_curso(curso):
    """Campos que sao do Curso, nao do Entregavel (spec 4.3): a validacao le
    entregavel.curso. A mesma checagem se repete na submissao ao coordenador,
    porque o curso pode ser editado depois do plano aprovado."""
    faltas = []
    if not curso.publico_alvo:
        faltas.append("Defina o publico-alvo do curso.")
    if not curso.carga_horaria:
        faltas.append("Informe a carga horaria do curso.")
    if not curso.formato:
        faltas.append("Informe o formato do curso.")
    if curso.referencial_id:
        try:
            curso.referencial.valida_quantidade(curso.competencias.count())
        except ValidationError as erro:
            faltas.append(erro.messages[0])
    return faltas


def _cards(entregavel):
    anexos = list(_arquivos(entregavel))
    if not anexos:
        faltas = ["Anexe ao menos um card."]
        return faltas
    sem_referencia = [a.titulo for a in anexos if not a.referencia_bibliografica.strip()]
    if sem_referencia:
        return [
            "Informe a referencia bibliografica em: " + ", ".join(sem_referencia) + "."
        ]
    return []


def _caderno(entregavel):
    anexos = list(_arquivos(entregavel))
    faltas = []
    if not any(a.rotulo == Rotulo.SEM_GABARITO for a in anexos):
        faltas.append("Anexe a versao sem gabarito.")
    if not any(a.rotulo == Rotulo.COM_GABARITO for a in anexos):
        faltas.append("Anexe a versao com gabarito.")
    plugadas = {TipoPratica.PLUGADA, TipoPratica.AMBAS}
    desplugadas = {TipoPratica.DESPLUGADA, TipoPratica.AMBAS}
    if not any(a.tipo_pratica in plugadas for a in anexos):
        faltas.append("Inclua ao menos uma atividade plugada.")
    if not any(a.tipo_pratica in desplugadas for a in anexos):
        faltas.append("Inclua ao menos uma atividade desplugada.")
    return faltas


def _videos(entregavel):
    videos = list(entregavel.anexos.filter(tipo_midia=TipoMidia.VIDEO))
    faltas = []
    if not 2 <= len(videos) <= 3:
        faltas.append(f"Envie de 2 a 3 videos; ha {len(videos)}.")
    fora_da_faixa = [
        v.titulo for v in videos
        if not (DURACAO_MINIMA <= (v.duracao_minutos or 0) <= DURACAO_MAXIMA)
    ]
    if fora_da_faixa:
        faltas.append(
            f"Cada video deve ter de {DURACAO_MINIMA} a {DURACAO_MAXIMA} minutos; "
            f"fora da faixa: {', '.join(fora_da_faixa)}."
        )
    return faltas


def _slides(entregavel):
    if not _arquivos(entregavel).exists():
        return ["Anexe ao menos um arquivo de slides."]
    return []
```

- [ ] **Step 4: Rodar e commitar**

```bash
pytest apps/cursos/tests/test_validacoes.py -v
git add apps/cursos
git commit -m "feat(cursos): validacoes do roteiro por entregavel"
```

Expected: PASS (16 testes, contando as parametrizações).

---

### Task 7: Máquina de estados da revisão

**Files:**
- Create: `apps/cursos/models/revisao.py`
- Modify: `apps/cursos/services.py`, `apps/cursos/models/__init__.py`
- Test: `apps/cursos/tests/test_revisao.py`

**Interfaces:**
- Consumes: `Entregavel`, `validacoes.pendencias` (Tasks 4 e 6).
- Produces: `apps.cursos.models.Revisao` (`entregavel`, `revisor`, `decisao`, `comentario`, `criado_em`); `services.enviar_para_revisao(entregavel, por)`, `services.aprovar_entregavel(entregavel, por, comentario="")`, `services.devolver_entregavel(entregavel, por, comentario)`; `Curso.pronto_para_o_coordenador -> bool`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_revisao.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo, Revisao


@pytest.fixture
def slides_prontos(dados_curso, aluno, arquivo_qualquer):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    return slides


@pytest.mark.django_db
def test_enviar_para_revisao_muda_o_estado(slides_prontos, aluno):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.EM_REVISAO
    assert slides_prontos.editavel is False


@pytest.mark.django_db
def test_enviar_com_pendencia_e_recusado(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    with pytest.raises(ValidationError) as erro:
        services.enviar_para_revisao(slides, por=aluno)
    assert "slides" in erro.value.messages[0].lower()
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.RASCUNHO


@pytest.mark.django_db
def test_aprovar_registra_revisao(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.aprovar_entregavel(slides_prontos, por=professor, comentario="Otimo trabalho.")
    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.APROVADO
    revisao = Revisao.objects.get(entregavel=slides_prontos)
    assert revisao.decisao == Revisao.APROVADO
    assert revisao.revisor == professor


@pytest.mark.django_db
def test_devolver_exige_comentario(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    with pytest.raises(ValidationError):
        services.devolver_entregavel(slides_prontos, por=professor, comentario="   ")
    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.EM_REVISAO


@pytest.mark.django_db
def test_devolver_reabre_para_edicao(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.devolver_entregavel(slides_prontos, por=professor, comentario="Faltou a ultima aula.")
    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.DEVOLVIDO
    assert slides_prontos.editavel is True


@pytest.mark.django_db
def test_ciclo_de_devolucao_e_reenvio_guarda_o_historico(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.devolver_entregavel(slides_prontos, por=professor, comentario="Corrija a capa.")
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.aprovar_entregavel(slides_prontos, por=professor)
    assert list(Revisao.objects.filter(entregavel=slides_prontos).values_list("decisao", flat=True)) == [
        Revisao.DEVOLVIDO,
        Revisao.APROVADO,
    ]


@pytest.mark.django_db
def test_nao_se_aprova_entregavel_que_nao_esta_em_revisao(slides_prontos, professor):
    with pytest.raises(ValidationError):
        services.aprovar_entregavel(slides_prontos, por=professor)


@pytest.mark.django_db
def test_nao_se_reenvia_entregavel_aprovado(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.aprovar_entregavel(slides_prontos, por=professor)
    with pytest.raises(ValidationError):
        services.enviar_para_revisao(slides_prontos, por=aluno)


@pytest.mark.django_db
def test_curso_so_fica_pronto_com_os_cinco_aprovados(slides_prontos, aluno, professor):
    curso = slides_prontos.curso
    assert curso.pronto_para_o_coordenador is False
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.aprovar_entregavel(slides_prontos, por=professor)
    curso.refresh_from_db()
    assert curso.pronto_para_o_coordenador is False
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    assert curso.pronto_para_o_coordenador is True
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_revisao.py -v`
Expected: FAIL - `ImportError: cannot import name 'Revisao'`.

- [ ] **Step 3: Implementar o modelo de revisão**

`apps/cursos/models/revisao.py`:

```python
from django.conf import settings
from django.db import models


class Revisao(models.Model):
    """Registro imutavel de cada decisao do professor. Nunca sobrescrito: e o
    historico das idas e vindas (spec 4.6)."""

    APROVADO = "APROVADO"
    DEVOLVIDO = "DEVOLVIDO"
    DECISOES = [(APROVADO, "Aprovado"), (DEVOLVIDO, "Devolvido")]

    entregavel = models.ForeignKey(
        "cursos.Entregavel", on_delete=models.CASCADE, related_name="revisoes", verbose_name="entregavel"
    )
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="revisoes", verbose_name="revisor"
    )
    decisao = models.CharField("decisao", max_length=20, choices=DECISOES)
    comentario = models.TextField("comentario", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "revisao"
        verbose_name_plural = "revisoes"
        ordering = ["criado_em"]

    def __str__(self):
        return f"{self.get_decisao_display()} em {self.entregavel}"
```

- [ ] **Step 4: Acrescentar as transições ao serviço**

Ao fim de `apps/cursos/services.py`:

```python
from django.core.exceptions import ValidationError

from apps.cursos import validacoes
from apps.cursos.choices import StatusEntregavel
from apps.cursos.models import Revisao


@transaction.atomic
def enviar_para_revisao(entregavel, por):
    if not entregavel.editavel:
        raise ValidationError(
            f"Este entregavel esta {entregavel.get_status_display().lower()} e nao pode ser reenviado."
        )
    faltas = validacoes.pendencias(entregavel)
    if faltas:
        raise ValidationError(faltas)
    entregavel.status = StatusEntregavel.EM_REVISAO
    entregavel.save()
    return entregavel


@transaction.atomic
def aprovar_entregavel(entregavel, por, comentario=""):
    _exige_em_revisao(entregavel)
    entregavel.status = StatusEntregavel.APROVADO
    entregavel.save()
    Revisao.objects.create(
        entregavel=entregavel, revisor=por, decisao=Revisao.APROVADO, comentario=comentario
    )
    return entregavel


@transaction.atomic
def devolver_entregavel(entregavel, por, comentario):
    _exige_em_revisao(entregavel)
    if not (comentario or "").strip():
        raise ValidationError("Escreva o que precisa ser corrigido antes de devolver.")
    entregavel.status = StatusEntregavel.DEVOLVIDO
    entregavel.save()
    Revisao.objects.create(
        entregavel=entregavel, revisor=por, decisao=Revisao.DEVOLVIDO, comentario=comentario
    )
    return entregavel


def _exige_em_revisao(entregavel):
    if entregavel.status != StatusEntregavel.EM_REVISAO:
        raise ValidationError("So e possivel revisar um entregavel que foi enviado para revisao.")
```

Acrescente a `Curso` (em `apps/cursos/models/curso.py`):

```python
    @property
    def pronto_para_o_coordenador(self):
        """Os cinco entregaveis aprovados liberam o curso para o coordenador (spec 5)."""
        from apps.cursos.choices import StatusEntregavel, TipoEntregavel

        aprovados = self.entregaveis.filter(status=StatusEntregavel.APROVADO).count()
        return aprovados == len(TipoEntregavel.values)
```

E ao `apps/cursos/models/__init__.py`:

```python
from apps.cursos.models.anexo import Anexo, Arquivo
from apps.cursos.models.curso import Curso
from apps.cursos.models.equipe import MembroEquipe
from apps.cursos.models.producao import Entregavel, Secao
from apps.cursos.models.revisao import Revisao
from apps.cursos.models.tema import Tema

__all__ = ["Anexo", "Arquivo", "Curso", "Entregavel", "MembroEquipe", "Revisao", "Secao", "Tema"]
```

- [ ] **Step 5: Migrar, rodar e commitar**

```bash
python manage.py makemigrations cursos
pytest apps/cursos/tests/test_revisao.py -v
git add apps/cursos
git commit -m "feat(cursos): maquina de estados da revisao com historico imutavel"
```

Expected: PASS (9 testes).

---

### Task 8: Permissões

**Files:**
- Create: `apps/cursos/permissions.py`
- Modify: `apps/cursos/services.py`
- Test: `apps/cursos/tests/test_permissions.py`

**Interfaces:**
- Consumes: `Curso`, `Entregavel` (Tasks 2-7).
- Produces: `apps.cursos.permissions.pode_ver_curso(usuario, curso) -> bool`, `pode_editar_producao(usuario, entregavel) -> bool`, `pode_revisar(usuario, curso) -> bool`, `pode_gerir_equipe(usuario, curso) -> bool`, e `garante(condicao, mensagem)` que levanta `django.core.exceptions.PermissionDenied`. Os serviços da Task 7 e da Task 4 passam a exigir permissão.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_permissions.py`:

```python
import pytest
from django.core.exceptions import PermissionDenied

from apps.cursos import permissions, services
from apps.cursos.choices import TipoEntregavel


@pytest.fixture
def curso_com_equipe(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso


@pytest.mark.django_db
def test_membro_ve_o_curso(curso_com_equipe, aluno):
    assert permissions.pode_ver_curso(aluno, curso_com_equipe)


@pytest.mark.django_db
def test_aluno_de_fora_nao_ve_o_curso(curso_com_equipe, outro_aluno):
    assert permissions.pode_ver_curso(outro_aluno, curso_com_equipe) is False


@pytest.mark.django_db
def test_professor_de_outro_curso_nao_ve(curso_com_equipe, coordenador, edicao, aluno):
    from apps.contas.models import Usuario

    outro_professor = Usuario.objects.create_user(
        email="outro.prof@ufsm.br", nome_completo="Elisa Esteves", cpf="111.444.777-35",
        papel=Usuario.PROFESSOR, siape="9999999", password="senha-de-teste-123",
    )
    assert permissions.pode_ver_curso(outro_professor, curso_com_equipe) is False


@pytest.mark.django_db
def test_coordenador_ve_tudo(curso_com_equipe, coordenador):
    assert permissions.pode_ver_curso(coordenador, curso_com_equipe)


@pytest.mark.django_db
def test_aluno_nao_revisa(curso_com_equipe, aluno):
    assert permissions.pode_revisar(aluno, curso_com_equipe) is False


@pytest.mark.django_db
def test_professor_responsavel_revisa(curso_com_equipe, professor):
    assert permissions.pode_revisar(professor, curso_com_equipe)


@pytest.mark.django_db
def test_aluno_de_fora_nao_envia_para_revisao(curso_com_equipe, outro_aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    with pytest.raises(PermissionDenied):
        services.enviar_para_revisao(slides, por=outro_aluno)


@pytest.mark.django_db
def test_aluno_nao_aprova_o_proprio_entregavel(curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    with pytest.raises(PermissionDenied):
        services.aprovar_entregavel(slides, por=aluno)


@pytest.mark.django_db
def test_aluno_nao_monta_equipe(curso_com_equipe, aluno, outro_aluno):
    with pytest.raises(PermissionDenied):
        services.adicionar_membro(curso_com_equipe, outro_aluno, por=aluno)


@pytest.mark.django_db
def test_entregavel_em_revisao_nao_e_editavel_nem_pelo_membro(curso_com_equipe, aluno, arquivo_qualquer):
    from apps.cursos.choices import TipoMidia
    from apps.cursos.models import Anexo

    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    assert permissions.pode_editar_producao(aluno, slides)
    services.enviar_para_revisao(slides, por=aluno)
    assert permissions.pode_editar_producao(aluno, slides) is False
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_permissions.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'apps.cursos.permissions'`.

- [ ] **Step 3: Implementar as permissões**

`apps/cursos/permissions.py`:

```python
from django.core.exceptions import PermissionDenied


def garante(condicao, mensagem):
    """Levanta PermissionDenied quando a condicao e falsa. Usado pelos servicos para
    que a checagem fique junto da regra, e nao espalhada em if de template (spec 10)."""
    if not condicao:
        raise PermissionDenied(mensagem)


def e_responsavel(usuario, curso):
    return curso.professor_responsavel_id == usuario.id


def pode_ver_curso(usuario, curso):
    if usuario.e_coordenador:
        return True
    if usuario.e_professor:
        return e_responsavel(usuario, curso)
    return curso.tem_membro(usuario)


def pode_gerir_equipe(usuario, curso):
    return usuario.e_coordenador or (usuario.e_professor and e_responsavel(usuario, curso))


def pode_revisar(usuario, curso):
    return pode_gerir_equipe(usuario, curso)


def pode_editar_producao(usuario, entregavel):
    """Aluno da equipe edita apenas enquanto o entregavel esta em rascunho ou
    devolvido; enviado para revisao, congela (spec 10)."""
    if not entregavel.editavel:
        return False
    return entregavel.curso.tem_membro(usuario)
```

- [ ] **Step 4: Amarrar as permissões aos serviços**

Em `apps/cursos/services.py`, importe `from apps.cursos import permissions` e acrescente a primeira linha de cada serviço:

```python
@transaction.atomic
def adicionar_membro(curso, aluno, por):
    permissions.garante(permissions.pode_gerir_equipe(por, curso), "Somente o professor responsavel monta a equipe.")
    ...


@transaction.atomic
def enviar_para_revisao(entregavel, por):
    permissions.garante(
        permissions.pode_editar_producao(por, entregavel) or permissions.pode_revisar(por, entregavel.curso),
        "Voce nao participa da equipe deste curso.",
    )
    ...


@transaction.atomic
def aprovar_entregavel(entregavel, por, comentario=""):
    permissions.garante(permissions.pode_revisar(por, entregavel.curso), "Somente o professor responsavel revisa.")
    ...


@transaction.atomic
def devolver_entregavel(entregavel, por, comentario):
    permissions.garante(permissions.pode_revisar(por, entregavel.curso), "Somente o professor responsavel revisa.")
    ...
```

A checagem de `enviar_para_revisao` precisa vir **antes** da checagem de `editavel`, senão um aluno de fora recebe "este entregável está em revisão" em vez de ser barrado - mensagem de erro que revela estado de curso alheio.

- [ ] **Step 5: Rodar a suíte inteira e commitar**

```bash
pytest -v
git add apps/cursos
git commit -m "feat(cursos): permissoes centralizadas e amarradas aos servicos"
```

Expected: PASS - inclusive os testes da Task 7, que passam `por=aluno` membro e `por=professor` responsável.

---

### Task 9: Telas do aluno

**Files:**
- Create: `apps/cursos/views/__init__.py`, `apps/cursos/views/aluno.py`, `apps/cursos/forms.py`, `apps/cursos/urls.py`, `templates/cursos/meus_cursos.html`, `templates/cursos/curso.html`, `templates/cursos/entregavel.html`, `templates/cursos/_secao.html`
- Modify: `config/urls.py`, `templates/painel.html`
- Test: `apps/cursos/tests/test_views_aluno.py`

**Interfaces:**
- Consumes: serviços e permissões (Tasks 4-8).
- Produces: rotas nomeadas `meus_cursos`, `curso` (`<int:pk>`), `entregavel` (`<int:pk>`), `salvar_secao` (`<int:pk>`), `anexar` (`<int:pk>`), `enviar_entregavel` (`<int:pk>`); `SecaoForm` e `AnexoForm`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_views_aluno.py`:

```python
import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo


@pytest.fixture
def curso_com_equipe(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso


@pytest.mark.django_db
def test_meus_cursos_lista_so_os_do_aluno(client, curso_com_equipe, aluno, outro_aluno):
    client.force_login(outro_aluno)
    resposta = client.get(reverse("meus_cursos"))
    assert curso_com_equipe.titulo not in resposta.content.decode()
    client.force_login(aluno)
    resposta = client.get(reverse("meus_cursos"))
    assert curso_com_equipe.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_curso_de_outra_equipe_devolve_403(client, curso_com_equipe, outro_aluno):
    client.force_login(outro_aluno)
    resposta = client.get(reverse("curso", args=[curso_com_equipe.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_painel_do_curso_mostra_os_cinco_entregaveis(client, curso_com_equipe, aluno):
    client.force_login(aluno)
    resposta = client.get(reverse("curso", args=[curso_com_equipe.pk]))
    conteudo = resposta.content.decode()
    assert conteudo.count("entregavel-card") == 5


@pytest.mark.django_db
def test_entregavel_mostra_o_que_falta(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.get(reverse("entregavel", args=[slides.pk]))
    assert "Anexe ao menos um arquivo de slides." in resposta.content.decode()


@pytest.mark.django_db
def test_salvar_secao_guarda_o_conteudo_e_o_autor(client, curso_com_equipe, aluno):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    client.force_login(aluno)
    resposta = client.post(reverse("salvar_secao", args=[secao.pk]), {"conteudo": "<p>Ementa nova</p>"})
    assert resposta.status_code == 200
    secao.refresh_from_db()
    assert "Ementa nova" in secao.conteudo
    assert secao.atualizado_por == aluno


@pytest.mark.django_db
def test_salvar_secao_de_entregavel_em_revisao_e_bloqueado(client, curso_com_equipe, aluno, arquivo_qualquer):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()
    Anexo.objects.create(
        entregavel=plano, tipo_midia=TipoMidia.ARQUIVO, titulo="Plano",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    services.enviar_para_revisao(plano, por=aluno)
    client.force_login(aluno)
    resposta = client.post(reverse("salvar_secao", args=[secao.pk]), {"conteudo": "<p>Mudanca</p>"})
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_enviar_para_revisao_pela_tela(client, curso_com_equipe, aluno, arquivo_qualquer):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    client.force_login(aluno)
    resposta = client.post(reverse("enviar_entregavel", args=[slides.pk]), follow=True)
    assert resposta.status_code == 200
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.EM_REVISAO


@pytest.mark.django_db
def test_enviar_com_pendencia_mostra_a_lista(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.post(reverse("enviar_entregavel", args=[slides.pk]), follow=True)
    assert "Anexe ao menos um arquivo de slides." in resposta.content.decode()
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.RASCUNHO
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_views_aluno.py -v`
Expected: FAIL - `NoReverseMatch: Reverse for 'meus_cursos' not found`.

- [ ] **Step 3: Escrever os formulários**

`apps/cursos/forms.py`:

```python
from django import forms

from apps.cursos.arquivos import valida_upload
from apps.cursos.models import Anexo, Secao


class SecaoForm(forms.ModelForm):
    class Meta:
        model = Secao
        fields = ["conteudo"]
        widgets = {"conteudo": forms.Textarea(attrs={"rows": 12})}


class AnexoForm(forms.ModelForm):
    upload = forms.FileField(label="arquivo", required=False)

    class Meta:
        model = Anexo
        fields = ["titulo", "descricao", "referencia_bibliografica", "rotulo", "tipo_pratica", "url"]

    def clean(self):
        dados = super().clean()
        upload = dados.get("upload")
        if upload:
            cabecalho = upload.read(16)
            upload.seek(0)
            dados["mime"] = valida_upload(upload.name, upload.size, cabecalho)
        elif not dados.get("url"):
            raise forms.ValidationError("Envie um arquivo ou informe um link.")
        return dados
```

- [ ] **Step 4: Escrever as views do aluno**

`apps/cursos/views/__init__.py`:

```python
from apps.cursos.views.aluno import (
    anexar,
    curso,
    entregavel,
    enviar_entregavel,
    meus_cursos,
    salvar_secao,
)

__all__ = ["anexar", "curso", "entregavel", "enviar_entregavel", "meus_cursos", "salvar_secao"]
```

`apps/cursos/views/aluno.py`:

```python
import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.cursos import permissions, services, validacoes
from apps.cursos.choices import TipoMidia
from apps.cursos.forms import AnexoForm, SecaoForm
from apps.cursos.models import Anexo, Arquivo, Curso, Entregavel, Secao


@login_required
def meus_cursos(request):
    cursos = Curso.objects.filter(
        Q(membros__aluno=request.user) | Q(professor_responsavel=request.user)
    ).distinct()
    return render(request, "cursos/meus_cursos.html", {"cursos": cursos})


@login_required
def curso(request, pk):
    obj = get_object_or_404(Curso, pk=pk)
    permissions.garante(permissions.pode_ver_curso(request.user, obj), "Curso de outra equipe.")
    entregaveis = obj.entregaveis.all()
    return render(request, "cursos/curso.html", {"curso": obj, "entregaveis": entregaveis})


@login_required
def entregavel(request, pk):
    obj = get_object_or_404(Entregavel, pk=pk)
    permissions.garante(permissions.pode_ver_curso(request.user, obj.curso), "Curso de outra equipe.")
    return render(
        request,
        "cursos/entregavel.html",
        {
            "entregavel": obj,
            "pendencias": validacoes.pendencias(obj),
            "form_anexo": AnexoForm(),
            "pode_editar": permissions.pode_editar_producao(request.user, obj),
            "ultima_revisao": obj.revisoes.last(),
        },
    )


@login_required
def salvar_secao(request, pk):
    secao = get_object_or_404(Secao, pk=pk)
    permissions.garante(
        permissions.pode_editar_producao(request.user, secao.entregavel),
        "Este entregavel nao esta aberto para edicao.",
    )
    form = SecaoForm(request.POST, instance=secao)
    if not form.is_valid():
        return render(request, "cursos/_secao.html", {"secao": secao, "erro": "Nao foi possivel salvar."})
    secao = form.save(commit=False)
    secao.atualizado_por = request.user
    secao.save()
    return render(request, "cursos/_secao.html", {"secao": secao, "salvo": True})


@login_required
def anexar(request, pk):
    obj = get_object_or_404(Entregavel, pk=pk)
    permissions.garante(
        permissions.pode_editar_producao(request.user, obj), "Este entregavel nao esta aberto para edicao."
    )
    form = AnexoForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "; ".join(m for lista in form.errors.values() for m in lista))
        return redirect("entregavel", pk=obj.pk)

    upload = form.cleaned_data.get("upload")
    anexo = form.save(commit=False)
    anexo.entregavel = obj
    anexo.enviado_por = request.user
    if upload:
        conteudo = upload.read()
        upload.seek(0)
        arquivo = Arquivo(
            nome_original=upload.name,
            tamanho=upload.size,
            mime=form.cleaned_data["mime"],
            hash_conteudo=hashlib.sha256(conteudo).hexdigest(),
            enviado_por=request.user,
        )
        arquivo.arquivo.save(upload.name, upload, save=False)
        arquivo.save()
        anexo.arquivo = arquivo
        anexo.tipo_midia = TipoMidia.ARQUIVO
    else:
        anexo.tipo_midia = TipoMidia.LINK
    anexo.save()
    messages.success(request, "Material anexado.")
    return redirect("entregavel", pk=obj.pk)


@login_required
def enviar_entregavel(request, pk):
    obj = get_object_or_404(Entregavel, pk=pk)
    try:
        services.enviar_para_revisao(obj, por=request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, "Entregavel enviado para revisao do professor.")
    return redirect("entregavel", pk=obj.pk)
```

- [ ] **Step 5: Escrever as rotas**

`apps/cursos/urls.py`:

```python
from django.urls import path

from apps.cursos import views

urlpatterns = [
    path("cursos/", views.meus_cursos, name="meus_cursos"),
    path("cursos/<int:pk>/", views.curso, name="curso"),
    path("entregaveis/<int:pk>/", views.entregavel, name="entregavel"),
    path("entregaveis/<int:pk>/anexar/", views.anexar, name="anexar"),
    path("entregaveis/<int:pk>/enviar/", views.enviar_entregavel, name="enviar_entregavel"),
    path("secoes/<int:pk>/salvar/", views.salvar_secao, name="salvar_secao"),
]
```

Em `config/urls.py`, antes do `include("apps.contas.urls")`:

```python
    path("", include("apps.cursos.urls")),
```

- [ ] **Step 6: Escrever os templates**

`templates/cursos/meus_cursos.html`:

```html
{% extends "base.html" %}
{% block titulo %}Meus cursos{% endblock %}
{% block conteudo %}
  <h1>Meus cursos</h1>
  {% for curso in cursos %}
    <article>
      <h2><a href="{% url 'curso' curso.pk %}">{{ curso.titulo }}</a></h2>
      <p>{{ curso.publico_alvo }} &middot; {{ curso.carga_horaria }}h &middot; {{ curso.get_status_display }}</p>
    </article>
  {% empty %}
    <p>Voce ainda nao participa de nenhum curso.</p>
  {% endfor %}
{% endblock %}
```

`templates/cursos/curso.html`:

```html
{% extends "base.html" %}
{% block titulo %}{{ curso.titulo }}{% endblock %}
{% block conteudo %}
  <h1>{{ curso.titulo }}</h1>
  <p>{{ curso.publico_alvo }} &middot; {{ curso.carga_horaria }}h &middot; {{ curso.get_formato_display }}</p>
  <p>Situacao: {{ curso.get_status_display }}</p>

  <h2>Entregaveis</h2>
  {% for entregavel in entregaveis %}
    <article class="entregavel-card">
      <h3><a href="{% url 'entregavel' entregavel.pk %}">{{ entregavel.get_tipo_display }}</a></h3>
      <p>{{ entregavel.get_status_display }}</p>
    </article>
  {% endfor %}

  <h2>Equipe</h2>
  <ul>
    {% for membro in curso.membros.all %}<li>{{ membro.aluno.nome_completo }}</li>{% endfor %}
  </ul>
{% endblock %}
```

`templates/cursos/entregavel.html`:

```html
{% extends "base.html" %}
{% block titulo %}{{ entregavel.get_tipo_display }}{% endblock %}
{% block conteudo %}
  <h1>{{ entregavel.get_tipo_display }}</h1>
  <p><a href="{% url 'curso' entregavel.curso.pk %}">{{ entregavel.curso.titulo }}</a></p>
  <p>Situacao: {{ entregavel.get_status_display }}</p>

  {% for mensagem in messages %}<p class="mensagem">{{ mensagem }}</p>{% endfor %}

  {% if ultima_revisao and ultima_revisao.decisao == "DEVOLVIDO" %}
    <section class="devolutiva">
      <h2>Devolvido pelo professor</h2>
      <p>{{ ultima_revisao.comentario }}</p>
    </section>
  {% endif %}

  {% if pendencias %}
    <section class="pendencias">
      <h2>O que falta</h2>
      <ul>{% for falta in pendencias %}<li>{{ falta }}</li>{% endfor %}</ul>
    </section>
  {% endif %}

  {% for secao in entregavel.secoes.all %}
    {% include "cursos/_secao.html" %}
  {% endfor %}

  <h2>Materiais</h2>
  <ul>
    {% for anexo in entregavel.anexos.all %}
      <li>{{ anexo.titulo }} ({{ anexo.get_tipo_midia_display }})</li>
    {% empty %}
      <li>Nenhum material anexado.</li>
    {% endfor %}
  </ul>

  {% if pode_editar %}
    <form method="post" action="{% url 'anexar' entregavel.pk %}" enctype="multipart/form-data">
      {% csrf_token %}
      {{ form_anexo.as_p }}
      <button type="submit">Anexar</button>
    </form>

    <form method="post" action="{% url 'enviar_entregavel' entregavel.pk %}">
      {% csrf_token %}
      <button type="submit">Enviar para revisao</button>
    </form>
  {% endif %}
{% endblock %}
```

`templates/cursos/_secao.html`:

```html
<section id="secao-{{ secao.pk }}">
  <h3>{{ secao.titulo }}</h3>
  {% if salvo %}<p class="mensagem">Salvo.</p>{% endif %}
  {% if erro %}<p class="mensagem">{{ erro }}</p>{% endif %}
  <form hx-post="{% url 'salvar_secao' secao.pk %}" hx-target="#secao-{{ secao.pk }}" hx-swap="outerHTML">
    {% csrf_token %}
    <textarea name="conteudo" rows="10">{{ secao.conteudo }}</textarea>
    <button type="submit">Salvar secao</button>
  </form>
</section>
```

Acrescente o HTMX ao `<head>` de `templates/base.html`, baixando o arquivo para `static/` em vez de usar CDN (o servidor da universidade pode não ter saída para a internet):

```bash
mkdir -p static/js
curl -o static/js/htmx.min.js https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js
```

```html
  {% load static %}
  <script src="{% static 'js/htmx.min.js' %}" defer></script>
```

E em `templates/painel.html`, dentro do bloco de conteúdo:

```html
  <p><a href="{% url 'meus_cursos' %}">Meus cursos</a></p>
```

- [ ] **Step 7: Rodar e commitar**

```bash
python manage.py collectstatic --noinput
pytest apps/cursos/tests/test_views_aluno.py -v
git add apps/cursos templates static config/urls.py
git commit -m "feat(cursos): telas do aluno para produzir e enviar entregaveis"
```

Expected: PASS (8 testes).

---

### Task 10: Telas do professor

**Files:**
- Create: `apps/cursos/views/professor.py`, `templates/cursos/nova_proposta.html`, `templates/cursos/equipe.html`, `templates/cursos/fila_revisao.html`, `templates/cursos/revisar.html`
- Modify: `apps/cursos/views/__init__.py`, `apps/cursos/urls.py`, `apps/cursos/forms.py`, `templates/painel.html`
- Test: `apps/cursos/tests/test_views_professor.py`

**Interfaces:**
- Consumes: serviços, permissões e validações (Tasks 4-8).
- Produces: rotas `nova_proposta`, `equipe` (`<int:pk>`), `fila_revisao`, `revisar` (`<int:pk>`), `decidir` (`<int:pk>`); `CursoForm`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_views_professor.py`:

```python
import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia, TipoPublico
from apps.cursos.models import Anexo, Curso


@pytest.fixture
def slides_em_revisao(dados_curso, aluno, arquivo_qualquer):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    services.enviar_para_revisao(slides, por=aluno)
    return slides


@pytest.mark.django_db
def test_professor_cria_proposta(client, professor, edicao):
    client.force_login(professor)
    resposta = client.post(
        reverse("nova_proposta"),
        {
            "titulo": "Robotica com sucata",
            "resumo": "Oficina de robotica de baixo custo.",
            "edicao": edicao.pk,
            "tipo_publico": TipoPublico.ESCOLAR,
            "etapa_ano": "EF09",
            "publico_descricao": "",
            "carga_horaria": 8,
            "formato": "PRESENCIAL",
            "palavras_chave": "robotica, sucata",
        },
        follow=True,
    )
    assert resposta.status_code == 200
    curso = Curso.objects.get(titulo="Robotica com sucata")
    assert curso.professor_responsavel == professor
    assert curso.entregaveis.count() == 5


@pytest.mark.django_db
def test_aluno_nao_cria_proposta(client, aluno):
    client.force_login(aluno)
    resposta = client.get(reverse("nova_proposta"))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_professor_monta_equipe(client, professor, dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.post(reverse("equipe", args=[curso.pk]), {"aluno": aluno.pk}, follow=True)
    assert resposta.status_code == 200
    assert curso.tem_membro(aluno)


@pytest.mark.django_db
def test_fila_mostra_o_que_espera_por_mim(client, professor, slides_em_revisao):
    client.force_login(professor)
    resposta = client.get(reverse("fila_revisao"))
    assert slides_em_revisao.curso.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_fila_de_outro_professor_esta_vazia(client, slides_em_revisao, db):
    from apps.contas.models import Usuario

    outro = Usuario.objects.create_user(
        email="outro.prof@ufsm.br", nome_completo="Elisa Esteves", cpf="111.444.777-35",
        papel=Usuario.PROFESSOR, siape="9999999", password="senha-de-teste-123",
    )
    client.force_login(outro)
    resposta = client.get(reverse("fila_revisao"))
    assert slides_em_revisao.curso.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_aprovar_pela_tela(client, professor, slides_em_revisao):
    client.force_login(professor)
    client.post(reverse("decidir", args=[slides_em_revisao.pk]), {"decisao": "APROVAR", "comentario": ""})
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.APROVADO


@pytest.mark.django_db
def test_devolver_sem_comentario_e_barrado_na_tela(client, professor, slides_em_revisao):
    client.force_login(professor)
    resposta = client.post(
        reverse("decidir", args=[slides_em_revisao.pk]),
        {"decisao": "DEVOLVER", "comentario": "  "},
        follow=True,
    )
    assert "Escreva o que precisa ser corrigido" in resposta.content.decode()
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.EM_REVISAO


@pytest.mark.django_db
def test_aluno_nao_decide(client, aluno, slides_em_revisao):
    client.force_login(aluno)
    resposta = client.post(reverse("decidir", args=[slides_em_revisao.pk]), {"decisao": "APROVAR"})
    assert resposta.status_code == 403
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_views_professor.py -v`
Expected: FAIL - `NoReverseMatch: Reverse for 'nova_proposta' not found`.

- [ ] **Step 3: Escrever o formulário do curso**

Acrescente a `apps/cursos/forms.py`:

```python
from apps.cursos.models import Curso


class CursoForm(forms.ModelForm):
    class Meta:
        model = Curso
        fields = [
            "titulo", "resumo", "edicao", "tipo_publico", "etapa_ano", "publico_descricao",
            "referencial", "carga_horaria", "formato", "pre_requisitos", "temas", "palavras_chave",
        ]
        widgets = {"resumo": forms.Textarea(attrs={"rows": 4})}
```

As competências ficam fora do formulário de criação: elas dependem do referencial escolhido e são editadas na tela do curso, depois que ele existe. Tentar resolver isso no mesmo formulário exigiria campo dependente em JavaScript, e a validação da faixa já acontece no envio do Plano de Ensino.

- [ ] **Step 4: Escrever as views do professor**

`apps/cursos/views/professor.py`:

```python
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.contas.models import Usuario
from apps.cursos import permissions, services, validacoes
from apps.cursos.choices import StatusEntregavel
from apps.cursos.forms import CursoForm
from apps.cursos.models import Curso, Entregavel


@login_required
def nova_proposta(request):
    permissions.garante(
        request.user.e_professor or request.user.e_coordenador,
        "Somente professor cria proposta de curso.",
    )
    form = CursoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dados = dict(form.cleaned_data)
        temas = dados.pop("temas", [])
        curso = services.criar_curso(professor_responsavel=request.user, **dados)
        curso.temas.set(temas)
        messages.success(request, "Proposta criada. Monte a equipe para comecar a producao.")
        return redirect("equipe", pk=curso.pk)
    return render(request, "cursos/nova_proposta.html", {"form": form})


@login_required
def equipe(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(permissions.pode_gerir_equipe(request.user, curso), "Curso de outro professor.")
    if request.method == "POST":
        aluno = get_object_or_404(Usuario, pk=request.POST["aluno"])
        try:
            services.adicionar_membro(curso, aluno, por=request.user)
        except ValidationError as erro:
            messages.error(request, erro.messages[0])
        else:
            messages.success(request, f"{aluno.nome_completo} entrou na equipe.")
        return redirect("equipe", pk=curso.pk)
    candidatos = Usuario.objects.filter(papel=Usuario.ALUNO, is_active=True).exclude(
        equipes__curso=curso
    )
    return render(request, "cursos/equipe.html", {"curso": curso, "candidatos": candidatos})


@login_required
def fila_revisao(request):
    entregaveis = Entregavel.objects.filter(
        status=StatusEntregavel.EM_REVISAO, curso__professor_responsavel=request.user
    ).select_related("curso")
    return render(request, "cursos/fila_revisao.html", {"entregaveis": entregaveis})


@login_required
def revisar(request, pk):
    entregavel = get_object_or_404(Entregavel, pk=pk)
    permissions.garante(permissions.pode_revisar(request.user, entregavel.curso), "Curso de outro professor.")
    return render(
        request,
        "cursos/revisar.html",
        {"entregavel": entregavel, "pendencias": validacoes.pendencias(entregavel)},
    )


@login_required
def decidir(request, pk):
    entregavel = get_object_or_404(Entregavel, pk=pk)
    comentario = request.POST.get("comentario", "")
    try:
        if request.POST.get("decisao") == "APROVAR":
            services.aprovar_entregavel(entregavel, por=request.user, comentario=comentario)
            messages.success(request, "Entregavel aprovado.")
        else:
            services.devolver_entregavel(entregavel, por=request.user, comentario=comentario)
            messages.success(request, "Entregavel devolvido a equipe.")
    except ValidationError as erro:
        messages.error(request, erro.messages[0])
        return redirect("revisar", pk=entregavel.pk)
    return redirect("fila_revisao")
```

Atualize `apps/cursos/views/__init__.py`:

```python
from apps.cursos.views.aluno import (
    anexar,
    curso,
    entregavel,
    enviar_entregavel,
    meus_cursos,
    salvar_secao,
)
from apps.cursos.views.professor import decidir, equipe, fila_revisao, nova_proposta, revisar

__all__ = [
    "anexar", "curso", "decidir", "entregavel", "enviar_entregavel", "equipe",
    "fila_revisao", "meus_cursos", "nova_proposta", "revisar", "salvar_secao",
]
```

E `apps/cursos/urls.py`, acrescentando:

```python
    path("propostas/nova/", views.nova_proposta, name="nova_proposta"),
    path("cursos/<int:pk>/equipe/", views.equipe, name="equipe"),
    path("revisao/", views.fila_revisao, name="fila_revisao"),
    path("revisao/<int:pk>/", views.revisar, name="revisar"),
    path("revisao/<int:pk>/decidir/", views.decidir, name="decidir"),
```

- [ ] **Step 5: Escrever os templates**

`templates/cursos/nova_proposta.html`:

```html
{% extends "base.html" %}
{% block titulo %}Nova proposta{% endblock %}
{% block conteudo %}
  <h1>Nova proposta de curso</h1>
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Criar proposta</button>
  </form>
{% endblock %}
```

`templates/cursos/equipe.html`:

```html
{% extends "base.html" %}
{% block titulo %}Equipe - {{ curso.titulo }}{% endblock %}
{% block conteudo %}
  <h1>Equipe de {{ curso.titulo }}</h1>
  {% for mensagem in messages %}<p class="mensagem">{{ mensagem }}</p>{% endfor %}
  <ul>
    {% for membro in curso.membros.all %}<li>{{ membro.aluno.nome_completo }}</li>{% empty %}<li>Equipe vazia.</li>{% endfor %}
  </ul>
  <form method="post">
    {% csrf_token %}
    <select name="aluno">
      {% for candidato in candidatos %}<option value="{{ candidato.pk }}">{{ candidato.nome_completo }}</option>{% endfor %}
    </select>
    <button type="submit">Adicionar a equipe</button>
  </form>
  <p><a href="{% url 'curso' curso.pk %}">Ver o curso</a></p>
{% endblock %}
```

`templates/cursos/fila_revisao.html`:

```html
{% extends "base.html" %}
{% block titulo %}Revisao{% endblock %}
{% block conteudo %}
  <h1>Esperando por voce</h1>
  {% for entregavel in entregaveis %}
    <article>
      <h2><a href="{% url 'revisar' entregavel.pk %}">{{ entregavel.get_tipo_display }}</a></h2>
      <p>{{ entregavel.curso.titulo }} &middot; enviado em {{ entregavel.atualizado_em }}</p>
    </article>
  {% empty %}
    <p>Nada aguardando revisao.</p>
  {% endfor %}
{% endblock %}
```

`templates/cursos/revisar.html`:

```html
{% extends "base.html" %}
{% block titulo %}Revisar{% endblock %}
{% block conteudo %}
  <h1>{{ entregavel.get_tipo_display }}</h1>
  <p>{{ entregavel.curso.titulo }}</p>
  {% for mensagem in messages %}<p class="mensagem">{{ mensagem }}</p>{% endfor %}

  {% for secao in entregavel.secoes.all %}
    <section><h3>{{ secao.titulo }}</h3><div>{{ secao.conteudo|safe }}</div></section>
  {% endfor %}

  <h2>Materiais</h2>
  <ul>
    {% for anexo in entregavel.anexos.all %}
      <li>{{ anexo.titulo }}{% if anexo.referencia_bibliografica %} - {{ anexo.referencia_bibliografica }}{% endif %}</li>
    {% endfor %}
  </ul>

  <form method="post" action="{% url 'decidir' entregavel.pk %}">
    {% csrf_token %}
    <label for="comentario">Comentario</label>
    <textarea id="comentario" name="comentario" rows="5"></textarea>
    <button type="submit" name="decisao" value="APROVAR">Aprovar</button>
    <button type="submit" name="decisao" value="DEVOLVER">Devolver</button>
  </form>
{% endblock %}
```

O `|safe` no conteúdo da seção é seguro porque `Secao.save()` sanitiza com nh3 antes de gravar (Task 4) - é o único lugar do sistema onde HTML do banco é renderizado sem escape, e depende dessa sanitização.

Acrescente a `templates/painel.html`:

```html
  {% if user.e_professor or user.e_coordenador %}
    <p><a href="{% url 'nova_proposta' %}">Nova proposta</a> &middot; <a href="{% url 'fila_revisao' %}">Revisao</a></p>
  {% endif %}
```

- [ ] **Step 6: Rodar a suíte inteira**

Run: `pytest -v`
Expected: PASS - todos os testes dos Planos 1 e 2.

- [ ] **Step 7: Conferir o fluxo inteiro na mão**

```bash
python manage.py migrate
python manage.py runserver
```

Como coordenador, cadastre um professor e dois alunos no Admin. Entre como o professor, crie uma proposta, monte a equipe. Entre como aluno, preencha uma seção, anexe um PDF, tente enviar o Plano de Ensino e confira a lista do que falta. Complete e envie. Volte como professor, devolva com comentário, e veja a devolutiva aparecer para o aluno.

- [ ] **Step 8: Commitar**

```bash
git add apps/cursos templates
git commit -m "feat(cursos): telas do professor para propor, montar equipe e revisar"
```

---

## Entregue ao fim deste plano

O ciclo de produção funciona de ponta a ponta: professor propõe, equipe produz, professor aprova ou devolve, e o curso chega ao estado de ter os cinco entregáveis aprovados. Falta o que vem depois (submeter ao coordenador, publicar, catalogar e receber demanda) que é o **Plano 3**.
