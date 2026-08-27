import fcntl
import io
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.notificacoes import services
from apps.notificacoes.management.commands import enviar_notificacoes as comando
from apps.notificacoes.models import Notificacao


@pytest.mark.django_db
def test_enfileirar_cria_uma_notificacao_por_destinatario():
    services.enfileirar(
        evento="ENTREGAVEL_DEVOLVIDO",
        destinatarios=["a@ufsm.br", "b@ufsm.br"],
        assunto="Entregavel devolvido",
        corpo="Confira a devolutiva.",
    )
    assert Notificacao.objects.count() == 2
    assert Notificacao.objects.filter(enviado_em__isnull=True).count() == 2


@pytest.mark.django_db
def test_enfileirar_ignora_destinatario_vazio():
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br", "", None], assunto="A", corpo="B")
    assert Notificacao.objects.count() == 1


@pytest.mark.django_db
def test_comando_envia_e_marca_como_enviada(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="Assunto", corpo="Corpo")
    call_command("enviar_notificacoes")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "Assunto"
    assert Notificacao.objects.filter(enviado_em__isnull=False).count() == 1


@pytest.mark.django_db
def test_comando_respeita_o_tamanho_do_lote(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(
        evento="X", destinatarios=[f"a{n}@ufsm.br" for n in range(5)], assunto="A", corpo="B"
    )
    call_command("enviar_notificacoes", lote=2)
    assert Notificacao.objects.filter(enviado_em__isnull=False).count() == 2


@pytest.mark.django_db
def test_falha_de_envio_registra_o_erro_e_nao_marca_como_enviada(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="A", corpo="B")
    with mock.patch("apps.notificacoes.management.commands.enviar_notificacoes.send_mail",
                    side_effect=OSError("smtp fora do ar")):
        call_command("enviar_notificacoes")
    notificacao = Notificacao.objects.get()
    assert notificacao.enviado_em is None
    assert notificacao.tentativas == 1
    assert "smtp" in notificacao.ultimo_erro


@pytest.mark.django_db
def test_notificacao_no_limite_de_tentativas_e_abandonada(settings):
    assert services.LIMITE_TENTATIVAS == 5
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="A", corpo="B")
    Notificacao.objects.update(tentativas=services.LIMITE_TENTATIVAS)
    call_command("enviar_notificacoes")
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_comando_nao_envia_quando_outra_execucao_esta_em_andamento(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="A", corpo="B")
    saida = io.StringIO()
    with open(comando.TRAVA, "w") as trava:
        # flock() trava a descricao de arquivo aberta, nao o processo: um segundo
        # descritor sobre o mesmo arquivo, mesmo neste mesmo processo de teste,
        # falha ao adquirir a trava exatamente como uma execucao concorrente do
        # cron falharia.
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        call_command("enviar_notificacoes", stdout=saida)
    assert len(mail.outbox) == 0
    assert "Outra execução" in saida.getvalue()


@pytest.mark.django_db
def test_notificacao_ja_enviada_nao_e_reenviada_nas_passadas_seguintes(settings):
    """O cron passa a cada minuto. Sem `enviado_em__isnull=True` no filtro de
    _enviar, toda notificacao ja entregue volta para a fila a cada passada e o
    destinatario recebe o mesmo aviso ate `tentativas` bater no limite - cinco
    copias de cada submissao, publicacao, devolucao e solicitacao.

    Os dois testes vizinhos que exercitam o comando o chamam uma vez so, e por
    isso passavam com essa metade do filtro apagada (achado da revisao de
    branch). Chamar tres vezes e o que prende a regra: uma passada nao consegue
    distinguir "nao reenvia" de "enviou agora".
    """
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="A", corpo="B")
    for _ in range(3):
        call_command("enviar_notificacoes")
    assert len(mail.outbox) == 1
    notificacao = Notificacao.objects.get()
    assert notificacao.enviado_em is not None
    assert notificacao.tentativas == 1


def test_recuo_dobra_a_cada_falha():
    """Recuo progressivo (spec 9): o intervalo cresce, nao e constante. Sem esta
    assercao, um `recuo` que devolvesse sempre RECUO_INICIAL continuaria
    passando nos testes de fila abaixo, que so olham "esperou ou nao esperou"."""
    assert services.recuo(1) == services.RECUO_INICIAL
    assert services.recuo(2) == 2 * services.RECUO_INICIAL
    assert services.recuo(3) == 4 * services.RECUO_INICIAL
    assert services.recuo(4) > services.recuo(3) > services.recuo(2) > services.recuo(1)


@pytest.mark.django_db
def test_notificacao_que_acabou_de_falhar_espera_antes_da_proxima_tentativa(settings):
    """Recuo progressivo (spec 9): a passada seguinte do cron, um minuto depois,
    nao pode retentar quem falhou agora. `tentativas` esta em 1, bem abaixo do
    limite, e `enviado_em` continua nulo - nenhuma outra metade do filtro recusa
    esta notificacao, so o recuo."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="A", corpo="B")
    with mock.patch("apps.notificacoes.management.commands.enviar_notificacoes.send_mail",
                    side_effect=OSError("smtp fora do ar")):
        call_command("enviar_notificacoes")
    notificacao = Notificacao.objects.get()
    assert notificacao.tentativas == 1
    assert notificacao.enviado_em is None
    assert notificacao.proxima_tentativa_em is not None

    # Agora o SMTP voltou: se nao houvesse recuo, esta passada entregaria.
    call_command("enviar_notificacoes")
    assert len(mail.outbox) == 0
    notificacao.refresh_from_db()
    assert notificacao.tentativas == 1


@pytest.mark.django_db
def test_notificacao_que_falhou_ha_tempo_volta_para_a_fila(settings):
    """Controle positivo do teste acima: passada a janela, a notificacao e
    retentada. Sem isto, um recuo infinito (ou um filtro que excluisse toda
    notificacao com proxima_tentativa_em preenchida) passaria despercebido."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="A", corpo="B")
    with mock.patch("apps.notificacoes.management.commands.enviar_notificacoes.send_mail",
                    side_effect=OSError("smtp fora do ar")):
        call_command("enviar_notificacoes")
    Notificacao.objects.update(
        proxima_tentativa_em=timezone.now() - services.recuo(1)
    )
    call_command("enviar_notificacoes")
    assert len(mail.outbox) == 1
    notificacao = Notificacao.objects.get()
    assert notificacao.enviado_em is not None
    assert notificacao.tentativas == 2
