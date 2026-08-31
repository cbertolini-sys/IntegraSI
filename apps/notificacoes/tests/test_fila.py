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


@pytest.mark.django_db
def test_a_janela_de_recuo_cresce_no_proprio_comando(settings):
    """Prende o crescimento *onde ele roda*, e nao so na funcao pura.

    test_recuo_dobra_a_cada_falha exercita services.recuo direto e nunca passa
    pelo comando: trocar `recuo(notificacao.tentativas)` por `RECUO_INICIAL` no
    ponto de chamada deixava a suite inteira verde, com a funcao provada e o uso
    dela nao. E a versao deste projeto do "teste com nome que nao exercita a
    regra", desta vez partida numa fronteira de funcao em vez de escondida no
    nome.

    Mede a janela contra um instante tomado antes da chamada: como o recuo agora
    conta do momento da falha (e nao do inicio do lote), proxima_tentativa_em cai
    entre `antes + recuo(n)` e `antes + recuo(n) + duracao da chamada`.
    """
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="A", corpo="B")
    smtp_fora_do_ar = mock.patch(
        "apps.notificacoes.management.commands.enviar_notificacoes.send_mail",
        side_effect=OSError("smtp fora do ar"),
    )

    antes_da_primeira = timezone.now()
    with smtp_fora_do_ar:
        call_command("enviar_notificacoes")
    notificacao = Notificacao.objects.get()
    assert notificacao.tentativas == 1
    assert notificacao.proxima_tentativa_em >= antes_da_primeira + services.recuo(1)
    assert notificacao.proxima_tentativa_em < antes_da_primeira + services.recuo(2)

    # Passada a primeira janela, a segunda falha precisa esperar o DOBRO. E esta
    # asserção que morre se o ponto de chamada usar um recuo fixo.
    Notificacao.objects.update(proxima_tentativa_em=timezone.now())
    antes_da_segunda = timezone.now()
    with smtp_fora_do_ar:
        call_command("enviar_notificacoes")
    notificacao.refresh_from_db()
    assert notificacao.tentativas == 2
    assert notificacao.proxima_tentativa_em >= antes_da_segunda + services.recuo(2)
    assert notificacao.proxima_tentativa_em < antes_da_segunda + services.recuo(3)


@pytest.mark.django_db
def test_recuo_conta_do_instante_da_falha_e_nao_do_inicio_do_lote(settings):
    """Spec 9, no cenario que a motiva: um lote grande contra um SMTP pendurado.

    Cada falha demora, e o lote inteiro pode durar mais que a janela de recuo. Se
    proxima_tentativa_em fosse contado do inicio do lote, todas as notificacoes
    do lote sairiam com a MESMA janela, ancorada num instante ja vencido quando o
    lote termina - o recuo se anularia justamente onde precisa valer.

    Cada notificacao tem de receber a janela contada da *sua* falha. O relogio do
    comando e mockado para que cada envio custe o dobro da janela; com o recuo
    ancorado no inicio do lote, as duas notificacoes ficariam com o mesmo
    proxima_tentativa_em, e as duas primeiras assercoes morrem.

    O que NAO se afirma aqui: que nenhuma notificacao volte a ficar elegivel
    antes de o lote acabar. Com cada item custando mais que a janela inteira, a
    cabeca do lote fica elegivel de novo por construcao, e isso esta certo - ja
    se passou tempo real suficiente. O defeito era a ancora compartilhada, nao a
    elegibilidade.
    """
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(
        evento="X", destinatarios=["a@ufsm.br", "b@ufsm.br"], assunto="A", corpo="B"
    )
    inicio_do_lote = timezone.now()
    relogio = [inicio_do_lote]
    falhas = []

    def falha_lenta(*args, **kwargs):
        # Cada tentativa consome mais tempo de parede que services.recuo(1).
        relogio[0] += services.recuo(1) * 2
        falhas.append(relogio[0])
        raise OSError("smtp pendurado")

    with mock.patch("apps.notificacoes.management.commands.enviar_notificacoes.timezone.now",
                    side_effect=lambda: relogio[0]):
        with mock.patch(
            "apps.notificacoes.management.commands.enviar_notificacoes.send_mail",
            side_effect=falha_lenta,
        ):
            call_command("enviar_notificacoes")

    # Notificacao.Meta.ordering = ["criado_em"], a mesma ordem em que o lote as
    # percorreu, entao a n-esima notificacao corresponde a n-esima falha.
    primeira, segunda = Notificacao.objects.all()
    assert primeira.proxima_tentativa_em == falhas[0] + services.recuo(1)
    assert segunda.proxima_tentativa_em == falhas[1] + services.recuo(1)
    # E as duas janelas sao distintas: uma ancora unica no inicio do lote as
    # tornaria iguais.
    assert primeira.proxima_tentativa_em != segunda.proxima_tentativa_em
    # O lote de fato durou mais que a janela - sem isto o cenario nao seria o da
    # spec 9 e o teste passaria por acidente.
    assert falhas[-1] > inicio_do_lote + services.recuo(1)


@pytest.mark.django_db
def test_enfileirar_nao_repete_destinatario():
    """A mesma pessoa em duas listas somadas nao pode virar dois e-mails iguais.

    E o caso de publicar_curso, que soma a equipe ao e-mail do responsavel: desde
    o Plano 6 o responsavel esta dentro da equipe, entao o endereco dele aparece
    duas vezes na lista. Quem impede a duplicata de chegar na caixa e este `set`,
    que existia desde sempre e nao tinha teste nenhum.
    """
    services.enfileirar(
        evento="TESTE",
        destinatarios=["ana@ufsm.br", "bruno@ufsm.br", "ana@ufsm.br"],
        assunto="Assunto",
        corpo="Corpo",
    )
    assert Notificacao.objects.filter(destinatario="ana@ufsm.br").count() == 1
    assert Notificacao.objects.count() == 2


@pytest.mark.django_db
def test_enfileirar_ignora_destinatario_vazio():
    """Prende a outra metade do mesmo `if d`: sem ela, uma lista com endereco
    vazio gravaria notificacao que o cron tentaria entregar para sempre."""
    services.enfileirar(
        evento="TESTE", destinatarios=["ana@ufsm.br", "", None], assunto="A", corpo="C"
    )
    assert Notificacao.objects.count() == 1
