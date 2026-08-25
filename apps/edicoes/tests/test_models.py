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


@pytest.mark.django_db
def test_resalvar_edicao_ativa_nao_levanta():
    edicao = criar_edicao()
    edicao.descricao = "Descricao alterada"
    edicao.save()
    assert Edicao.objects.get(pk=edicao.pk).descricao == "Descricao alterada"


@pytest.mark.django_db
def test_data_fim_igual_data_inicio_e_recusada():
    with pytest.raises(ValidationError):
        criar_edicao(data_fim=datetime.date(2026, 8, 1))
