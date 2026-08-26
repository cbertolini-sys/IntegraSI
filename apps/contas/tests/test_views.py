import pytest
from django.urls import reverse

from apps.contas.models import Usuario


@pytest.fixture
def aluno(db):
    return Usuario.objects.create_user(
        email="aluno@ufsm.br",
        nome_completo="Ana Alves",
        cpf="529.982.247-25",
        papel=Usuario.ALUNO,
        matricula="201910101",
        password="senha-de-teste-123",
    )


@pytest.mark.django_db
def test_painel_exige_login(client):
    resposta = client.get(reverse("painel"))
    assert resposta.status_code == 302
    assert reverse("login") in resposta.url


def test_painel_sauda_pelo_nome_e_mostra_o_papel(client, aluno):
    client.force_login(aluno)
    resposta = client.get(reverse("painel"))
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Ana Alves" in conteudo
    assert "Aluno" in conteudo


def test_painel_nunca_mostra_cpf(client, aluno):
    client.force_login(aluno)
    resposta = client.get(reverse("painel"))
    assert "52998224725" not in resposta.content.decode()


def test_login_com_email_e_senha(client, aluno):
    resposta = client.post(
        reverse("login"),
        {"username": "aluno@ufsm.br", "password": "senha-de-teste-123"},
    )
    assert resposta.status_code == 302
    assert resposta.url == reverse("painel")


def test_login_funciona_de_ponta_a_ponta_e_grava_last_login(client, aluno):
    # django.contrib.auth grava o login com save(update_fields=["last_login"]);
    # este teste é a garantia de que o fluxo real (não só a chamada isolada ao
    # model) segue funcionando depois da guarda de update_fields em Usuario.save().
    assert aluno.last_login is None
    resposta = client.post(
        reverse("login"),
        {"username": "aluno@ufsm.br", "password": "senha-de-teste-123"},
    )
    assert resposta.status_code == 302
    aluno.refresh_from_db()
    assert aluno.last_login is not None
