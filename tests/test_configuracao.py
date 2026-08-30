import os
import subprocess
import sys

import pytest
from django.conf import settings


def _importar_settings_em_subprocesso(remover=(), acrescentar=None, expressao="settings.DEBUG"):
    """Importa config.settings num subprocesso com ambiente limpo, fora do
    alcance de pytest-django (que força settings.DEBUG = False para toda a
    sessão de testes via setup_test_environment()).

    `expressao` é o que o subprocesso imprime: qualquer setting cujo padrão
    dependa de DEBUG só pode ser observado assim."""
    ambiente = {k: v for k, v in os.environ.items() if k not in remover}
    ambiente.update(acrescentar or {})
    ambiente["DJANGO_SETTINGS_MODULE"] = "config.settings"
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); from django.conf import settings; "
            f"print({expressao})",
        ],
        capture_output=True,
        text=True,
        env=ambiente,
    )


def test_debug_desligado_quando_a_variavel_nao_e_definida():
    """pytest-django força DEBUG=False durante os testes, então a única forma de
    verificar o padrão de produção é importar as settings fora dele."""
    resultado = _importar_settings_em_subprocesso(remover={"DEBUG"})
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


def test_banco_e_postgresql():
    assert "postgresql" in settings.DATABASES["default"]["ENGINE"]


def test_idioma_e_fuso_do_projeto():
    assert settings.LANGUAGE_CODE == "pt-br"
    assert settings.TIME_ZONE == "America/Sao_Paulo"
    assert settings.USE_TZ is True


def test_x_accel_nasce_ligado_quando_debug_esta_desligado():
    """Em produção quem transmite arquivo é o nginx (spec 8). O padrão precisa ser
    o seguro: quem esquecer de definir USAR_X_ACCEL no servidor não pode acabar
    com o Django transmitindo 1 GB de dentro de um worker."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG", "USAR_X_ACCEL"}, expressao="settings.USAR_X_ACCEL"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "True"


def test_x_accel_nasce_desligado_em_desenvolvimento():
    """Sem nginx na frente, um X-Accel-Redirect chega ao navegador como resposta
    vazia: na máquina de quem desenvolve, quem entrega é o próprio Django."""
    resultado = _importar_settings_em_subprocesso(
        remover={"USAR_X_ACCEL"}, acrescentar={"DEBUG": "True"}, expressao="settings.USAR_X_ACCEL"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


# --- Segurança de produção ----------------------------------------------------
# Dívida registrada no CLAUDE.md desde o Plano 1: "Segurança de produção (HTTPS,
# cookies seguros, HSTS) é do Plano 4, dono do deploy". Como o padrão depende de
# DEBUG, e pytest-django força DEBUG=False na sessão inteira, a única forma de
# observar o padrão é a mesma de USAR_X_ACCEL: importar as settings num
# subprocesso com ambiente de produção.

SEGURANCA_EM_PRODUCAO = {
    "SECURE_SSL_REDIRECT": "True",
    "SESSION_COOKIE_SECURE": "True",
    "CSRF_COOKIE_SECURE": "True",
    "SECURE_HSTS_SECONDS": "31536000",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": "True",
    "SECURE_HSTS_PRELOAD": "True",
    "SECURE_PROXY_SSL_HEADER": "('HTTP_X_FORWARDED_PROTO', 'https')",
}


@pytest.mark.parametrize("chave,esperado", sorted(SEGURANCA_EM_PRODUCAO.items()))
def test_seguranca_de_producao_nasce_ligada(chave, esperado):
    """Quem esquecer SEGURANCA_HTTPS no servidor não pode acabar servindo o
    sistema em http, com cookie de sessão viajando em claro e sem HSTS."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG", "SEGURANCA_HTTPS", "CONFIAR_NO_PROXY"},
        expressao=f"settings.{chave}",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == esperado


@pytest.mark.parametrize("chave", sorted(SEGURANCA_EM_PRODUCAO))
def test_seguranca_de_producao_nasce_desligada_em_desenvolvimento(chave):
    """Sem TLS na máquina de quem desenvolve, SECURE_SSL_REDIRECT devolveria 301
    para uma porta https que não existe: o runserver ficaria inutilizável."""
    resultado = _importar_settings_em_subprocesso(
        remover={"SEGURANCA_HTTPS", "CONFIAR_NO_PROXY"},
        acrescentar={"DEBUG": "True"},
        expressao=f"settings.{chave}",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() in ("False", "0", "None")


def test_a_seguranca_pode_ser_desligada_por_variavel():
    """Um servidor de homologação sem certificado precisa subir; o desligamento é
    explícito e por variável, nunca por acidente."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG"},
        acrescentar={"SEGURANCA_HTTPS": "False"},
        expressao="settings.SECURE_SSL_REDIRECT",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


def test_confiar_no_proxy_nasce_ligado_em_producao():
    """Atrás do nginx, REMOTE_ADDR é sempre 127.0.0.1: sem esta chave o limite por
    IP do formulário público viraria um limite global (spec 10)."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG", "CONFIAR_NO_PROXY"}, expressao="settings.CONFIAR_NO_PROXY"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "True"


def test_confiar_no_proxy_nasce_desligado_em_desenvolvimento():
    """Sem proxy na frente, X-Forwarded-For é texto escrito pelo cliente."""
    resultado = _importar_settings_em_subprocesso(
        remover={"CONFIAR_NO_PROXY"},
        acrescentar={"DEBUG": "True"},
        expressao="settings.CONFIAR_NO_PROXY",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"
