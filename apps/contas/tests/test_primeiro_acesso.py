import uuid

import pytest
from django.urls import reverse

from apps.contas import services
from apps.contas.models import Usuario


@pytest.fixture
def convite(db, professor):
    aluno = Usuario.objects.create_user(
        email="novo@acad.ufsm.br", nome_completo="Novo Aluno",
        cpf=None, papel=Usuario.ALUNO, password=None,
    )
    return services.convidar(aluno, por=professor)


def dados_validos():
    return {
        "senha": "uma-senha-de-verdade-123",
        "confirmacao": "uma-senha-de-verdade-123",
        "cpf": "071.620.218-24",
        "matricula": "201910101",
        "telefone": "(55) 99999-1234",
    }


@pytest.mark.django_db
def test_pagina_do_convite_abre_sem_login(client, convite):
    """Quem chega aqui ainda não tem senha: exigir login seria um beco."""
    resposta = client.get(reverse("primeiro_acesso", args=[convite.token]))
    assert resposta.status_code == 200


@pytest.mark.django_db
def test_completar_o_perfil_e_entrar(client, convite):
    resposta = client.post(
        reverse("primeiro_acesso", args=[convite.token]), dados_validos(), follow=True
    )
    assert resposta.status_code == 200
    convite.usuario.refresh_from_db()
    assert convite.usuario.perfil_completo is True
    assert resposta.context["user"].is_authenticated


@pytest.mark.django_db
def test_senhas_diferentes_sao_recusadas(client, convite):
    dados = dados_validos()
    dados["confirmacao"] = "outra-coisa-completamente"
    client.post(reverse("primeiro_acesso", args=[convite.token]), dados)
    convite.usuario.refresh_from_db()
    assert convite.usuario.perfil_completo is False


@pytest.mark.django_db
def test_cpf_invalido_e_recusado_no_proprio_campo(client, convite):
    dados = dados_validos()
    dados["cpf"] = "111.111.111-11"
    resposta = client.post(reverse("primeiro_acesso", args=[convite.token]), dados)
    assert resposta.status_code == 200
    convite.usuario.refresh_from_db()
    assert convite.usuario.perfil_completo is False


@pytest.mark.django_db
def test_token_invalido_mostra_pagina_propria(client):
    resposta = client.get(reverse("primeiro_acesso", args=[uuid.uuid4()]))
    assert resposta.status_code == 200
    assert "não vale mais" in resposta.content.decode()


@pytest.mark.django_db
def test_convite_ja_usado_nao_abre_de_novo(client, convite):
    client.post(reverse("primeiro_acesso", args=[convite.token]), dados_validos(), follow=True)
    resposta = client.get(reverse("primeiro_acesso", args=[convite.token]))
    assert "não vale mais" in resposta.content.decode()


@pytest.mark.django_db
def test_metodo_errado_e_rejeitado(client, convite):
    assert client.delete(reverse("primeiro_acesso", args=[convite.token])).status_code == 405


@pytest.mark.django_db
def test_perfil_incompleto_so_alcanca_a_propria_tela(client, convite):
    """Decisão do coordenador: enquanto não completa, o aluno é levado de volta.
    Meio-estado -- produzir material sem CPF -- não existe."""
    client.force_login(convite.usuario)
    resposta = client.get(reverse("meus_cursos"))
    assert resposta.status_code == 302
    assert str(convite.token) in resposta.url


@pytest.mark.django_db
def test_perfil_completo_circula_normalmente(client, convite):
    services.consumir_convite(
        convite.token, senha="uma-senha-de-verdade-123",
        cpf="071.620.218-24", matricula="201910101", telefone="(55) 99999-1234",
    )
    convite.usuario.refresh_from_db()
    client.force_login(convite.usuario)
    assert client.get(reverse("meus_cursos")).status_code == 200


@pytest.mark.django_db
def test_o_portao_nao_prende_o_logout(client, convite):
    """Sem esta exceção, quem entra com o cadastro pela metade não consegue nem
    sair da conta.

    A asserção é sobre a SESSÃO, e não sobre o código HTTP: o portão também
    responde 302, então `status_code in (200, 302)` passava com "logout" fora das
    liberadas -- a pessoa era redirecionada para o convite e seguia logada, e o
    teste não via diferença (conferido por mutação).
    """
    client.force_login(convite.usuario)
    client.post(reverse("logout"))
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_o_portao_nao_prende_o_catalogo_publico(client, convite):
    """O catálogo é público: prender alguém logado nele seria pior que não ter
    login nenhum."""
    client.force_login(convite.usuario)
    assert client.get(reverse("catalogo")).status_code == 200


@pytest.mark.django_db
def test_quem_nao_tem_convite_pendente_circula(client, aluno):
    """Contas antigas -- criadas antes do Plano 5, ou pelo Admin -- podem estar
    sem telefone e não têm convite nenhum. O portão não pode trancá-las fora do
    sistema: sem convite não há para onde redirecionar."""
    assert aluno.perfil_completo is False
    client.force_login(aluno)
    assert client.get(reverse("meus_cursos")).status_code == 200
