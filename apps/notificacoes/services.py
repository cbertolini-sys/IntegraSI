from apps.notificacoes.models import Notificacao

LIMITE_TENTATIVAS = 5


def enfileirar(evento, destinatarios, assunto, corpo):
    """Grava as notificações a enviar. Nunca envia dentro da requisição."""
    unicos = sorted({d for d in destinatarios if d})
    return Notificacao.objects.bulk_create(
        [
            Notificacao(destinatario=d, assunto=assunto, corpo=corpo, evento=evento)
            for d in unicos
        ]
    )
