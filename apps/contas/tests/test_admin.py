import pytest
from django.urls import reverse

from apps.contas.admin import mascara_cpf
from apps.contas.models import Usuario


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
            # O campo do model tem max_length=11: o Admin exige o CPF ja em
            # digitos (sem pontuacao) porque a normalizacao so acontece no
            # full_clean() do model, que roda depois da validacao de campo do form.
            "cpf": "12345678909",
            "papel": Usuario.ALUNO,
            "matricula": "2021001234",
            "siape": "",
            "usable_password": "true",
            "password1": "senha-do-aluno-2026",
            "password2": "senha-do-aluno-2026",
        },
    )
    if resposta.status_code == 200:
        # Ajuda a diagnosticar falhas de validacao do formulario do Admin.
        assert not resposta.context["adminform"].form.errors, resposta.context[
            "adminform"
        ].form.errors
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
