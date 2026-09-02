"""Limite de tentativas de login, por IP.

A solicitacao publica ja limitava cinco pedidos por IP por hora; o login, que e a
porta de todo o resto, aceitava tentativas sem conta. Os e-mails sao
institucionais e portanto adivinhaveis.

Conta por IP e ignora o e-mail tentado, a pedido: sem isso, quem gira a lista de
enderecos do mesmo lugar ganha cota nova a cada endereco.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.contas.models import TentativaDeLogin, Usuario
from apps.contas.views import JANELA_DE_TENTATIVAS, LIMITE_DE_TENTATIVAS

SENHA = "senha-de-teste-123"


@pytest.fixture
def pessoa(db):
    return Usuario.objects.create_user(
        email="ana@ufsm.br",
        nome_completo="Ana Alves",
        cpf="529.982.247-25",
        papel=Usuario.ALUNO,
        matricula="201910101",
        password=SENHA,
    )


def tenta(client, email="ana@ufsm.br", senha="errada", ip="203.0.113.7"):
    return client.post(
        reverse("login"),
        {"username": email, "password": senha},
        HTTP_X_FORWARDED_FOR=ip,
    )


@pytest.mark.django_db
def test_a_senha_certa_entra_normalmente(client, pessoa):
    resposta = tenta(client, senha=SENHA)
    assert resposta.status_code == 302


@pytest.mark.django_db
def test_depois_do_limite_ate_a_senha_certa_e_recusada(client, pessoa):
    """O ponto do limite: quem acerta na tentativa 40 nao pode entrar."""
    for _ in range(LIMITE_DE_TENTATIVAS):
        tenta(client)
    resposta = tenta(client, senha=SENHA)
    assert resposta.status_code == 200
    assert "muitas tentativas" in resposta.content.decode().lower()
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_o_limite_conta_qualquer_e_mail(client, pessoa):
    """Girar a lista de enderecos do mesmo lugar nao pode dar cota nova."""
    for n in range(LIMITE_DE_TENTATIVAS):
        tenta(client, email=f"pessoa{n}@ufsm.br")
    resposta = tenta(client, senha=SENHA)
    assert resposta.status_code == 200
    assert "muitas tentativas" in resposta.content.decode().lower()


@pytest.mark.django_db
def test_outro_ip_nao_herda_o_bloqueio(client, pessoa):
    for _ in range(LIMITE_DE_TENTATIVAS):
        tenta(client)
    assert tenta(client, senha=SENHA, ip="198.51.100.4").status_code == 302


@pytest.mark.django_db
def test_tentativa_velha_nao_conta(client, pessoa):
    """A janela desliza: quem errou ontem nao carrega isso para hoje."""
    for _ in range(LIMITE_DE_TENTATIVAS):
        tenta(client)
    antes = timezone.now() - JANELA_DE_TENTATIVAS - datetime.timedelta(minutes=1)
    TentativaDeLogin.objects.update(criado_em=antes)
    assert tenta(client, senha=SENHA).status_code == 302


@pytest.mark.django_db
def test_a_recusa_nao_diz_se_a_conta_existe(client, pessoa):
    """Mesma resposta para conta que existe e conta que nao existe: a diferenca
    seria um oraculo de enderecos validos."""
    for _ in range(LIMITE_DE_TENTATIVAS):
        tenta(client)
    conhecida = tenta(client, email="ana@ufsm.br").content.decode()
    desconhecida = tenta(client, email="ninguem@ufsm.br").content.decode()
    assert "muitas tentativas" in conhecida.lower()
    assert "muitas tentativas" in desconhecida.lower()


@pytest.mark.django_db
def test_a_tentativa_nao_guarda_o_e_mail_digitado(client, pessoa):
    """O que a regra precisa e o IP e a hora. O endereco digitado num formulario
    publico pode ser de terceiro, ou um erro de digitacao, e guardar isso e dado
    pessoal que a regra nao usa."""
    tenta(client, email="alguem@exemplo.org")
    campos = {c.name for c in TentativaDeLogin._meta.get_fields()}
    assert "email" not in campos
    assert campos >= {"ip", "criado_em"}


@pytest.mark.django_db
def test_o_ip_vem_do_ultimo_elemento_da_cadeia(client, pessoa):
    """Herdado do ajudante que a solicitacao ja usava: cada proxy ACRESCENTA ao
    fim, entao o primeiro elemento e texto que o cliente mandou. Ler o primeiro
    entregaria o limite a quem inventasse um IP por requisicao."""
    for _ in range(LIMITE_DE_TENTATIVAS):
        client.post(
            reverse("login"),
            {"username": "ana@ufsm.br", "password": "errada"},
            HTTP_X_FORWARDED_FOR="9.9.9.9, 203.0.113.7",
        )
    resposta = client.post(
        reverse("login"),
        {"username": "ana@ufsm.br", "password": SENHA},
        HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.7",
    )
    assert resposta.status_code == 200, "o IP inventado no inicio deu cota nova"


@pytest.mark.django_db
def test_o_get_da_tela_de_login_nunca_e_bloqueado(client, pessoa):
    """Bloquear a propria tela deixaria a pessoa sem nem ler a mensagem."""
    for _ in range(LIMITE_DE_TENTATIVAS + 5):
        tenta(client)
    assert client.get(reverse("login")).status_code == 200
