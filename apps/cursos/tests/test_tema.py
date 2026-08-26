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


@pytest.mark.django_db
def test_fixture_carrega_temas_iniciais_ativos():
    from django.core.management import call_command

    call_command("loaddata", "temas_iniciais")
    assert Tema.objects.filter(ativo=True).count() == 5
    assert Tema.objects.filter(slug="ia-na-educacao").exists()
