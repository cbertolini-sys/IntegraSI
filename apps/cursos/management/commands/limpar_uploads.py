import datetime
from functools import partial

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.cursos.models import UploadEmAndamento


def _apagar_parcial(caminho):
    # `missing_ok`: a rotina roda por cron e precisa ser re-executavel. Um parcial
    # que ja sumiu do disco -- meia execucao anterior, faxina manual, restauracao de
    # backup -- nao pode derrubar a limpeza dos uploads seguintes.
    caminho.unlink(missing_ok=True)


class Command(BaseCommand):
    help = "Remove uploads em blocos abandonados. Rode por cron."

    def add_arguments(self, parser):
        parser.add_argument(
            "--horas", type=int, default=24, help="Idade minima do upload para ser abandonado."
        )

    def handle(self, *args, **opcoes):
        corte = timezone.now() - datetime.timedelta(hours=opcoes["horas"])
        total = 0
        with transaction.atomic():
            for upload in UploadEmAndamento.objects.filter(atualizado_em__lt=corte):
                # Ordem obrigatoria: a linha sai dentro da transacao, os bytes so
                # depois que ela confirma. Apagar o parcial aqui dentro e a inversao
                # que a Task 2 ja pagou uma vez (services.concluir_upload): um
                # rollback devolve a linha ao banco apontando para um arquivo que nao
                # existe mais, e o dono nao consegue nem retomar nem concluir.
                #
                # `partial` e nao `lambda`: o agendamento acontece dentro do laco, e
                # `lambda: caminho.unlink(...)` capturaria a variavel, nao o valor --
                # todas as chamadas apagariam o parcial da ultima volta.
                transaction.on_commit(partial(_apagar_parcial, upload.caminho()))
                upload.delete()
                total += 1
        # Sem esta rotina, o disco enche de fragmentos de video que ninguem
        # reclamou (spec 13).
        self.stdout.write(self.style.SUCCESS(f"{total} uploads abandonados removidos."))
