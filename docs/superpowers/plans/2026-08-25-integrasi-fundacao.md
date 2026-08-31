# IntegraSI - Plano 1: Fundação e Cadastros

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Colocar de pé o projeto Django do IntegraSI com autenticação por papéis e todos os cadastros de apoio (edições da disciplina, referenciais pedagógicos e temas), de modo que o coordenador consiga entrar no sistema e cadastrar tudo que um curso vai precisar referenciar.

**Architecture:** Django monolítico, PostgreSQL, templates renderizados no servidor. Apps pequenos e de mão única sob `apps/`. Modelo de usuário próprio desde a primeira migração, com papel e documentos de identificação validados e normalizados no próprio modelo. Cadastros de apoio administrados pelo Django Admin - nenhuma tela de CRUD escrita à mão nesta etapa.

**Tech Stack:** Python 3.12, Django 5.x, PostgreSQL 16, pytest + pytest-django, python-dotenv, dj-database-url.

**Spec:** `docs/superpowers/specs/2026-08-25-integrasi-design.md`

## Global Constraints

- Módulo de produção apenas. Nenhum campo de frequência, nota ou certificado (spec §1.1).
- Dependência entre apps é de mão única: `turmas` lê `cursos`; `cursos` e `catalogo` não conhecem `turmas`.
- Só `services.py` altera campo de status. Nenhum sinal `post_save` para lógica de domínio (spec §7.2).
- `DEBUG` desligado por padrão; toda configuração vem de variável de ambiente.
- CPF, matrícula e SIAPE armazenados **somente com dígitos**; CPF com dígitos verificadores conferidos (spec §4.1).
- CPF nunca aparece fora do Django Admin, e mascarado nas listagens (spec §10).
- Nenhuma tela, filtro ou relatório pode pressupor BNCC - cursos sem referencial são de primeira classe (spec §4.2).
- Textos de interface e nomes de campos em português.

---

### Task 1: Esqueleto do projeto e configuração por ambiente

**Files:**
- Create: `pyproject.toml`, `.env.example`, `.gitignore`, `config/settings.py`, `config/urls.py`, `manage.py`, `apps/__init__.py`
- Test: `tests/test_configuracao.py`

**Interfaces:**
- Consumes: nada (primeira tarefa).
- Produces: pacote `config` com `settings.py` lendo `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` e `DATABASE_URL` do ambiente; pacote `apps/` onde todos os apps posteriores serão criados; `pytest` configurado com `DJANGO_SETTINGS_MODULE=config.settings`.

- [ ] **Step 1: Criar ambiente e instalar dependências**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install "django>=5.0,<6.0" "psycopg[binary]" python-dotenv dj-database-url pytest pytest-django
```

- [ ] **Step 2: Gerar o projeto e o pacote de apps**

```bash
django-admin startproject config .
mkdir -p apps tests
touch apps/__init__.py tests/__init__.py
```

- [ ] **Step 3: Subir um PostgreSQL local para desenvolvimento e testes**

```bash
docker run -d --name integrasi-db -e POSTGRES_PASSWORD=integrasi \
  -e POSTGRES_USER=integrasi -e POSTGRES_DB=integrasi -p 5432:5432 postgres:16
```

Se já houver PostgreSQL na máquina, use-o e apenas ajuste a `DATABASE_URL` no passo seguinte. O usuário do banco precisa de permissão para criar bancos, porque o pytest cria um banco de teste separado.

- [ ] **Step 4: Escrever `.env.example` e `.env`**

```bash
cat > .env.example <<'EOF'
SECRET_KEY=troque-esta-chave
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://integrasi:integrasi@localhost:5432/integrasi
EOF
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Cole a chave gerada em `SECRET_KEY` no `.env` (o `.env.example` fica com o valor de exemplo).

- [ ] **Step 5: Escrever o teste de configuração (vai falhar)**

`tests/test_configuracao.py`:

```python
from django.conf import settings


def test_debug_desligado_por_padrao():
    assert settings.DEBUG is False


def test_banco_e_postgresql():
    assert "postgresql" in settings.DATABASES["default"]["ENGINE"]


def test_idioma_e_fuso_do_projeto():
    assert settings.LANGUAGE_CODE == "pt-br"
    assert settings.TIME_ZONE == "America/Sao_Paulo"
    assert settings.USE_TZ is True
```

- [ ] **Step 6: Configurar o pytest e rodar o teste para vê-lo falhar**

Acrescente ao `pyproject.toml` (crie o arquivo se não existir):

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
python_files = ["test_*.py"]
addopts = "-q"
```

Run: `pytest tests/test_configuracao.py -v`
Expected: FAIL - `assert 'pt-br' == 'en-us'` e o engine ainda é `sqlite3`.

- [ ] **Step 7: Reescrever `config/settings.py`**

```python
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"])}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

- [ ] **Step 8: Rodar os testes e ver passar**

Run: `pytest tests/test_configuracao.py -v`
Expected: PASS (3 testes).

- [ ] **Step 9: Escrever o `.gitignore` e commitar**

```bash
cat > .gitignore <<'EOF'
.venv/
__pycache__/
*.pyc
.env
media/
staticfiles/
.pytest_cache/
EOF
git add pyproject.toml .env.example .gitignore config manage.py apps tests
git commit -m "chore: esqueleto do projeto Django com configuracao por ambiente"
```

---

### Task 2: Normalização e validação de documentos

**Files:**
- Create: `apps/contas/__init__.py`, `apps/contas/validators.py`
- Test: `apps/contas/tests/__init__.py`, `apps/contas/tests/test_validators.py`

**Interfaces:**
- Consumes: nada.
- Produces: `somente_digitos(valor: str | None) -> str` e `valida_cpf(valor: str) -> None` (levanta `django.core.exceptions.ValidationError`). Ambos usados pelo modelo `Usuario` na Task 3.

- [ ] **Step 1: Criar o app e escrever o teste (vai falhar)**

```bash
mkdir -p apps/contas/tests
touch apps/contas/__init__.py apps/contas/tests/__init__.py
```

`apps/contas/tests/test_validators.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.contas.validators import somente_digitos, valida_cpf


def test_somente_digitos_remove_pontuacao():
    assert somente_digitos("529.982.247-25") == "52998224725"


def test_somente_digitos_aceita_vazio_e_none():
    assert somente_digitos("") == ""
    assert somente_digitos(None) == ""


@pytest.mark.parametrize("cpf", ["52998224725", "529.982.247-25", "12345678909", "98765432100"])
def test_cpf_valido_nao_levanta(cpf):
    valida_cpf(cpf)


@pytest.mark.parametrize(
    "cpf",
    [
        "52998224724",   # digito verificador errado
        "11111111111",   # todos os digitos iguais
        "1234567890",    # curto demais
        "123456789012",  # longo demais
        "abcdefghijk",   # sem digito nenhum
    ],
)
def test_cpf_invalido_levanta(cpf):
    with pytest.raises(ValidationError):
        valida_cpf(cpf)
```

- [ ] **Step 2: Rodar o teste para vê-lo falhar**

Run: `pytest apps/contas/tests/test_validators.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'apps.contas.validators'`.

- [ ] **Step 3: Implementar os validadores**

`apps/contas/validators.py`:

```python
import re

from django.core.exceptions import ValidationError

_NAO_DIGITO = re.compile(r"\D")


def somente_digitos(valor):
    """Devolve apenas os digitos de `valor`. Aceita None e string vazia."""
    return _NAO_DIGITO.sub("", valor or "")


def valida_cpf(valor):
    """Confere os dois digitos verificadores do CPF. Aceita o numero formatado."""
    cpf = somente_digitos(valor)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        raise ValidationError("CPF invalido.", code="cpf_invalido")
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            raise ValidationError("CPF invalido.", code="cpf_invalido")
```

- [ ] **Step 4: Rodar os testes e ver passar**

Run: `pytest apps/contas/tests/test_validators.py -v`
Expected: PASS (9 testes, contando as parametrizações).

- [ ] **Step 5: Commitar**

```bash
git add apps/contas
git commit -m "feat(contas): normalizacao de documentos e validacao de CPF"
```

---

### Task 3: Modelo de usuário com papéis e documentos

**Files:**
- Create: `apps/contas/models.py`, `apps/contas/apps.py`, `apps/contas/migrations/__init__.py`
- Modify: `config/settings.py` (INSTALLED_APPS, AUTH_USER_MODEL)
- Test: `apps/contas/tests/test_models.py`

**Interfaces:**
- Consumes: `somente_digitos`, `valida_cpf` (Task 2).
- Produces: `apps.contas.models.Usuario` com campos `nome_completo`, `email`, `cpf`, `papel`, `matricula`, `siape`, `is_active`, `is_staff`; constantes `Usuario.COORDENADOR`, `Usuario.PROFESSOR`, `Usuario.ALUNO`; propriedades `e_coordenador`, `e_professor`, `e_aluno`; manager com `create_user(email, nome_completo, cpf, papel, password=None, **extra)` e `create_superuser(...)`. `AUTH_USER_MODEL = "contas.Usuario"`.

- [ ] **Step 1: Gerar o app e registrá-lo**

```bash
mkdir -p apps/contas
python manage.py startapp contas apps/contas
```

Em `apps/contas/apps.py`, troque `name = "contas"` por `name = "apps.contas"`.

Em `config/settings.py`, acrescente ao fim de `INSTALLED_APPS`:

```python
    "apps.contas",
```

e depois de `AUTH_PASSWORD_VALIDATORS`:

```python
AUTH_USER_MODEL = "contas.Usuario"
```

- [ ] **Step 2: Escrever o teste do modelo (vai falhar)**

`apps/contas/tests/test_models.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.contas.models import Usuario

CPF_A = "529.982.247-25"
CPF_B = "123.456.789-09"


def criar_aluno(**kwargs):
    dados = {
        "email": "aluno@ufsm.br",
        "nome_completo": "Ana Alves",
        "cpf": CPF_A,
        "papel": Usuario.ALUNO,
        "matricula": "201910101",
    }
    dados.update(kwargs)
    return Usuario.objects.create_user(**dados)


def criar_professor(**kwargs):
    dados = {
        "email": "prof@ufsm.br",
        "nome_completo": "Bruno Barros",
        "cpf": CPF_B,
        "papel": Usuario.PROFESSOR,
        "siape": "1234567",
    }
    dados.update(kwargs)
    return Usuario.objects.create_user(**dados)


@pytest.mark.django_db
def test_documentos_sao_gravados_somente_com_digitos():
    aluno = criar_aluno(matricula="2019.10101")
    aluno.refresh_from_db()
    assert aluno.cpf == "52998224725"
    assert aluno.matricula == "201910101"


@pytest.mark.django_db
def test_cpf_invalido_e_recusado():
    with pytest.raises(ValidationError):
        criar_aluno(cpf="529.982.247-24")


@pytest.mark.django_db
def test_aluno_sem_matricula_e_recusado():
    with pytest.raises(ValidationError):
        criar_aluno(matricula="")


@pytest.mark.django_db
def test_professor_sem_siape_e_recusado():
    with pytest.raises(ValidationError):
        criar_professor(siape="")


@pytest.mark.django_db
def test_aluno_nao_pode_ter_siape():
    with pytest.raises(ValidationError):
        criar_aluno(siape="1234567")


@pytest.mark.django_db
def test_professor_nao_pode_ter_matricula():
    with pytest.raises(ValidationError):
        criar_professor(matricula="201910101")


@pytest.mark.django_db
def test_mesmo_cpf_escrito_de_duas_formas_colide():
    criar_aluno()
    with pytest.raises(ValidationError):
        criar_professor(cpf="52998224725")


@pytest.mark.django_db
def test_email_duplicado_e_recusado():
    criar_aluno()
    with pytest.raises(ValidationError):
        criar_professor(email="aluno@ufsm.br")


@pytest.mark.django_db
def test_propriedades_de_papel():
    aluno = criar_aluno()
    professor = criar_professor()
    assert aluno.e_aluno and not aluno.e_professor and not aluno.e_coordenador
    assert professor.e_professor and not professor.e_aluno


@pytest.mark.django_db
def test_str_mostra_nome_e_nunca_o_cpf():
    aluno = criar_aluno()
    assert str(aluno) == "Ana Alves"
    assert "529" not in str(aluno)
```

- [ ] **Step 3: Rodar o teste para vê-lo falhar**

Run: `pytest apps/contas/tests/test_models.py -v`
Expected: FAIL - `ImportError: cannot import name 'Usuario' from 'apps.contas.models'`.

- [ ] **Step 4: Implementar o modelo**

`apps/contas/models.py`:

```python
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models

from apps.contas.validators import somente_digitos, valida_cpf


class UsuarioManager(BaseUserManager):
    def create_user(self, email, nome_completo, cpf, papel, password=None, **extra):
        if not email:
            raise ValueError("E-mail e obrigatorio.")
        usuario = self.model(
            email=self.normalize_email(email),
            nome_completo=nome_completo,
            cpf=cpf,
            papel=papel,
            **extra,
        )
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, email, nome_completo, cpf, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(
            email=email,
            nome_completo=nome_completo,
            cpf=cpf,
            papel=Usuario.COORDENADOR,
            password=password,
            **extra,
        )


class Usuario(AbstractBaseUser, PermissionsMixin):
    COORDENADOR = "COORDENADOR"
    PROFESSOR = "PROFESSOR"
    ALUNO = "ALUNO"
    PAPEIS = [
        (COORDENADOR, "Coordenador"),
        (PROFESSOR, "Professor"),
        (ALUNO, "Aluno"),
    ]

    nome_completo = models.CharField("nome completo", max_length=150)
    email = models.EmailField("e-mail", unique=True)
    cpf = models.CharField("CPF", max_length=11, unique=True, validators=[valida_cpf])
    papel = models.CharField("papel", max_length=20, choices=PAPEIS)
    matricula = models.CharField(
        "matricula", max_length=20, unique=True, null=True, blank=True
    )
    siape = models.CharField("SIAPE", max_length=20, unique=True, null=True, blank=True)

    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("acessa o admin", default=False)
    date_joined = models.DateTimeField("cadastrado em", auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nome_completo", "cpf"]

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["nome_completo"]

    def __str__(self):
        return self.nome_completo

    @property
    def e_coordenador(self):
        return self.papel == self.COORDENADOR

    @property
    def e_professor(self):
        return self.papel == self.PROFESSOR

    @property
    def e_aluno(self):
        return self.papel == self.ALUNO

    def full_clean(self, *args, **kwargs):
        # Normaliza antes de qualquer validacao: sem isso a unicidade nao vale nada,
        # porque 529.982.247-25 e 52998224725 conviveriam no banco (spec 4.1).
        self.cpf = somente_digitos(self.cpf)
        self.matricula = somente_digitos(self.matricula) or None
        self.siape = somente_digitos(self.siape) or None
        super().full_clean(*args, **kwargs)

    def clean(self):
        super().clean()
        erros = {}
        if self.e_aluno:
            if not self.matricula:
                erros["matricula"] = "Matricula e obrigatoria para aluno."
            if self.siape:
                erros["siape"] = "Aluno nao tem SIAPE."
        else:
            if not self.siape:
                erros["siape"] = "SIAPE e obrigatorio para professor e coordenador."
            if self.matricula:
                erros["matricula"] = "Professor e coordenador nao tem matricula."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
```

- [ ] **Step 5: Gerar a migração e rodar os testes**

```bash
python manage.py makemigrations contas
pytest apps/contas/tests -v
```

Expected: PASS (todos os testes de `test_models.py` mais os da Task 2).

- [ ] **Step 6: Commitar**

```bash
git add apps/contas config/settings.py
git commit -m "feat(contas): modelo de usuario com papeis, CPF, matricula e SIAPE"
```

---

### Task 4: Admin de contas com CPF mascarado e comando de bootstrap

**Files:**
- Create: `apps/contas/admin.py`, `apps/contas/forms.py`, `apps/contas/management/__init__.py`, `apps/contas/management/commands/__init__.py`, `apps/contas/management/commands/criar_coordenador.py`
- Test: `apps/contas/tests/test_admin.py`, `apps/contas/tests/test_comandos.py`

**Interfaces:**
- Consumes: `Usuario` (Task 3).
- Produces: `apps.contas.admin.mascara_cpf(cpf: str) -> str` (devolve `***.***.247-25`); comando `python manage.py criar_coordenador --email --nome --cpf --siape --senha`.

- [ ] **Step 1: Escrever os testes (vão falhar)**

`apps/contas/tests/test_admin.py`:

```python
import pytest
from django.urls import reverse

from apps.contas.admin import mascara_cpf
from apps.contas.models import Usuario


def test_mascara_esconde_os_oito_primeiros_digitos():
    assert mascara_cpf("52998224725") == "***.***.247-25"


def test_mascara_aceita_vazio():
    assert mascara_cpf("") == ""


@pytest.mark.django_db
def test_listagem_do_admin_nao_expoe_cpf_inteiro(client):
    coordenador = Usuario.objects.create_superuser(
        email="coord@ufsm.br",
        nome_completo="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        password="senha-de-teste-123",
    )
    client.force_login(coordenador)
    resposta = client.get(reverse("admin:contas_usuario_changelist"))
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "***.***.247-25" in conteudo
    assert "52998224725" not in conteudo
```

`apps/contas/tests/test_comandos.py`:

```python
import pytest
from django.core.management import call_command

from apps.contas.models import Usuario


@pytest.mark.django_db
def test_comando_cria_coordenador_com_acesso_ao_admin():
    call_command(
        "criar_coordenador",
        email="coord@ufsm.br",
        nome="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        senha="senha-de-teste-123",
    )
    coordenador = Usuario.objects.get(email="coord@ufsm.br")
    assert coordenador.e_coordenador
    assert coordenador.is_staff and coordenador.is_superuser
    assert coordenador.check_password("senha-de-teste-123")
    assert coordenador.cpf == "52998224725"


@pytest.mark.django_db
def test_comando_e_idempotente_no_email():
    for _ in range(2):
        call_command(
            "criar_coordenador",
            email="coord@ufsm.br",
            nome="Carla Costa",
            cpf="529.982.247-25",
            siape="7654321",
            senha="senha-de-teste-123",
        )
    assert Usuario.objects.filter(email="coord@ufsm.br").count() == 1
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/contas/tests/test_admin.py apps/contas/tests/test_comandos.py -v`
Expected: FAIL - `ImportError: cannot import name 'mascara_cpf'` e `CommandError: Unknown command: 'criar_coordenador'`.

- [ ] **Step 3: Escrever os formulários do Admin**

`apps/contas/forms.py`:

```python
from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from apps.contas.models import Usuario


class UsuarioCreationForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("email", "nome_completo", "cpf", "papel", "matricula", "siape")


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = (
            "email",
            "nome_completo",
            "cpf",
            "papel",
            "matricula",
            "siape",
            "is_active",
            "is_staff",
        )
```

- [ ] **Step 4: Escrever o Admin**

`apps/contas/admin.py`:

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.contas.forms import UsuarioChangeForm, UsuarioCreationForm
from apps.contas.models import Usuario


def mascara_cpf(cpf):
    """Mostra so os tres ultimos digitos e o verificador (spec 10)."""
    if not cpf:
        return ""
    return f"***.***.{cpf[6:9]}-{cpf[9:11]}"


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    ordering = ["nome_completo"]
    list_display = ["nome_completo", "email", "papel", "cpf_mascarado", "is_active"]
    list_filter = ["papel", "is_active"]
    search_fields = ["nome_completo", "email", "matricula", "siape"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Identificacao", {"fields": ("nome_completo", "cpf", "papel", "matricula", "siape")}),
        ("Acesso", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "nome_completo", "cpf", "papel", "matricula", "siape", "password1", "password2"),
            },
        ),
    )

    @admin.display(description="CPF")
    def cpf_mascarado(self, obj):
        return mascara_cpf(obj.cpf)
```

`search_fields` não inclui `cpf` de propósito: buscar por CPF no Admin devolveria o número na URL e nos registros de acesso do servidor.

- [ ] **Step 5: Escrever o comando de bootstrap**

```bash
mkdir -p apps/contas/management/commands
touch apps/contas/management/__init__.py apps/contas/management/commands/__init__.py
```

`apps/contas/management/commands/criar_coordenador.py`:

```python
from django.core.management.base import BaseCommand

from apps.contas.models import Usuario


class Command(BaseCommand):
    help = "Cria (ou atualiza a senha do) coordenador inicial do sistema."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--nome", required=True)
        parser.add_argument("--cpf", required=True)
        parser.add_argument("--siape", required=True)
        parser.add_argument("--senha", required=True)

    def handle(self, *args, **opcoes):
        usuario = Usuario.objects.filter(email=opcoes["email"]).first()
        if usuario is None:
            Usuario.objects.create_superuser(
                email=opcoes["email"],
                nome_completo=opcoes["nome"],
                cpf=opcoes["cpf"],
                siape=opcoes["siape"],
                password=opcoes["senha"],
            )
            self.stdout.write(self.style.SUCCESS("Coordenador criado."))
            return
        usuario.set_password(opcoes["senha"])
        usuario.save()
        self.stdout.write(self.style.SUCCESS("Coordenador ja existia; senha atualizada."))
```

- [ ] **Step 6: Rodar os testes e ver passar**

Run: `pytest apps/contas/tests -v`
Expected: PASS.

- [ ] **Step 7: Commitar**

```bash
git add apps/contas
git commit -m "feat(contas): admin com CPF mascarado e comando criar_coordenador"
```

---

### Task 5: Autenticação e painel inicial por papel

**Files:**
- Create: `templates/base.html`, `templates/registration/login.html`, `templates/painel.html`, `apps/contas/views.py`, `apps/contas/urls.py`
- Modify: `config/urls.py`, `config/settings.py` (LOGIN_REDIRECT_URL, LOGOUT_REDIRECT_URL, LOGIN_URL)
- Test: `apps/contas/tests/test_views.py`

**Interfaces:**
- Consumes: `Usuario` (Task 3).
- Produces: rota nomeada `painel` (exige login) e as rotas de autenticação do Django (`login`, `logout`); `templates/base.html` com os blocos `titulo` e `conteudo`, herdado por todos os templates dos planos seguintes.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/contas/tests/test_views.py`:

```python
import pytest
from django.urls import reverse

from apps.contas.models import Usuario


@pytest.fixture
def aluno(db):
    return Usuario.objects.create_user(
        email="aluno@ufsm.br",
        nome_completo="Ana Alves",
        cpf="529.982.247-25",
        papel=Usuario.ALUNO,
        matricula="201910101",
        password="senha-de-teste-123",
    )


@pytest.mark.django_db
def test_painel_exige_login(client):
    resposta = client.get(reverse("painel"))
    assert resposta.status_code == 302
    assert reverse("login") in resposta.url


@pytest.mark.django_db
def test_painel_sauda_pelo_nome_e_mostra_o_papel(client, aluno):
    client.force_login(aluno)
    resposta = client.get(reverse("painel"))
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Ana Alves" in conteudo
    assert "Aluno" in conteudo


@pytest.mark.django_db
def test_painel_nunca_mostra_cpf(client, aluno):
    client.force_login(aluno)
    resposta = client.get(reverse("painel"))
    assert "52998224725" not in resposta.content.decode()


@pytest.mark.django_db
def test_login_com_email_e_senha(client, aluno):
    resposta = client.post(
        reverse("login"),
        {"username": "aluno@ufsm.br", "password": "senha-de-teste-123"},
    )
    assert resposta.status_code == 302
    assert resposta.url == reverse("painel")
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/contas/tests/test_views.py -v`
Expected: FAIL - `NoReverseMatch: Reverse for 'painel' not found`.

- [ ] **Step 3: Escrever a view e as rotas**

`apps/contas/views.py`:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def painel(request):
    return render(request, "painel.html")
```

`apps/contas/urls.py`:

```python
from django.urls import path

from apps.contas import views

urlpatterns = [
    path("painel/", views.painel, name="painel"),
]
```

`config/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("contas/", include("django.contrib.auth.urls")),
    path("", include("apps.contas.urls")),
]
```

Em `config/settings.py`, ao lado de `AUTH_USER_MODEL`:

```python
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "painel"
LOGOUT_REDIRECT_URL = "login"
```

- [ ] **Step 4: Escrever os templates**

`templates/base.html`:

```html
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block titulo %}IntegraSI{% endblock %}</title>
</head>
<body>
  <header>
    <a href="{% url 'painel' %}">IntegraSI</a>
    {% if user.is_authenticated %}
      <span>{{ user.nome_completo }} - {{ user.get_papel_display }}</span>
      <form method="post" action="{% url 'logout' %}">
        {% csrf_token %}
        <button type="submit">Sair</button>
      </form>
    {% endif %}
  </header>
  <main>
    {% block conteudo %}{% endblock %}
  </main>
</body>
</html>
```

`templates/registration/login.html`:

```html
{% extends "base.html" %}
{% block titulo %}Entrar - IntegraSI{% endblock %}
{% block conteudo %}
  <h1>Entrar</h1>
  {% if form.errors %}<p>E-mail ou senha incorretos.</p>{% endif %}
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Entrar</button>
  </form>
{% endblock %}
```

`templates/painel.html`:

```html
{% extends "base.html" %}
{% block titulo %}Painel - IntegraSI{% endblock %}
{% block conteudo %}
  <h1>Ola, {{ user.nome_completo }}</h1>
  <p>Voce esta no IntegraSI como {{ user.get_papel_display }}.</p>
{% endblock %}
```

- [ ] **Step 5: Rodar os testes e ver passar**

Run: `pytest apps/contas/tests -v`
Expected: PASS.

- [ ] **Step 6: Subir o servidor e conferir na mão**

```bash
python manage.py migrate
python manage.py criar_coordenador --email coord@ufsm.br --nome "Carla Costa" \
  --cpf 529.982.247-25 --siape 7654321 --senha trocar-esta-senha
python manage.py runserver
```

Abra `http://localhost:8000/`, entre com `coord@ufsm.br`, confirme a saudação e o botão Sair, e depois `http://localhost:8000/admin/` para ver a listagem com o CPF mascarado.

- [ ] **Step 7: Commitar**

```bash
git add apps/contas config templates
git commit -m "feat(contas): login por e-mail e painel inicial por papel"
```

---

### Task 6: Edições da disciplina

**Files:**
- Create: `apps/edicoes/` (app completo), `apps/edicoes/models.py`, `apps/edicoes/admin.py`
- Modify: `config/settings.py` (INSTALLED_APPS)
- Test: `apps/edicoes/tests/__init__.py`, `apps/edicoes/tests/test_models.py`

**Interfaces:**
- Consumes: nada.
- Produces: `apps.edicoes.models.Edicao` com `codigo`, `descricao`, `data_inicio`, `data_fim`, `ativa`; `Edicao.objects.corrente()` devolvendo a edição ativa ou `None`. O `Curso` (Plano 2) terá FK obrigatória para `Edicao`.

- [ ] **Step 1: Criar o app e registrá-lo**

```bash
mkdir -p apps/edicoes/tests
python manage.py startapp edicoes apps/edicoes
touch apps/edicoes/tests/__init__.py
```

Em `apps/edicoes/apps.py`, troque `name = "edicoes"` por `name = "apps.edicoes"`, e acrescente `"apps.edicoes"` a `INSTALLED_APPS`.

- [ ] **Step 2: Escrever o teste (vai falhar)**

`apps/edicoes/tests/test_models.py`:

```python
import datetime

import pytest
from django.core.exceptions import ValidationError

from apps.edicoes.models import Edicao


def criar_edicao(**kwargs):
    dados = {
        "codigo": "2026/2",
        "descricao": "TICs para Inclusao Digital",
        "data_inicio": datetime.date(2026, 8, 1),
        "data_fim": datetime.date(2026, 12, 20),
        "ativa": True,
    }
    dados.update(kwargs)
    return Edicao.objects.create(**dados)


@pytest.mark.django_db
def test_corrente_devolve_a_edicao_ativa():
    criar_edicao(codigo="2026/1", ativa=False)
    atual = criar_edicao()
    assert Edicao.objects.corrente() == atual


@pytest.mark.django_db
def test_corrente_devolve_none_quando_nenhuma_esta_ativa():
    criar_edicao(ativa=False)
    assert Edicao.objects.corrente() is None


@pytest.mark.django_db
def test_duas_edicoes_ativas_sao_recusadas():
    criar_edicao()
    with pytest.raises(ValidationError):
        criar_edicao(codigo="2027/1")


@pytest.mark.django_db
def test_fim_antes_do_inicio_e_recusado():
    with pytest.raises(ValidationError):
        criar_edicao(data_fim=datetime.date(2026, 1, 1))


@pytest.mark.django_db
def test_codigo_duplicado_e_recusado():
    criar_edicao(ativa=False)
    with pytest.raises(ValidationError):
        criar_edicao(ativa=False)


@pytest.mark.django_db
def test_str_e_o_codigo():
    assert str(criar_edicao()) == "2026/2"
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `pytest apps/edicoes/tests -v`
Expected: FAIL - `ImportError: cannot import name 'Edicao'`.

- [ ] **Step 4: Implementar o modelo**

`apps/edicoes/models.py`:

```python
from django.core.exceptions import ValidationError
from django.db import models


class EdicaoManager(models.Manager):
    def corrente(self):
        """A edicao em andamento, ou None se o coordenador ainda nao abriu nenhuma."""
        return self.filter(ativa=True).first()


class Edicao(models.Model):
    codigo = models.CharField("codigo", max_length=10, unique=True, help_text="Ex.: 2026/2")
    descricao = models.CharField("descricao", max_length=200)
    data_inicio = models.DateField("inicio")
    data_fim = models.DateField("fim")
    ativa = models.BooleanField("edicao corrente", default=False)

    objects = EdicaoManager()

    class Meta:
        verbose_name = "edicao"
        verbose_name_plural = "edicoes"
        ordering = ["-data_inicio"]

    def __str__(self):
        return self.codigo

    def clean(self):
        super().clean()
        if self.data_inicio and self.data_fim and self.data_fim <= self.data_inicio:
            raise ValidationError({"data_fim": "O fim deve ser posterior ao inicio."})
        if self.ativa:
            outras = Edicao.objects.filter(ativa=True).exclude(pk=self.pk)
            if outras.exists():
                raise ValidationError(
                    {"ativa": f"A edicao {outras.first().codigo} ja esta ativa. Desative-a antes."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
```

- [ ] **Step 5: Escrever o Admin**

`apps/edicoes/admin.py`:

```python
from django.contrib import admin

from apps.edicoes.models import Edicao


@admin.register(Edicao)
class EdicaoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "descricao", "data_inicio", "data_fim", "ativa"]
    list_filter = ["ativa"]
    search_fields = ["codigo", "descricao"]
```

- [ ] **Step 6: Migrar, rodar os testes e commitar**

```bash
python manage.py makemigrations edicoes
pytest apps/edicoes/tests -v
git add apps/edicoes config/settings.py
git commit -m "feat(edicoes): edicao da disciplina com apenas uma corrente por vez"
```

Expected: PASS (6 testes).

---

### Task 7: Referenciais pedagógicos, categorias e competências

**Files:**
- Create: `apps/referenciais/` (app completo), `apps/referenciais/models.py`, `apps/referenciais/choices.py`, `apps/referenciais/admin.py`
- Modify: `config/settings.py` (INSTALLED_APPS)
- Test: `apps/referenciais/tests/__init__.py`, `apps/referenciais/tests/test_models.py`

**Interfaces:**
- Consumes: nada.
- Produces: `apps.referenciais.models.Referencial` (`nome`, `sigla`, `descricao`, `min_competencias`, `max_competencias`, `ativo`), `Categoria` (`referencial`, `nome`, `ordem`), `Competencia` (`referencial`, `categoria`, `codigo`, `descricao`, `etapa`, `ordem`); `apps.referenciais.choices.ETAPAS` - lista de tuplas usada também pelo campo `etapa_ano` do `Curso` no Plano 2. Método `Referencial.valida_quantidade(n: int) -> None`, que o `Curso` chamará ao validar suas competências.

- [ ] **Step 1: Criar o app e registrá-lo**

```bash
mkdir -p apps/referenciais/tests
python manage.py startapp referenciais apps/referenciais
touch apps/referenciais/tests/__init__.py
```

Em `apps/referenciais/apps.py`, troque `name = "referenciais"` por `name = "apps.referenciais"`, e acrescente `"apps.referenciais"` a `INSTALLED_APPS`.

- [ ] **Step 2: Escrever o teste (vai falhar)**

`apps/referenciais/tests/test_models.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.referenciais.choices import ETAPAS
from apps.referenciais.models import Categoria, Competencia, Referencial


@pytest.fixture
def bncc(db):
    return Referencial.objects.create(
        nome="BNCC da Computacao",
        sigla="BNCC-COMP",
        descricao="Resolucao CNE/CEB 1/2022",
        min_competencias=2,
        max_competencias=5,
    )


@pytest.fixture
def pensamento(bncc):
    return Categoria.objects.create(referencial=bncc, nome="Pensamento Computacional", ordem=1)


def test_etapas_cobrem_da_infantil_ao_medio():
    codigos = [codigo for codigo, _ in ETAPAS]
    assert "EI" in codigos
    assert "EF05" in codigos
    assert "EM03" in codigos


@pytest.mark.django_db
def test_faixa_aceita_quantidade_dentro_do_intervalo(bncc):
    bncc.valida_quantidade(2)
    bncc.valida_quantidade(5)


@pytest.mark.django_db
def test_faixa_recusa_abaixo_do_minimo(bncc):
    with pytest.raises(ValidationError):
        bncc.valida_quantidade(1)


@pytest.mark.django_db
def test_faixa_recusa_acima_do_maximo(bncc):
    with pytest.raises(ValidationError):
        bncc.valida_quantidade(6)


@pytest.mark.django_db
def test_maximo_menor_que_minimo_e_recusado(bncc):
    bncc.max_competencias = 1
    with pytest.raises(ValidationError):
        bncc.full_clean()


@pytest.mark.django_db
def test_competencia_de_categoria_de_outro_referencial_e_recusada(bncc, pensamento):
    outro = Referencial.objects.create(
        nome="Curriculo Gaucho", sigla="CG", min_competencias=1, max_competencias=3
    )
    competencia = Competencia(
        referencial=outro,
        categoria=pensamento,
        codigo="XX01",
        descricao="Qualquer",
        etapa="EF05",
        ordem=1,
    )
    with pytest.raises(ValidationError):
        competencia.full_clean()


@pytest.mark.django_db
def test_codigo_repetido_no_mesmo_referencial_e_recusado(bncc, pensamento):
    Competencia.objects.create(
        referencial=bncc, categoria=pensamento, codigo="EF05CO01", descricao="A", etapa="EF05", ordem=1
    )
    duplicada = Competencia(
        referencial=bncc, categoria=pensamento, codigo="EF05CO01", descricao="B", etapa="EF05", ordem=2
    )
    with pytest.raises(ValidationError):
        duplicada.full_clean()


@pytest.mark.django_db
def test_str_da_competencia_mostra_codigo(bncc, pensamento):
    competencia = Competencia.objects.create(
        referencial=bncc, categoria=pensamento, codigo="EF05CO01", descricao="Descricao", etapa="EF05", ordem=1
    )
    assert str(competencia).startswith("EF05CO01")
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `pytest apps/referenciais/tests -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'apps.referenciais.choices'`.

- [ ] **Step 4: Escrever as etapas de ensino**

`apps/referenciais/choices.py`:

```python
# Etapas da educacao basica. Usado pela Competencia e pelo campo etapa_ano do Curso
# quando o publico e escolar (spec 4.3).
ETAPAS = [
    ("EI", "Educacao Infantil"),
    ("EF01", "1o ano do Ensino Fundamental"),
    ("EF02", "2o ano do Ensino Fundamental"),
    ("EF03", "3o ano do Ensino Fundamental"),
    ("EF04", "4o ano do Ensino Fundamental"),
    ("EF05", "5o ano do Ensino Fundamental"),
    ("EF06", "6o ano do Ensino Fundamental"),
    ("EF07", "7o ano do Ensino Fundamental"),
    ("EF08", "8o ano do Ensino Fundamental"),
    ("EF09", "9o ano do Ensino Fundamental"),
    ("EM01", "1o ano do Ensino Medio"),
    ("EM02", "2o ano do Ensino Medio"),
    ("EM03", "3o ano do Ensino Medio"),
]
```

- [ ] **Step 5: Implementar os modelos**

Sobre os `on_delete`: as tres chaves cascateiam, de modo que apagar um referencial leva junto suas categorias e competencias. Nao ha `PROTECT` aqui de proposito - o guarda real esta no Plano 2, onde `Curso.referencial` e `PROTECT`: um referencial usado por qualquer curso nao pode ser apagado, e so os nao utilizados cascateiam. Um `PROTECT` em `Competencia.categoria` combinado com o `CASCADE` de `Categoria.referencial` cria um impasse: o coletor do Django desce de `Referencial` para `Categoria`, esbarra no `PROTECT` e levanta `ProtectedError` mesmo quando as mesmas competencias ja estavam marcadas para cascatear.

`apps/referenciais/models.py`:

```python
from django.core.exceptions import ValidationError
from django.db import models

from apps.referenciais.choices import ETAPAS


class Referencial(models.Model):
    """Um modelo pedagogico de referencia. A BNCC da Computacao e um deles, nao o unico:
    cursos de Arduino ou IA na Educacao ficam sem referencial (spec 4.2)."""

    nome = models.CharField("nome", max_length=120, unique=True)
    sigla = models.CharField("sigla", max_length=20, unique=True)
    descricao = models.TextField("descricao", blank=True)
    min_competencias = models.PositiveSmallIntegerField("minimo de competencias", default=1)
    max_competencias = models.PositiveSmallIntegerField("maximo de competencias", default=5)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "referencial"
        verbose_name_plural = "referenciais"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        if self.max_competencias < self.min_competencias:
            raise ValidationError(
                {"max_competencias": "O maximo nao pode ser menor que o minimo."}
            )

    def valida_quantidade(self, quantidade):
        """Levanta ValidationError se a quantidade de competencias escolhidas nao
        respeitar a faixa deste referencial. Chamado pelo Curso (Plano 2)."""
        if not (self.min_competencias <= quantidade <= self.max_competencias):
            raise ValidationError(
                f"{self.nome} exige de {self.min_competencias} a "
                f"{self.max_competencias} competencias; foram escolhidas {quantidade}."
            )


class Categoria(models.Model):
    """Agrupamento dentro de um referencial. Na BNCC da Computacao chama-se eixo."""

    referencial = models.ForeignKey(
        Referencial, on_delete=models.CASCADE, related_name="categorias", verbose_name="referencial"
    )
    nome = models.CharField("nome", max_length=120)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["referencial", "ordem", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["referencial", "nome"], name="categoria_unica_no_referencial")
        ]

    def __str__(self):
        return self.nome


class Competencia(models.Model):
    referencial = models.ForeignKey(
        Referencial, on_delete=models.CASCADE, related_name="competencias", verbose_name="referencial"
    )
    categoria = models.ForeignKey(
        Categoria, on_delete=models.CASCADE, related_name="competencias", verbose_name="categoria"
    )
    codigo = models.CharField("codigo", max_length=20)
    descricao = models.TextField("descricao")
    etapa = models.CharField("etapa", max_length=4, choices=ETAPAS)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "competencia"
        verbose_name_plural = "competencias"
        ordering = ["referencial", "etapa", "ordem", "codigo"]
        constraints = [
            models.UniqueConstraint(fields=["referencial", "codigo"], name="competencia_unica_no_referencial")
        ]

    def __str__(self):
        return f"{self.codigo} - {self.descricao[:60]}"

    def clean(self):
        super().clean()
        if self.categoria_id and self.referencial_id and self.categoria.referencial_id != self.referencial_id:
            raise ValidationError({"categoria": "A categoria pertence a outro referencial."})
```

- [ ] **Step 6: Escrever o Admin**

`apps/referenciais/admin.py`:

```python
from django.contrib import admin

from apps.referenciais.models import Categoria, Competencia, Referencial


class CategoriaInline(admin.TabularInline):
    model = Categoria
    extra = 0


@admin.register(Referencial)
class ReferencialAdmin(admin.ModelAdmin):
    list_display = ["nome", "sigla", "min_competencias", "max_competencias", "ativo"]
    list_filter = ["ativo"]
    inlines = [CategoriaInline]


@admin.register(Competencia)
class CompetenciaAdmin(admin.ModelAdmin):
    list_display = ["codigo", "etapa", "categoria", "referencial"]
    list_filter = ["referencial", "etapa", "categoria"]
    search_fields = ["codigo", "descricao"]
```

- [ ] **Step 7: Migrar, rodar os testes e commitar**

```bash
python manage.py makemigrations referenciais
pytest apps/referenciais/tests -v
git add apps/referenciais config/settings.py
git commit -m "feat(referenciais): referencial generico com categorias e competencias"
```

Expected: PASS (8 testes).

---

### Task 8: Carga da BNCC da Computação

**Files:**
- Create: `apps/referenciais/fixtures/bncc_computacao.json`, `apps/referenciais/management/__init__.py`, `apps/referenciais/management/commands/__init__.py`, `apps/referenciais/management/commands/importar_competencias.py`, `docs/dados/README.md`
- Test: `apps/referenciais/tests/test_importacao.py`

**Interfaces:**
- Consumes: `Referencial`, `Categoria`, `Competencia` (Task 7).
- Produces: fixture com o referencial `BNCC-COMP` e seus três eixos; comando `python manage.py importar_competencias --referencial BNCC-COMP --csv caminho.csv`, idempotente.

**Nota importante para quem executa:** os códigos oficiais das habilidades da BNCC da Computação (`EF05CO01` e afins) **não são inventados aqui**. O comando importa de um CSV que o coordenador monta a partir do texto da Resolução CNE/CEB nº 1/2022. A fixture traz apenas o referencial e os três eixos, que são estáveis e verificáveis.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/referenciais/tests/test_importacao.py`:

```python
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.referenciais.models import Categoria, Competencia, Referencial

CSV = """codigo,descricao,etapa,categoria
EF05CO01,Decompor um problema em partes menores,EF05,Pensamento Computacional
EF05CO04,Reconhecer dados pessoais e sua protecao,EF05,Cultura Digital
"""


@pytest.fixture
def bncc(db):
    call_command("loaddata", "bncc_computacao")
    return Referencial.objects.get(sigla="BNCC-COMP")


@pytest.mark.django_db
def test_fixture_traz_referencial_e_os_tres_eixos(bncc):
    assert bncc.min_competencias == 2
    assert bncc.max_competencias == 5
    nomes = set(bncc.categorias.values_list("nome", flat=True))
    assert nomes == {"Pensamento Computacional", "Mundo Digital", "Cultura Digital"}


@pytest.mark.django_db
def test_importa_competencias_do_csv(bncc, tmp_path):
    arquivo = tmp_path / "habilidades.csv"
    arquivo.write_text(CSV, encoding="utf-8")
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    assert Competencia.objects.filter(referencial=bncc).count() == 2
    competencia = Competencia.objects.get(codigo="EF05CO01")
    assert competencia.categoria.nome == "Pensamento Computacional"
    assert competencia.etapa == "EF05"


@pytest.mark.django_db
def test_importar_duas_vezes_nao_duplica_e_atualiza_descricao(bncc, tmp_path):
    arquivo = tmp_path / "habilidades.csv"
    arquivo.write_text(CSV, encoding="utf-8")
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    arquivo.write_text(CSV.replace("Decompor um problema em partes menores", "Texto corrigido"), encoding="utf-8")
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    assert Competencia.objects.filter(referencial=bncc).count() == 2
    assert Competencia.objects.get(codigo="EF05CO01").descricao == "Texto corrigido"


@pytest.mark.django_db
def test_categoria_desconhecida_no_csv_interrompe_a_importacao(bncc, tmp_path):
    """A primeira linha e valida e a segunda nao: sem @transaction.atomic no
    comando, a primeira sobreviveria e o arquivo ficaria meio importado. Com uma
    linha ruim apenas, o teste passaria mesmo sem a transacao, e nao testaria nada."""
    arquivo = tmp_path / "habilidades.csv"
    arquivo.write_text(
        "codigo,descricao,etapa,categoria\n"
        "EF05CO01,Decompor um problema,EF05,Pensamento Computacional\n"
        "EF05CO09,X,EF05,Eixo Inexistente\n",
        encoding="utf-8",
    )
    with pytest.raises(CommandError):
        call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    assert Competencia.objects.filter(referencial=bncc).count() == 0
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/referenciais/tests/test_importacao.py -v`
Expected: FAIL - `CommandError: No fixture named 'bncc_computacao' found`.

- [ ] **Step 3: Escrever a fixture**

```bash
mkdir -p apps/referenciais/fixtures
```

`apps/referenciais/fixtures/bncc_computacao.json`:

```json
[
  {
    "model": "referenciais.referencial",
    "pk": 1,
    "fields": {
      "nome": "BNCC da Computacao",
      "sigla": "BNCC-COMP",
      "descricao": "Complemento a BNCC - Resolucao CNE/CEB no 1/2022",
      "min_competencias": 2,
      "max_competencias": 5,
      "ativo": true
    }
  },
  {
    "model": "referenciais.categoria",
    "pk": 1,
    "fields": {"referencial": 1, "nome": "Pensamento Computacional", "ordem": 1}
  },
  {
    "model": "referenciais.categoria",
    "pk": 2,
    "fields": {"referencial": 1, "nome": "Mundo Digital", "ordem": 2}
  },
  {
    "model": "referenciais.categoria",
    "pk": 3,
    "fields": {"referencial": 1, "nome": "Cultura Digital", "ordem": 3}
  }
]
```

- [ ] **Step 4: Escrever o comando de importação**

```bash
mkdir -p apps/referenciais/management/commands
touch apps/referenciais/management/__init__.py apps/referenciais/management/commands/__init__.py
```

`apps/referenciais/management/commands/importar_competencias.py`:

```python
import csv as csv_lib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.referenciais.choices import ETAPAS
from apps.referenciais.models import Competencia, Referencial

COLUNAS = {"codigo", "descricao", "etapa", "categoria"}
ETAPAS_VALIDAS = {codigo for codigo, _ in ETAPAS}


class Command(BaseCommand):
    help = "Importa competencias de um referencial a partir de um CSV (codigo,descricao,etapa,categoria)."

    def add_arguments(self, parser):
        parser.add_argument("--referencial", required=True, help="Sigla do referencial, ex.: BNCC-COMP")
        parser.add_argument("--csv", required=True, help="Caminho do arquivo CSV")

    @transaction.atomic
    def handle(self, *args, **opcoes):
        try:
            referencial = Referencial.objects.get(sigla=opcoes["referencial"])
        except Referencial.DoesNotExist:
            raise CommandError(f"Referencial {opcoes['referencial']} nao existe.")

        categorias = {c.nome: c for c in referencial.categorias.all()}

        with open(opcoes["csv"], encoding="utf-8") as arquivo:
            leitor = csv_lib.DictReader(arquivo)
            if not COLUNAS.issubset(set(leitor.fieldnames or [])):
                raise CommandError(f"O CSV precisa das colunas: {', '.join(sorted(COLUNAS))}.")
            total = 0
            for numero, linha in enumerate(leitor, start=2):
                # linha.get(campo) or "" cobre a linha curta, em que o DictReader
                # devolve None e um .strip() direto estouraria com AttributeError
                # no terminal do coordenador em vez de uma mensagem util.
                valores = {campo: (linha.get(campo) or "").strip() for campo in COLUNAS}
                if not valores["codigo"]:
                    raise CommandError(f"Linha {numero}: codigo vazio.")
                categoria = categorias.get(valores["categoria"])
                if categoria is None:
                    raise CommandError(
                        f"Linha {numero}: categoria '{valores['categoria']}' nao existe em {referencial.sigla}."
                    )
                # O CSV e transcrito a mao a partir do PDF da Resolucao, e
                # update_or_create nao chama full_clean(): sem esta conferencia uma
                # etapa digitada errada ("EF5") gravaria em silencio, e a habilidade
                # sumiria do ano a que deveria pertencer sem erro nenhum.
                if valores["etapa"] not in ETAPAS_VALIDAS:
                    raise CommandError(
                        f"Linha {numero}: etapa '{valores['etapa']}' nao existe. "
                        f"Use uma de: {', '.join(sorted(ETAPAS_VALIDAS))}."
                    )
                Competencia.objects.update_or_create(
                    referencial=referencial,
                    codigo=valores["codigo"],
                    defaults={
                        "categoria": categoria,
                        "descricao": valores["descricao"],
                        "etapa": valores["etapa"],
                        "ordem": total,
                    },
                )
                total += 1

        self.stdout.write(self.style.SUCCESS(f"{total} competencias importadas em {referencial.sigla}."))
```

O decorador `@transaction.atomic` é o que faz o último teste passar: uma categoria desconhecida no meio do arquivo desfaz a importação inteira, em vez de deixar metade das habilidades carregadas.

- [ ] **Step 5: Documentar a origem dos dados**

```bash
mkdir -p docs/dados
cat > docs/dados/README.md <<'EOF'
# Dados de referencia

## BNCC da Computacao

A fixture `apps/referenciais/fixtures/bncc_computacao.json` traz o referencial e os
tres eixos (Pensamento Computacional, Mundo Digital, Cultura Digital).

As habilidades (EF05CO01 e afins) NAO estao no repositorio: elas sao transcritas do
Complemento a BNCC (Resolucao CNE/CEB no 1/2022) para um CSV com as colunas
`codigo,descricao,etapa,categoria` e importadas com:

    python manage.py loaddata bncc_computacao
    python manage.py importar_competencias --referencial BNCC-COMP --csv habilidades.csv

Importar de novo atualiza as descricoes sem duplicar nada.
EOF
```

- [ ] **Step 6: Rodar os testes e commitar**

Run: `pytest apps/referenciais/tests -v`
Expected: PASS (12 testes, somando os da Task 7).

```bash
git add apps/referenciais docs/dados
git commit -m "feat(referenciais): fixture da BNCC e importador de competencias por CSV"
```

---

### Task 9: Temas para filtro do catálogo

**Files:**
- Create: `apps/cursos/` (app completo, começando pelo `Tema`), `apps/cursos/models.py`, `apps/cursos/admin.py`, `apps/cursos/fixtures/temas_iniciais.json`
- Modify: `config/settings.py` (INSTALLED_APPS)
- Test: `apps/cursos/tests/__init__.py`, `apps/cursos/tests/test_tema.py`

**Interfaces:**
- Consumes: nada.
- Produces: `apps.cursos.models.Tema` com `nome`, `slug` (gerado do nome quando vazio) e `ativo`. O `Curso` (Plano 2) terá M2M `temas` para este modelo, e o catálogo (Plano 3) o usará como filtro.

Este é o primeiro arquivo do app `cursos`, que os planos seguintes vão preencher. Ele entra aqui, e não no Plano 2, porque `Tema` é cadastro de apoio como os demais desta etapa e não depende de nada do núcleo de produção.

- [ ] **Step 1: Criar o app e registrá-lo**

```bash
mkdir -p apps/cursos/tests
python manage.py startapp cursos apps/cursos
touch apps/cursos/tests/__init__.py
```

Em `apps/cursos/apps.py`, troque `name = "cursos"` por `name = "apps.cursos"`, e acrescente `"apps.cursos"` a `INSTALLED_APPS`.

- [ ] **Step 2: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_tema.py`:

```python
import pytest
from django.core.exceptions import ValidationError

from apps.cursos.models import Tema


@pytest.mark.django_db
def test_slug_e_gerado_a_partir_do_nome():
    tema = Tema.objects.create(nome="Robotica Educacional")
    assert tema.slug == "robotica-educacional"


@pytest.mark.django_db
def test_slug_informado_e_respeitado():
    tema = Tema.objects.create(nome="IA na Educacao", slug="ia-educacao")
    assert tema.slug == "ia-educacao"


@pytest.mark.django_db
def test_nome_duplicado_e_recusado():
    Tema.objects.create(nome="Seguranca Digital")
    with pytest.raises(ValidationError):
        Tema.objects.create(nome="Seguranca Digital")


@pytest.mark.django_db
def test_slug_duplicado_por_nomes_parecidos_e_recusado():
    Tema.objects.create(nome="Seguranca Digital")
    with pytest.raises(ValidationError):
        Tema.objects.create(nome="Seguranca digital!")


@pytest.mark.django_db
def test_tema_nasce_ativo_e_str_e_o_nome():
    tema = Tema.objects.create(nome="Inclusao Digital de Adultos")
    assert tema.ativo is True
    assert str(tema) == "Inclusao Digital de Adultos"
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `pytest apps/cursos/tests -v`
Expected: FAIL - `ImportError: cannot import name 'Tema' from 'apps.cursos.models'`.

- [ ] **Step 4: Implementar o modelo**

`apps/cursos/models.py`:

```python
from django.db import models
from django.utils.text import slugify


class Tema(models.Model):
    """Vocabulario controlado usado como filtro no catalogo publico (spec 4.4).
    E controlado de proposito: com texto livre, 'robotica' e 'Robotica' viram dois
    filtros diferentes e nenhum deles encontra tudo."""

    nome = models.CharField("nome", max_length=80, unique=True)
    slug = models.SlugField("slug", max_length=80, unique=True, blank=True)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "tema"
        verbose_name_plural = "temas"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def full_clean(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().full_clean(*args, **kwargs)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
```

- [ ] **Step 5: Escrever o Admin**

`apps/cursos/admin.py`:

```python
from django.contrib import admin

from apps.cursos.models import Tema


@admin.register(Tema)
class TemaAdmin(admin.ModelAdmin):
    list_display = ["nome", "slug", "ativo"]
    list_filter = ["ativo"]
    search_fields = ["nome"]
    prepopulated_fields = {"slug": ("nome",)}
```

- [ ] **Step 6: Escrever a fixture de temas iniciais**

A spec §13 pede temas na carga inicial, para que o catálogo não nasça sem filtro nenhum. Acrescente o teste ao fim de `apps/cursos/tests/test_tema.py`:

```python
@pytest.mark.django_db
def test_fixture_carrega_temas_iniciais_ativos():
    from django.core.management import call_command

    call_command("loaddata", "temas_iniciais")
    assert Tema.objects.filter(ativo=True).count() == 5
    assert Tema.objects.filter(slug="ia-na-educacao").exists()
```

Rode e veja falhar: `pytest apps/cursos/tests/test_tema.py::test_fixture_carrega_temas_iniciais_ativos -v`
Expected: FAIL - `CommandError: No fixture named 'temas_iniciais' found`.

Depois crie o arquivo:

```bash
mkdir -p apps/cursos/fixtures
```

`apps/cursos/fixtures/temas_iniciais.json`:

```json
[
  {"model": "cursos.tema", "pk": 1, "fields": {"nome": "Pensamento Computacional", "slug": "pensamento-computacional", "ativo": true}},
  {"model": "cursos.tema", "pk": 2, "fields": {"nome": "Robotica Educacional", "slug": "robotica-educacional", "ativo": true}},
  {"model": "cursos.tema", "pk": 3, "fields": {"nome": "Seguranca Digital", "slug": "seguranca-digital", "ativo": true}},
  {"model": "cursos.tema", "pk": 4, "fields": {"nome": "IA na Educacao", "slug": "ia-na-educacao", "ativo": true}},
  {"model": "cursos.tema", "pk": 5, "fields": {"nome": "Inclusao Digital de Adultos", "slug": "inclusao-digital-de-adultos", "ativo": true}}
]
```

Rode de novo: `pytest apps/cursos/tests/test_tema.py -v`
Expected: PASS (6 testes).

Esta lista é ponto de partida, não camisa de força: o coordenador acrescenta e desativa temas pelo Admin conforme os cursos aparecem.

- [ ] **Step 7: Migrar e rodar a suíte inteira**

```bash
python manage.py makemigrations cursos
pytest -v
```

Expected: PASS - todos os testes dos apps `contas`, `edicoes`, `referenciais` e `cursos`, mais os de configuração.

- [ ] **Step 8: Conferir na mão e commitar**

```bash
python manage.py migrate
python manage.py loaddata bncc_computacao temas_iniciais
python manage.py runserver
```

Entre no Admin como coordenador e confirme que dá para cadastrar uma edição, ver a BNCC da Computação com seus três eixos, e ver os cinco temas carregados. Depois:

```bash
git add apps/cursos config/settings.py
git commit -m "feat(cursos): tema controlado para filtro do catalogo"
```

---

## Entregue ao fim deste plano

O coordenador entra no sistema, cadastra professores e alunos com seus documentos validados, abre a edição corrente da disciplina, carrega a BNCC da Computação (ou qualquer outro referencial) e cadastra os temas do catálogo. Nada de curso ainda - é o que o **Plano 2: Produção de cursos** constrói em cima disto.

## Próximos planos

- **Plano 2 - Produção de cursos:** `Curso` com identidade pedagógica e público-alvo obrigatório, `MembroEquipe`, os cinco `Entregavel`, `Secao`, `Anexo`, `Revisao`, `services.py` com a máquina de estados e as validações do §6.
- **Plano 3 - Publicação e demanda:** submissão ao coordenador, catálogo público com busca, `Solicitacao`, `Turma`, `Participante`, `notificacoes`.
- **Plano 4 - Mídia e versões:** `Arquivo`, upload retomável de 1 GB, entrega via `X-Accel-Redirect`, versionamento de cursos, deploy e backup.
