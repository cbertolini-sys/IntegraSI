import datetime

from apps.notificacoes.models import Notificacao

LIMITE_TENTATIVAS = 5

# Recuo progressivo (spec 9). O cron roda a cada minuto: sem recuo, um SMTP fora
# do ar queima as cinco tentativas em cinco minutos e a notificacao e abandonada
# antes que qualquer pessoa perceba a falha - alem de martelar o servidor de
# e-mail justamente quando ele esta em apuros.
RECUO_INICIAL = datetime.timedelta(minutes=5)


def recuo(tentativas):
    """Quanto esperar antes da proxima tentativa, depois de `tentativas` falhas.

    Dobra a cada falha: 5, 10, 20 e 40 minutos entre as cinco tentativas que
    LIMITE_TENTATIVAS permite - pouco mais de uma hora de janela total, em vez
    dos cinco minutos de antes.
    """
    return RECUO_INICIAL * (2 ** (max(tentativas, 1) - 1))


def enfileirar(evento, destinatarios, assunto, corpo):
    """Grava as notificações a enviar. Nunca envia dentro da requisição."""
    unicos = sorted({d for d in destinatarios if d})
    return Notificacao.objects.bulk_create(
        [
            Notificacao(destinatario=d, assunto=assunto, corpo=corpo, evento=evento)
            for d in unicos
        ]
    )
