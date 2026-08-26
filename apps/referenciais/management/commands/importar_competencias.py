import csv as csv_lib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.referenciais.choices import ETAPAS
from apps.referenciais.models import Competencia, Referencial

COLUNAS = {"codigo", "descricao", "etapa", "categoria"}
ETAPAS_VALIDAS = {codigo for codigo, _ in ETAPAS}


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
                valores = {campo: (linha.get(campo) or "").strip() for campo in COLUNAS}

                if not valores["codigo"]:
                    raise CommandError(f"Linha {numero}: falta o codigo (linha incompleta?).")

                if valores["etapa"] not in ETAPAS_VALIDAS:
                    raise CommandError(
                        f"Linha {numero}: etapa '{valores['etapa']}' invalida. "
                        f"Valores aceitos: {', '.join(sorted(ETAPAS_VALIDAS))}."
                    )

                categoria = categorias.get(valores["categoria"])
                if categoria is None:
                    raise CommandError(
                        f"Linha {numero}: categoria '{valores['categoria']}' nao existe em {referencial.sigla}."
                    )
                Competencia.objects.update_or_create(
                    referencial=referencial,
                    codigo=valores["codigo"],
                    defaults={
                        "categoria": categoria,
                        "descricao": valores["descricao"],
                        "etapa": valores["etapa"],
                        "ordem": total,
                    },
                )
                total += 1

        self.stdout.write(self.style.SUCCESS(f"{total} competencias importadas em {referencial.sigla}."))
