import datetime
from functools import partial

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.cursos.models import Anexo, Arquivo


def _apagar_bytes(storage, nome):
    # `FileSystemStorage.delete` engole FileNotFoundError, entao a rotina e
    # re-executavel: linha viva com os bytes ja fora do disco nao derruba a passada.
    storage.delete(nome)


class Command(BaseCommand):
    help = "Remove arquivos que nenhum anexo de nenhuma versao referencia. Rode por cron."

    def add_arguments(self, parser):
        parser.add_argument(
            "--horas", type=int, default=24, help="Idade minima do arquivo para ser considerado lixo."
        )

    def handle(self, *args, **opcoes):
        corte = timezone.now() - datetime.timedelta(hours=opcoes["horas"])
        total = 0
        with transaction.atomic():
            # Idade + select_for_update, e nao contador de referencias: contador
            # denormalizado desanda em exclusao em lote, rollback ou clone de versao,
            # e o modo de falha dele e apagar arquivo em uso (spec 13). A idade cobre
            # a janela entre o fim do upload e o salvamento do Anexo, em que o
            # arquivo legitimamente nao tem referencia nenhuma.
            #
            # `~Exists`, e nao `anexos__isnull=True`: a travessia da relacao inversa
            # produz um LEFT OUTER JOIN, e o PostgreSQL recusa
            # "FOR UPDATE cannot be applied to the nullable side of an outer join" --
            # a rotina nao rodaria nunca. O conserto obvio tambem tem armadilha:
            # `exclude(pk__in=Anexo.objects.values("arquivo_id"))` gera um NOT IN, e
            # `Anexo.arquivo` e anulavel (anexo de link nao tem arquivo); um unico
            # NULL na lista faz o NOT IN nao devolver linha nenhuma, e a limpeza
            # viraria silenciosamente um no-op. NOT EXISTS nao tem nem o join nem a
            # sensibilidade a NULL.
            orfaos = Arquivo.objects.filter(
                ~Exists(Anexo.objects.filter(arquivo=OuterRef("pk"))),
                enviado_em__lt=corte,
            ).select_for_update()
            for arquivo in orfaos:
                campo = arquivo.arquivo
                # Mesma ordem e mesmo motivo do limpar_uploads: a linha sai dentro da
                # transacao, os bytes depois do commit. Ao contrario, um rollback
                # devolveria o Arquivo ao banco sem os bytes, e todo Anexo que o
                # referencia entregaria 404 para sempre.
                transaction.on_commit(partial(_apagar_bytes, campo.storage, campo.name))
                arquivo.delete()
                total += 1
        self.stdout.write(self.style.SUCCESS(f"{total} arquivos orfaos removidos."))
