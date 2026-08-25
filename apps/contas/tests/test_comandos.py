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
