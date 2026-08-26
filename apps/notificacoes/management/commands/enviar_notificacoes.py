import fcntl
from pathlib import Path

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notificacoes.models import Notificacao
from apps.notificacoes.services import LIMITE_TENTATIVAS

TRAVA = Path(settings.BASE_DIR) / "enviar_notificacoes.lock"


class Command(BaseCommand):
    help = "Envia as notificações pendentes. Rode por cron."

    def add_arguments(self, parser):
        parser.add_argument("--lote", type=int, default=50, help="Máximo de envios por execução.")

    def handle(self, *args, **opcoes):
        with open(TRAVA, "w") as trava:
            try:
                # Sem a trava, uma execução lenta se sobrepõe à seguinte e o mesmo
                # e-mail sai duas vezes (spec 9).
                fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.stdout.write("Outra execução está em andamento; saindo.")
                return
            self._enviar(opcoes["lote"])

    def _enviar(self, lote):
        pendentes = Notificacao.objects.filter(
            enviado_em__isnull=True, tentativas__lt=LIMITE_TENTATIVAS
        )[:lote]
        enviadas = 0
        for notificacao in pendentes:
            try:
                send_mail(
                    subject=notificacao.assunto,
                    message=notificacao.corpo,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[notificacao.destinatario],
                    fail_silently=False,
                )
            except Exception as erro:
                notificacao.tentativas += 1
                notificacao.ultimo_erro = str(erro)
                notificacao.save(update_fields=["tentativas", "ultimo_erro"])
                continue
            notificacao.enviado_em = timezone.now()
            notificacao.tentativas += 1
            notificacao.ultimo_erro = ""
            notificacao.save(update_fields=["enviado_em", "tentativas", "ultimo_erro"])
            enviadas += 1
        self.stdout.write(self.style.SUCCESS(f"{enviadas} notificações enviadas."))
