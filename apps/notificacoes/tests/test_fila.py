import fcntl
import io
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command

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
