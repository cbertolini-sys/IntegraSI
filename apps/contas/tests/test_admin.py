import pytest
from django.urls import reverse

from apps.contas.admin import mascara_cpf
from apps.contas.models import Usuario


def _assert_sem_erros_do_admin(resposta):
    """Ajuda a diagnosticar falhas de validação do formulário do Admin."""
    if resposta.status_code == 200:
        assert not resposta.context["adminform"].form.errors, resposta.context[
            "adminform"
        ].form.errors


def test_mascara_esconde_os_oito_primeiros_digitos():
    assert mascara_cpf("52998224725") == "***.***.247-25"


def test_mascara_aceita_vazio():
    assert mascara_cpf("") == ""


@pytest.mark.django_db
def test_listagem_do_admin_nao_expoe_cpf_inteiro(client):
    coordenador = Usuario.objects.create_superuser(
        email="coord@ufsm.br",
        nome_completo="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        password="senha-de-teste-123",
    )
    client.force_login(coordenador)
    resposta = client.get(reverse("admin:contas_usuario_changelist"))
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "***.***.247-25" in conteudo
    assert "52998224725" not in conteudo


@pytest.mark.django_db
def test_pagina_de_adicionar_usuario_carrega(client):
    coordenador = Usuario.objects.create_superuser(
        email="coord@ufsm.br",
        nome_completo="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        password="senha-de-teste-123",
    )
    client.force_login(coordenador)
    resposta = client.get(reverse("admin:contas_usuario_add"))
    assert resposta.status_code == 200


@pytest.mark.django_db
def test_criar_aluno_pelo_admin_persiste_no_banco(client):
    coordenador = Usuario.objects.create_superuser(
        email="coord@ufsm.br",
        nome_completo="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        password="senha-de-teste-123",
    )
    client.force_login(coordenador)
    resposta = client.post(
        reverse("admin:contas_usuario_add"),
        {
            "email": "aluno@ufsm.br",
            "nome_completo": "Ana Aluna",
            "cpf": "12345678909",
            "papel": Usuario.ALUNO,
            "matricula": "2021001234",
            "siape": "",
            "usable_password": "true",
            "password1": "senha-do-aluno-2026",
            "password2": "senha-do-aluno-2026",
        },
    )
    _assert_sem_erros_do_admin(resposta)
    assert resposta.status_code == 302

    aluno = Usuario.objects.get(email="aluno@ufsm.br")
    assert aluno.papel == Usuario.ALUNO
    assert aluno.e_aluno
    assert aluno.matricula == "2021001234"
    assert aluno.check_password("senha-do-aluno-2026")

    resposta_change = client.get(
        reverse("admin:contas_usuario_change", args=[aluno.pk])
    )
    assert resposta_change.status_code == 200


@pytest.mark.django_db
def test_criar_aluno_pelo_admin_aceita_cpf_e_matricula_com_pontuacao(client):
    # Regressão: o ModelForm gera um CharField(max_length=11) para `cpf` a
    # partir do model, e essa validação de tamanho roda ANTES do
    # full_clean() do model (onde vive a normalização de pontuação). Sem os
    # campos declarados explicitamente em UsuarioCreationForm, um CPF
    # digitado com pontuação (14 caracteres) era rejeitado por "max 11
    # caracteres" antes mesmo de chegar lá.
    coordenador = Usuario.objects.create_superuser(
        email="coord@ufsm.br",
        nome_completo="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        password="senha-de-teste-123",
    )
    client.force_login(coordenador)
    resposta = client.post(
        reverse("admin:contas_usuario_add"),
        {
            "email": "aluno2@ufsm.br",
            "nome_completo": "Beatriz Aluna",
            "cpf": "123.456.789-09",
            "papel": Usuario.ALUNO,
            "matricula": "2021.001.234",
            "siape": "",
            "usable_password": "true",
            "password1": "senha-do-aluno-2026",
            "password2": "senha-do-aluno-2026",
        },
    )
    _assert_sem_erros_do_admin(resposta)
    assert resposta.status_code == 302

    aluno = Usuario.objects.get(email="aluno2@ufsm.br")
    assert aluno.cpf == "12345678909"
    assert aluno.matricula == "2021001234"


@pytest.mark.django_db
def test_admin_recusa_cpf_com_digito_verificador_errado(client):
    """UsuarioCreationForm redeclara `cpf` como um CharField solto, o que
    descarta os validators do campo do model. Os dígitos verificadores só
    sobrevivem no caminho do Admin porque _post_clean() roda
    instance.full_clean() por baixo -- uma indireção que nenhum outro teste
    da suite exercita, já que todos usam CPF válido. Este teste prova que a
    indireção continua funcionando."""
    coordenador = Usuario.objects.create_superuser(
        email="coord@ufsm.br",
        nome_completo="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        password="senha-de-teste-123",
    )
    client.force_login(coordenador)
    resposta = client.post(
        reverse("admin:contas_usuario_add"),
        {
            "email": "invalido@ufsm.br",
            "nome_completo": "CPF Invalido",
            "cpf": "529.982.247-24",
            "papel": Usuario.ALUNO,
            "matricula": "2021009999",
            "siape": "",
            "usable_password": "true",
            "password1": "senha-do-aluno-2026",
            "password2": "senha-do-aluno-2026",
        },
    )
    assert resposta.status_code == 200
    assert "cpf" in resposta.context["adminform"].form.errors
    assert not Usuario.objects.filter(email="invalido@ufsm.br").exists()


@pytest.mark.django_db
def test_admin_permite_alterar_usuario_com_cpf_de_11_digitos_ja_gravado(client):
    coordenador = Usuario.objects.create_superuser(
        email="coord@ufsm.br",
        nome_completo="Carla Costa",
        cpf="529.982.247-25",
        siape="7654321",
        password="senha-de-teste-123",
    )
    aluno = Usuario.objects.create_user(
        email="aluno3@ufsm.br",
        nome_completo="Carlos Aluno",
        cpf="123.456.789-09",
        papel=Usuario.ALUNO,
        matricula="2021005555",
        password="senha-do-aluno-2026",
    )
    assert aluno.cpf == "12345678909"
    client.force_login(coordenador)
    resposta = client.post(
        reverse("admin:contas_usuario_change", args=[aluno.pk]),
        {
            "email": aluno.email,
            "nome_completo": "Carlos Aluno da Silva",
            "cpf": aluno.cpf,
            "papel": Usuario.ALUNO,
            "matricula": aluno.matricula,
            "siape": "",
            "is_active": "on",
        },
    )
    _assert_sem_erros_do_admin(resposta)
    assert resposta.status_code == 302
    aluno.refresh_from_db()
    assert aluno.cpf == "12345678909"
    assert aluno.nome_completo == "Carlos Aluno da Silva"
