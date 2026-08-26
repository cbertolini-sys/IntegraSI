import os
import subprocess
import sys

from django.conf import settings


def _importar_settings_em_subprocesso(remover=()):
    """Importa config.settings num subprocesso com ambiente limpo, fora do
    alcance de pytest-django (que força settings.DEBUG = False para toda a
    sessão de testes via setup_test_environment())."""
    ambiente = {k: v for k, v in os.environ.items() if k not in remover}
    ambiente["DJANGO_SETTINGS_MODULE"] = "config.settings"
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); from django.conf import settings; print(settings.DEBUG)",
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
