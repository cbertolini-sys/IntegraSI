import csv as csv_lib

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.referenciais.choices import ETAPAS_REFERENCIAL
from apps.referenciais.models import Competencia, Referencial

COLUNAS = {"codigo", "descricao", "etapa", "categoria"}
# ETAPAS_REFERENCIAL, e nao ETAPAS: o CSV traz a etapa como o REFERENCIAL a
# organiza ("EM" para o Ensino Medio inteiro), nao como o curso a declara
# ("EM02"). Validar contra o vocabulario do curso recusava as 26 habilidades
# do Medio, e foi o teste de importacao ponta a ponta que acusou.
ETAPAS_VALIDAS = {codigo for codigo, _ in ETAPAS_REFERENCIAL}


class Command(BaseCommand):
    help = "Importa competências de um referencial a partir de um CSV (codigo,descricao,etapa,categoria)."

    def add_arguments(self, parser):
        parser.add_argument("--referencial", required=True, help="Sigla do referencial, ex.: BNCC-COMP")
        parser.add_argument("--csv", required=True, help="Caminho do arquivo CSV")

    @transaction.atomic
    def handle(self, *args, **opcoes):
        try:
            referencial = Referencial.objects.get(sigla=opcoes["referencial"])
        except Referencial.DoesNotExist:
            raise CommandError(f"Referencial {opcoes['referencial']} não existe.")

        categorias = {c.nome: c for c in referencial.categorias.all()}

        with open(opcoes["csv"], encoding="utf-8") as arquivo:
            leitor = csv_lib.DictReader(arquivo)
            if not COLUNAS.issubset(set(leitor.fieldnames or [])):
                raise CommandError(f"O CSV precisa das colunas: {', '.join(sorted(COLUNAS))}.")
            total = 0
            for numero, linha in enumerate(leitor, start=2):
                valores = {campo: (linha.get(campo) or "").strip() for campo in COLUNAS}

                if not valores["codigo"]:
                    raise CommandError(f"Linha {numero}: falta o código (linha incompleta?).")

                # A validação abaixo duplica as `choices` de Competencia.etapa, que
                # Competencia.save() -> full_clean() já impõe. Mantida mesmo assim:
                # ela nomeia a linha do CSV e lista os valores aceitos, uma
                # mensagem que um ValidationError de model não consegue dar.
                if valores["etapa"] not in ETAPAS_VALIDAS:
                    raise CommandError(
                        f"Linha {numero}: etapa '{valores['etapa']}' inválida. "
                        f"Valores aceitos: {', '.join(sorted(ETAPAS_VALIDAS))}."
                    )

                categoria = categorias.get(valores["categoria"])
                if categoria is None:
                    raise CommandError(
                        f"Linha {numero}: categoria '{valores['categoria']}' não existe em {referencial.sigla}."
                    )
                # Opcional de proposito, e por isso fora de COLUNAS: outro
                # referencial pode nao ter esse nivel intermediario, e exigir a
                # coluna quebraria um CSV que hoje importa.
                objeto = (linha.get("objeto_conhecimento") or "").strip()
                Competencia.objects.update_or_create(
                    referencial=referencial,
                    codigo=valores["codigo"],
                    defaults={
                        "categoria": categoria,
                        "descricao": valores["descricao"],
                        "objeto_conhecimento": objeto,
                        "etapa": valores["etapa"],
                        "ordem": total,
                    },
                )
                total += 1

        self.stdout.write(self.style.SUCCESS(f"{total} competências importadas em {referencial.sigla}."))
