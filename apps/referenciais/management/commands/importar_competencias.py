import csv as csv_lib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.referenciais.models import Categoria, Competencia, Referencial

COLUNAS = {"codigo", "descricao", "etapa", "categoria"}


class Command(BaseCommand):
    help = "Importa competencias de um referencial a partir de um CSV (codigo,descricao,etapa,categoria)."

    def add_arguments(self, parser):
        parser.add_argument("--referencial", required=True, help="Sigla do referencial, ex.: BNCC-COMP")
        parser.add_argument("--csv", required=True, help="Caminho do arquivo CSV")

    @transaction.atomic
    def handle(self, *args, **opcoes):
        try:
            referencial = Referencial.objects.get(sigla=opcoes["referencial"])
        except Referencial.DoesNotExist:
            raise CommandError(f"Referencial {opcoes['referencial']} nao existe.")

        categorias = {c.nome: c for c in referencial.categorias.all()}

        with open(opcoes["csv"], encoding="utf-8") as arquivo:
            leitor = csv_lib.DictReader(arquivo)
            if not COLUNAS.issubset(set(leitor.fieldnames or [])):
                raise CommandError(f"O CSV precisa das colunas: {', '.join(sorted(COLUNAS))}.")
            total = 0
            for numero, linha in enumerate(leitor, start=2):
                categoria = categorias.get(linha["categoria"].strip())
                if categoria is None:
                    raise CommandError(
                        f"Linha {numero}: categoria '{linha['categoria']}' nao existe em {referencial.sigla}."
                    )
                Competencia.objects.update_or_create(
                    referencial=referencial,
                    codigo=linha["codigo"].strip(),
                    defaults={
                        "categoria": categoria,
                        "descricao": linha["descricao"].strip(),
                        "etapa": linha["etapa"].strip(),
                        "ordem": total,
                    },
                )
                total += 1

        self.stdout.write(self.style.SUCCESS(f"{total} competencias importadas em {referencial.sigla}."))
