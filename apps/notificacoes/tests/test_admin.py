import pytest
from django.contrib import admin
from django.urls import reverse

from apps.contas.models import Usuario
from apps.notificacoes.admin import NotificacaoAdmin
from apps.notificacoes.models import Notificacao
from apps.notificacoes.services import LIMITE_TENTATIVAS


@pytest.fixture
def operador(db):
    usuario = Usuario.objects.create_user(
        email="coord@ufsm.br", nome_completo="Carla Costa", cpf="529.982.247-25",
        papel=Usuario.COORDENADOR, siape="7654321", password="senha-de-teste-123",
    )
    usuario.is_staff = True
    usuario.is_superuser = True
    usuario.save(update_fields=["is_staff", "is_superuser"])
    return usuario


@pytest.fixture
def fila(db):
    pendente = Notificacao.objects.create(
        destinatario="pendente@ufsm.br", assunto="Entregável devolvido",
        corpo="Confira.", evento="ENTREGAVEL_DEVOLVIDO",
    )
    esgotada = Notificacao.objects.create(
        destinatario="esgotada@ufsm.br", assunto="Curso publicado", corpo="Saiu.",
        evento="CURSO_PUBLICADO", tentativas=LIMITE_TENTATIVAS,
        ultimo_erro="SMTPAuthenticationError: " + "x" * 500,
    )
    enviada = Notificacao.objects.create(
        destinatario="enviada@ufsm.br", assunto="Curso submetido", corpo="Chegou.",
        evento="CURSO_SUBMETIDO", tentativas=1,
    )
    from django.utils import timezone

    Notificacao.objects.filter(pk=enviada.pk).update(enviado_em=timezone.now())
    return {"pendente": pendente, "esgotada": esgotada, "enviada": enviada}


# Regra 16
def test_notificacao_esta_registrada_no_admin():
    assert Notificacao in admin.site._registry


# Regra 17
def test_a_lista_mostra_os_campos_que_o_operador_precisa():
    """Fila travada sem estes campos e igual a fila nenhuma: e por `tentativas`,
    `enviado_em` e `ultimo_erro` que se descobre que o SMTP caiu."""
    for campo in ["destinatario", "evento", "tentativas", "enviado_em"]:
        assert campo in NotificacaoAdmin.list_display
    assert "erro_resumido" in NotificacaoAdmin.list_display


# Regra 18
@pytest.mark.django_db
def test_a_lista_abre_e_mostra_o_ultimo_erro_encurtado(client, operador, fila):
    client.force_login(operador)
    resposta = client.get(reverse("admin:notificacoes_notificacao_changelist"))
    assert resposta.status_code == 200
    corpo = resposta.content.decode()
    assert "esgotada@ufsm.br" in corpo
    assert "SMTPAuthenticationError" in corpo
    # Encurtado: os 500 caracteres do erro nao vao inteiros para a coluna.
    assert "x" * 500 not in corpo


# Regra 19
@pytest.mark.django_db
@pytest.mark.parametrize(
    "situacao,esperado",
    [
        ("pendente", ["pendente@ufsm.br"]),
        ("esgotada", ["esgotada@ufsm.br"]),
        ("enviada", ["enviada@ufsm.br"]),
    ],
)
def test_o_filtro_de_situacao_separa_a_fila(client, operador, fila, situacao, esperado):
    """A notificacao esgotada e a que importa: ela saiu do filtro do cron e nunca
    mais sera tentada, entao nada alem desta tela avisa que ela existe."""
    client.force_login(operador)
    resposta = client.get(
        reverse("admin:notificacoes_notificacao_changelist"), {"situacao": situacao}
    )
    assert resposta.status_code == 200
    destinatarios = list(
        resposta.context["cl"].queryset.values_list("destinatario", flat=True)
    )
    assert destinatarios == esperado


# Regra 20
@pytest.mark.django_db
def test_o_admin_nao_deixa_criar_notificacao_a_mao(client, operador):
    """Enfileirar pelo Admin pularia `services.enfileirar`, unico lugar que sabe
    montar assunto e corpo de um evento."""
    client.force_login(operador)
    resposta = client.get(reverse("admin:notificacoes_notificacao_add"))
    assert resposta.status_code == 403


# Regra 21
@pytest.mark.django_db
def test_o_admin_nao_deixa_editar_a_fila(client, operador, fila):
    """`enviado_em` limpo a mao reenvia o e-mail; `tentativas` zerado a mao
    ressuscita a notificacao sem passar por service nenhum (R56)."""
    client.force_login(operador)
    url = reverse("admin:notificacoes_notificacao_change", args=[fila["esgotada"].pk])

    leitura = client.get(url)
    assert leitura.status_code == 200
    assert not leitura.context["has_change_permission"]

    # 403 e nao "gravou sem mudar nada": a recusa tem que ser da permissao. Se ela
    # viesse de todos os campos serem readonly, o POST voltaria 302 e o registro
    # ficaria intacto -- indistinguivel de nao haver guarda nenhuma.
    resposta = client.post(url, {"tentativas": 0, "destinatario": "outro@ufsm.br"})
    assert resposta.status_code == 403
    fila["esgotada"].refresh_from_db()
    assert fila["esgotada"].tentativas == LIMITE_TENTATIVAS
    assert fila["esgotada"].destinatario == "esgotada@ufsm.br"
