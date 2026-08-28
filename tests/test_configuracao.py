import os
import subprocess
import sys

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
