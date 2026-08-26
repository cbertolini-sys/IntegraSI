import io

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


@pytest.mark.django_db
def test_email_de_aluno_existente_e_promovido_a_coordenador_em_vez_de_ter_a_senha_trocada():
    """O comando é a única rota de recuperação de acesso e roda sob estresse, por
    alguém trancado para fora do sistema. Se o e-mail informado já pertencer a um
    aluno ou professor, o comando NÃO pode se limitar a resetar a senha dessa
    outra pessoa e dizer que "funcionou" -- precisa promovê-la a coordenador,
    explicitamente, ou falhar. Este teste crava a promoção."""
    aluno = Usuario.objects.create_user(
        email="aluno@ufsm.br",
        nome_completo="Ana Aluna",
        cpf="529.982.247-25",
        papel=Usuario.ALUNO,
        matricula="201910101",
        password="senha-antiga-do-aluno",
    )
    saida = io.StringIO()
    call_command(
        "criar_coordenador",
        email="aluno@ufsm.br",
        nome="Ana Aluna",
        cpf="529.982.247-25",
        siape="7654321",
        senha="senha-nova-do-coordenador",
        stdout=saida,
    )
    aluno.refresh_from_db()
    assert aluno.e_coordenador
    assert aluno.is_staff and aluno.is_superuser
    assert aluno.matricula is None
    assert aluno.siape == "7654321"
    assert aluno.check_password("senha-nova-do-coordenador")
    assert Usuario.objects.filter(email="aluno@ufsm.br").count() == 1
    assert "promovido" in saida.getvalue().lower()


@pytest.mark.django_db
def test_reset_de_senha_de_coordenador_existente_reporta_o_caminho_de_reset():
    call_command(
        "criar_coordenador",
        email="coord@ufsm.br",
        nome="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        senha="senha-de-teste-123",
    )
    saida = io.StringIO()
    call_command(
        "criar_coordenador",
        email="coord@ufsm.br",
        nome="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        senha="outra-senha-456",
        stdout=saida,
    )
    coordenador = Usuario.objects.get(email="coord@ufsm.br")
    assert coordenador.check_password("outra-senha-456")
    mensagem = saida.getvalue().lower()
    assert "atualizada" in mensagem
    assert "promovido" not in mensagem
