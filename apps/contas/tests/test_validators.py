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
