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
