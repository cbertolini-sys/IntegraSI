from pathlib import Path

import dj_database_url
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
# `ARQUIVO_ENV` existe para que os testes possam observar o PADRAO do codigo. Sem
# ele, `load_dotenv` reabre o .env desta maquina dentro do subprocesso de teste e
# repoe as variaveis que o teste acabou de remover do ambiente: o teste da
# seguranca de producao passava a medir "codigo + .env local", e reprovava em
# qualquer instalacao que definisse SEGURANCA_HTTPS - inclusive a do servidor.
# Em producao ninguem define esta variavel, e o caminho e o de sempre.
load_dotenv(os.environ.get("ARQUIVO_ENV") or BASE_DIR / ".env")

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
    "django.contrib.postgres",
    "apps.catalogo",
    "apps.contas",
    "apps.cursos",
    "apps.notificacoes",
    "apps.referenciais",
    "apps.turmas",
    "apps.painel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.contas.middleware.PerfilCompletoMiddleware",
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

AUTH_USER_MODEL = "contas.Usuario"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "painel"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"
# Em producao quem transmite arquivo e o nginx (X-Accel-Redirect); em
# desenvolvimento, o proprio Django. O padrao segue DEBUG para que esquecer a
# variavel no servidor nao deixe 1 GB de video passando por um worker Python.
USAR_X_ACCEL = os.environ.get("USAR_X_ACCEL", "True" if not DEBUG else "False") == "True"

# --- Producao atras do nginx (spec 13) ---------------------------------------
# As duas chaves abaixo nascem ligadas quando DEBUG esta desligado, pelo mesmo
# motivo de USAR_X_ACCEL: esquecer a variavel no servidor nao pode produzir a
# configuracao insegura. Quem desenvolve continua sem nenhuma delas.

# Existe um proxy na frente e o que ele diz sobre a requisicao vale. Atras do
# nginx, REMOTE_ADDR e sempre 127.0.0.1: sem esta chave, o limite por IP do
# formulario publico (spec 10) viraria um limite global, e um visitante
# fecharia o formulario para todo mundo. Sem proxy nenhum na frente, ao
# contrario, X-Forwarded-For e texto escrito pelo cliente e nao vale nada -- por
# isso a leitura e condicional, e nao incondicional. Quem servir o gunicorn
# exposto direto na rede tem que deixar isto em False.
CONFIAR_NO_PROXY = os.environ.get("CONFIAR_NO_PROXY", "True" if not DEBUG else "False") == "True"

# HTTPS obrigatorio (spec 13, e a divida que o Plano 1 registrou no CLAUDE.md:
# "Seguranca de producao (HTTPS, cookies seguros, HSTS) e do Plano 4").
SEGURANCA_HTTPS = os.environ.get("SEGURANCA_HTTPS", "True" if not DEBUG else "False") == "True"
SECURE_SSL_REDIRECT = SEGURANCA_HTTPS
SESSION_COOKIE_SECURE = SEGURANCA_HTTPS
CSRF_COOKIE_SECURE = SEGURANCA_HTTPS
# Um ano, com subdominios e apto a preload: HSTS curto so adia o problema, e
# meia-boca ele nao protege o primeiro acesso de subdominio nenhum.
SECURE_HSTS_SECONDS = 31_536_000 if SEGURANCA_HTTPS else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SEGURANCA_HTTPS
SECURE_HSTS_PRELOAD = SEGURANCA_HTTPS
# O gunicorn so ve http; quem termina o TLS e o nginx, que repassa o esquema
# neste cabecalho (deploy/nginx.conf). Sem isto, SECURE_SSL_REDIRECT devolve 301
# para https, o nginx repassa em http de novo, e o navegador entra em laco.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if CONFIAR_NO_PROXY else None
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"

EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "integrasi@ufsm.br")

# Acima disto o upload vai para arquivo temporario em vez de ficar na memoria.
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
# Teto geral do corpo da requisicao nesta etapa; o Plano 4 sobe o limite so na
# rota de upload de video em blocos.
DATA_UPLOAD_MAX_MEMORY_SIZE = 55 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Log e aviso de erro ------------------------------------------------------

# `ADMINS` recebe "Nome:email" separados por virgula. Vazio, ninguem e avisado -
# que era o estado anterior, com o `AdminEmailHandler` padrao do Django
# apontando para uma lista vazia.
ADMINS = [
    (nome.strip(), email.strip())
    for nome, _, email in (
        entrada.partition(":")
        for entrada in os.environ.get("ADMINS", "").split(",")
        if entrada.strip()
    )
    if email.strip()
]
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

# Log da aplicacao em arquivo proprio, com rotacao.
#
# Sem isto vale o padrao do Django: `django.request` escreve em stderr (que vira
# journald, sem retencao definida por nos) e num `AdminEmailHandler` que, com
# ADMINS vazio, nao manda para ninguem. Um 500 em producao nao deixava rastro em
# arquivo nenhum e nao avisava ninguem.
#
# Ligado por variavel, e nao por `not DEBUG`, ao contrario das tres chaves de
# seguranca: aquelas produzem configuracao SEGURA quando esquecidas, esta abre um
# arquivo no disco. Um caminho errado (ou um diretorio que nao existe, ou sem
# permissao para o usuario do servico) faz o processo NAO SUBIR - o handler e
# construido na carga das settings. Melhor ficar sem log do que nao subir, e o
# `docs/operacao.md` cobra a variavel na instalacao.
CAMINHO_DO_LOG = os.environ.get("CAMINHO_DO_LOG", "")
if CAMINHO_DO_LOG:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "completo": {
                "format": "{asctime} {levelname} {name} {message}",
                "style": "{",
            },
        },
        "handlers": {
            "arquivo": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": CAMINHO_DO_LOG,
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 10,
                "formatter": "completo",
            },
            "email_admin": {
                "level": "ERROR",
                "class": "django.utils.log.AdminEmailHandler",
                # `include_html` FALSE de proposito. O corpo HTML que o Django
                # monta traz o traceback com as VARIAVEIS LOCAIS de cada quadro,
                # e nesta base as locais de uma view de convite ou de perfil
                # carregam CPF, e-mail e telefone de terceiro (spec 10). Ligar o
                # padrao mandaria dado pessoal por e-mail a cada erro.
                "include_html": False,
            },
        },
        "loggers": {
            "django": {"handlers": ["arquivo"], "level": "INFO"},
            "django.request": {
                "handlers": ["arquivo", "email_admin"],
                "level": "ERROR",
                "propagate": False,
            },
        },
    }
