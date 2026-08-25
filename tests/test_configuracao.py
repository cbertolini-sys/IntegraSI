from django.conf import settings


def test_debug_desligado_por_padrao():
    assert settings.DEBUG is False


def test_banco_e_postgresql():
    assert "postgresql" in settings.DATABASES["default"]["ENGINE"]


def test_idioma_e_fuso_do_projeto():
    assert settings.LANGUAGE_CODE == "pt-br"
    assert settings.TIME_ZONE == "America/Sao_Paulo"
    assert settings.USE_TZ is True
