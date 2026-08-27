import fcntl
from pathlib import Path

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.notificacoes.models import Notificacao
from apps.notificacoes.services import LIMITE_TENTATIVAS, recuo

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
        # Instante da montagem do lote: serve para escolher quem entra, e so para
        # isso. O recuo de quem falhar e contado a partir da falha, la embaixo.
        inicio_do_lote = timezone.now()
        pendentes = Notificacao.objects.filter(
            # enviado_em__isnull=True e o que impede o reenvio: o cron passa a cada
            # minuto e, sem esta metade do filtro, toda notificacao ja entregue
            # volta para a fila e e reenviada ate tentativas bater no limite.
            enviado_em__isnull=True,
            tentativas__lt=LIMITE_TENTATIVAS,
        ).filter(
            # Recuo progressivo (spec 9): quem falhou ha pouco espera a janela
            # passar. Nulo e quem nunca falhou - entra na primeira passada.
            Q(proxima_tentativa_em__isnull=True) | Q(proxima_tentativa_em__lte=inicio_do_lote)
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
                # timezone.now() de novo, e nao o inicio_do_lote: com --lote 50
                # contra um SMTP pendurado, o proprio lote dura mais que a janela
                # de 5 minutos, e contar o recuo do inicio deixaria a cabeca do
                # lote elegivel outra vez antes de a cauda terminar - o recuo se
                # anularia justamente no cenario que a spec 9 descreve. O caminho
                # de sucesso ja usava um now() fresco pelo mesmo motivo.
                notificacao.proxima_tentativa_em = timezone.now() + recuo(notificacao.tentativas)
                notificacao.save(
                    update_fields=["tentativas", "ultimo_erro", "proxima_tentativa_em"]
                )
                continue
            notificacao.enviado_em = timezone.now()
            notificacao.tentativas += 1
            notificacao.ultimo_erro = ""
            notificacao.save(update_fields=["enviado_em", "tentativas", "ultimo_erro"])
            enviadas += 1
        self.stdout.write(self.style.SUCCESS(f"{enviadas} notificações enviadas."))
