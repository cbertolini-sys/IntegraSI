"""Esqueci minha senha, redefinir por e-mail.

Mesmo desenho do convite de primeiro acesso (token com prazo, uso único, e-mail
pela fila de `notificacoes`), mas duas metades separadas de propósito, porque
`ConviteAluno` já registra por que as duas políticas não podem morar na mesma
chave (ver `RedefinicaoDeSenha`):

 1. O token dura duas horas, e não sete dias.
 2. É uso único.
 3. Pedir de novo invalida o token anterior.
 4. E-mail que não bate com ninguém não estoura erro, e não enfileira nada --
    e não vira `RedefinicaoDeSenha` nenhuma, porque não há usuário para ligar.
 5. Conta desativada não recebe o link: `is_active=False` já barra o login por
    outro caminho, e mandar um e-mail ali só confirmaria pra fora que a conta
    existe e está desativada.
 6. Conta sem senha ainda (convite de primeiro acesso pendente) também não
    recebe: quem está nesse caso precisa do link de convite, não deste.
 7. Senha fraca é recusada na hora de redefinir, pela mesma
    `validate_password` do primeiro acesso.
 8. Token vencido é recusado.
 9. Token inexistente é recusado.
10. Redefinir com sucesso troca a senha de verdade: a antiga para de entrar, a
    nova entra.
11. A resposta da TELA (`esqueci_senha`) é sempre a mesma frase, exista ou não
    a conta -- o mesmo princípio que `LoginComLimite` já aplica.
12. Limite de cinco pedidos por IP por hora, GET nunca bloqueado.
13. Sucesso na redefinição loga a pessoa e manda pro painel, como o convite.
14. `PerfilCompletoMiddleware` libera as duas telas novas.
"""

import datetime

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.contas import services
from apps.contas.models import RedefinicaoDeSenha, TentativaDeRedefinicao, Usuario
from apps.contas.views import LIMITE_DE_PEDIDOS_POR_HORA
from apps.notificacoes.models import Notificacao

SENHA_ANTIGA = "senha-de-teste-123"


@pytest.fixture
def pessoa(db):
    return Usuario.objects.create_user(
        email="ana@ufsm.br", nome_completo="Ana Alves",
        cpf="529.982.247-25", papel=Usuario.ALUNO, matricula="201910101",
        password=SENHA_ANTIGA,
    )


@pytest.fixture
def desativada(db):
    u = Usuario.objects.create_user(
        email="desativada@ufsm.br", nome_completo="Conta Desativada",
        cpf="071.620.218-24", papel=Usuario.ALUNO, matricula="201910102",
        password=SENHA_ANTIGA,
    )
    u.is_active = False
    u.save(update_fields=["is_active"])
    return u


@pytest.fixture
def sem_senha_ainda(db):
    """Uma conta que a coordenação criou e o convite ainda não foi aberto --
    tem e-mail, não tem senha utilizável."""
    return Usuario.objects.create_user(
        email="pendente@ufsm.br", nome_completo="",
        cpf=None, papel=Usuario.PROFESSOR, password=None,
    )


# --- Regras de servico ---------------------------------------------------------


@pytest.mark.django_db
def test_o_token_dura_duas_horas(pessoa):
    redefinicao = services.solicitar_redefinicao_de_senha(pessoa.email)
    esperado = timezone.now() + datetime.timedelta(hours=2)
    assert abs((redefinicao.expira_em - esperado).total_seconds()) < 60
    assert redefinicao.valido is True


@pytest.mark.django_db
def test_avisa_por_e_mail(pessoa):
    services.solicitar_redefinicao_de_senha(pessoa.email)
    fila = Notificacao.objects.filter(destinatario=pessoa.email)
    assert fila.count() == 1


@pytest.mark.django_db
def test_o_e_mail_leva_o_token_e_nao_a_senha_atual(pessoa):
    redefinicao = services.solicitar_redefinicao_de_senha(pessoa.email)
    corpo = Notificacao.objects.get(destinatario=pessoa.email).corpo
    assert str(redefinicao.token) in corpo
    assert pessoa.password not in corpo


@pytest.mark.django_db
def test_e_mail_inexistente_nao_gera_token_nem_e_mail(db):
    resultado = services.solicitar_redefinicao_de_senha("ninguem@ufsm.br")
    assert resultado is None
    assert RedefinicaoDeSenha.objects.count() == 0
    assert Notificacao.objects.count() == 0


@pytest.mark.django_db
def test_conta_desativada_nao_recebe_o_link(desativada):
    resultado = services.solicitar_redefinicao_de_senha(desativada.email)
    assert resultado is None
    assert RedefinicaoDeSenha.objects.count() == 0
    assert Notificacao.objects.count() == 0


@pytest.mark.django_db
def test_conta_sem_senha_ainda_nao_recebe_o_link(sem_senha_ainda):
    """Quem nunca completou o primeiro acesso precisa do convite, nao deste
    link: nao ha senha antiga para redefinir."""
    resultado = services.solicitar_redefinicao_de_senha(sem_senha_ainda.email)
    assert resultado is None
    assert RedefinicaoDeSenha.objects.count() == 0
    assert Notificacao.objects.count() == 0


@pytest.mark.django_db
def test_redefinir_troca_a_senha(pessoa):
    redefinicao = services.solicitar_redefinicao_de_senha(pessoa.email)
    services.redefinir_senha(redefinicao.token, "uma-senha-nova-de-verdade-456")
    pessoa.refresh_from_db()
    assert pessoa.check_password("uma-senha-nova-de-verdade-456")
    assert not pessoa.check_password(SENHA_ANTIGA)


@pytest.mark.django_db
def test_redefinicao_e_de_uso_unico(pessoa):
    redefinicao = services.solicitar_redefinicao_de_senha(pessoa.email)
    services.redefinir_senha(redefinicao.token, "uma-senha-nova-de-verdade-456")
    with pytest.raises(ValidationError):
        services.redefinir_senha(redefinicao.token, "outra-senha-qualquer-789")


@pytest.mark.django_db
def test_token_vencido_e_recusado(pessoa):
    redefinicao = services.solicitar_redefinicao_de_senha(pessoa.email)
    RedefinicaoDeSenha.objects.filter(pk=redefinicao.pk).update(
        expira_em=timezone.now() - datetime.timedelta(minutes=1)
    )
    with pytest.raises(ValidationError):
        services.redefinir_senha(redefinicao.token, "uma-senha-nova-de-verdade-456")


@pytest.mark.django_db
def test_token_inexistente_e_recusado(db):
    import uuid

    with pytest.raises(ValidationError):
        services.redefinir_senha(uuid.uuid4(), "uma-senha-nova-de-verdade-456")


@pytest.mark.django_db
def test_senha_fraca_e_recusada(pessoa):
    redefinicao = services.solicitar_redefinicao_de_senha(pessoa.email)
    with pytest.raises(ValidationError):
        services.redefinir_senha(redefinicao.token, "123")
    pessoa.refresh_from_db()
    assert pessoa.check_password(SENHA_ANTIGA), "a senha antiga nao pode ter sido trocada"


@pytest.mark.django_db
def test_pedir_de_novo_invalida_o_token_anterior(pessoa):
    primeiro = services.solicitar_redefinicao_de_senha(pessoa.email)
    segundo = services.solicitar_redefinicao_de_senha(pessoa.email)
    primeiro.refresh_from_db()
    assert primeiro.valido is False
    assert segundo.valido is True
    with pytest.raises(ValidationError):
        services.redefinir_senha(primeiro.token, "uma-senha-nova-de-verdade-456")


# --- A tela: mensagem generica e limite por IP ----------------------------------


def pede(client, email, ip="203.0.113.7"):
    return client.post(
        reverse("esqueci_senha"), {"email": email}, HTTP_X_FORWARDED_FOR=ip
    )


@pytest.mark.django_db
def test_a_tela_diz_a_mesma_coisa_para_conta_que_existe_e_que_nao_existe(client, pessoa):
    """O mesmo principio que `LoginComLimite` ja aplica: a resposta nao pode
    virar oraculo de e-mails validos."""
    conhecida = pede(client, pessoa.email, ip="203.0.113.10").content.decode()
    desconhecida = pede(client, "ninguem@ufsm.br", ip="203.0.113.11").content.decode()
    assert conhecida == desconhecida


@pytest.mark.django_db
def test_pedir_de_verdade_enfileira_o_e_mail(client, pessoa):
    pede(client, pessoa.email)
    assert Notificacao.objects.filter(destinatario=pessoa.email).count() == 1


@pytest.mark.django_db
def test_o_limite_por_ip_bloqueia_depois_de_cinco(client, pessoa):
    """O limite e conferido ANTES de olhar o e-mail, como em `LoginComLimite`:
    a mensagem de bloqueio e sempre a mesma, e por isso pode ser distinta da
    mensagem de sucesso sem virar oraculo -- ela nao diz nada sobre a conta."""
    for _ in range(LIMITE_DE_PEDIDOS_POR_HORA):
        pede(client, pessoa.email)
    antes = Notificacao.objects.filter(destinatario=pessoa.email).count()
    resposta = pede(client, pessoa.email)
    depois = Notificacao.objects.filter(destinatario=pessoa.email).count()
    assert depois == antes, "o sexto pedido nao pode ter enfileirado outro e-mail"
    assert "muitas" in resposta.content.decode().lower()


@pytest.mark.django_db
def test_o_limite_conta_por_ip_e_nao_por_e_mail(client, pessoa):
    for n in range(LIMITE_DE_PEDIDOS_POR_HORA):
        pede(client, f"pessoa{n}@ufsm.br")
    antes = Notificacao.objects.filter(destinatario=pessoa.email).count()
    pede(client, pessoa.email)
    assert Notificacao.objects.filter(destinatario=pessoa.email).count() == antes


@pytest.mark.django_db
def test_outro_ip_nao_herda_o_bloqueio(client, pessoa):
    for _ in range(LIMITE_DE_PEDIDOS_POR_HORA):
        pede(client, pessoa.email)
    pede(client, pessoa.email, ip="198.51.100.9")
    assert Notificacao.objects.filter(destinatario=pessoa.email).count() == LIMITE_DE_PEDIDOS_POR_HORA + 1


@pytest.mark.django_db
def test_o_get_da_tela_nunca_e_bloqueado(client, pessoa):
    for _ in range(LIMITE_DE_PEDIDOS_POR_HORA + 5):
        pede(client, pessoa.email)
    assert client.get(reverse("esqueci_senha")).status_code == 200


@pytest.mark.django_db
def test_a_tentativa_nao_guarda_o_e_mail_digitado(client, pessoa):
    pede(client, "alguem@exemplo.org")
    campos = {c.name for c in TentativaDeRedefinicao._meta.get_fields()}
    assert "email" not in campos
    assert campos >= {"ip", "criado_em"}


# --- A tela de redefinir: token invalido, sucesso, login automatico ------------


@pytest.mark.django_db
def test_token_invalido_mostra_a_tela_de_link_vencido_e_nao_quebra(client):
    import uuid

    resposta = client.get(reverse("redefinir_senha", args=[uuid.uuid4()]))
    assert resposta.status_code == 200
    assert "não vale mais" in resposta.content.decode().lower()


@pytest.mark.django_db
def test_redefinir_com_sucesso_loga_a_pessoa_e_manda_ao_painel(client, pessoa):
    redefinicao = services.solicitar_redefinicao_de_senha(pessoa.email)
    resposta = client.post(
        reverse("redefinir_senha", args=[redefinicao.token]),
        {"senha": "uma-senha-nova-de-verdade-456", "confirmacao": "uma-senha-nova-de-verdade-456"},
    )
    assert resposta.status_code == 302
    assert resposta.url == reverse("painel")
    assert "_auth_user_id" in client.session


@pytest.mark.django_db
def test_confirmacao_diferente_e_recusada_no_formulario(client, pessoa):
    redefinicao = services.solicitar_redefinicao_de_senha(pessoa.email)
    resposta = client.post(
        reverse("redefinir_senha", args=[redefinicao.token]),
        {"senha": "uma-senha-nova-de-verdade-456", "confirmacao": "outra-coisa-completamente-diferente"},
    )
    assert resposta.status_code == 200
    assert "_auth_user_id" not in client.session
    pessoa.refresh_from_db()
    assert pessoa.check_password(SENHA_ANTIGA)


# --- A porta do login e o middleware --------------------------------------------


@pytest.mark.django_db
def test_a_tela_de_login_tem_o_link(client):
    resposta = client.get(reverse("login"))
    assert reverse("esqueci_senha") in resposta.content.decode()


@pytest.mark.django_db
def test_perfil_incompleto_ainda_alcanca_as_duas_telas_novas(client):
    """`PerfilCompletoMiddleware` prende quem tem convite pendente na propria
    tela; sem liberar estas duas, a pessoa presa nao conseguiria nem pedir a
    redefinicao nem abrir o link que recebeu."""
    from apps.contas.middleware import PerfilCompletoMiddleware

    assert "esqueci_senha" in PerfilCompletoMiddleware.LIBERADAS
    assert "redefinir_senha" in PerfilCompletoMiddleware.LIBERADAS
