from django.core.exceptions import ValidationError
from django.db import models

from apps.referenciais.choices import ETAPAS


class Referencial(models.Model):
    """Um modelo pedagogico de referencia. A BNCC da Computacao e um deles, nao o unico:
    cursos de Arduino ou IA na Educacao ficam sem referencial (spec 4.2)."""

    nome = models.CharField("nome", max_length=120, unique=True)
    sigla = models.CharField("sigla", max_length=20, unique=True)
    descricao = models.TextField("descricao", blank=True)
    min_competencias = models.PositiveSmallIntegerField("minimo de competencias", default=1)
    max_competencias = models.PositiveSmallIntegerField("maximo de competencias", default=5)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "referencial"
        verbose_name_plural = "referenciais"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        if self.max_competencias < self.min_competencias:
            raise ValidationError(
                {"max_competencias": "O maximo nao pode ser menor que o minimo."}
            )

    def valida_quantidade(self, quantidade):
        """Levanta ValidationError se a quantidade de competencias escolhidas nao
        respeitar a faixa deste referencial. Chamado pelo Curso (Plano 2)."""
        if not (self.min_competencias <= quantidade <= self.max_competencias):
            raise ValidationError(
                f"{self.nome} exige de {self.min_competencias} a "
                f"{self.max_competencias} competencias; foram escolhidas {quantidade}."
            )


class Categoria(models.Model):
    """Agrupamento dentro de um referencial. Na BNCC da Computacao chama-se eixo."""

    referencial = models.ForeignKey(
        Referencial, on_delete=models.CASCADE, related_name="categorias", verbose_name="referencial"
    )
    nome = models.CharField("nome", max_length=120)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["referencial", "ordem", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["referencial", "nome"], name="categoria_unica_no_referencial")
        ]

    def __str__(self):
        return self.nome


class Competencia(models.Model):
    referencial = models.ForeignKey(
        Referencial, on_delete=models.CASCADE, related_name="competencias", verbose_name="referencial"
    )
    categoria = models.ForeignKey(
        Categoria, on_delete=models.CASCADE, related_name="competencias", verbose_name="categoria"
    )
    codigo = models.CharField("codigo", max_length=20)
    descricao = models.TextField("descricao")
    etapa = models.CharField("etapa", max_length=4, choices=ETAPAS)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)

    class Meta:
        verbose_name = "competencia"
        verbose_name_plural = "competencias"
        ordering = ["referencial", "etapa", "ordem", "codigo"]
        constraints = [
            models.UniqueConstraint(fields=["referencial", "codigo"], name="competencia_unica_no_referencial")
        ]

    def __str__(self):
        return f"{self.codigo} - {self.descricao[:60]}"

    def clean(self):
        super().clean()
        if self.categoria_id and self.referencial_id and self.categoria.referencial_id != self.referencial_id:
            raise ValidationError({"categoria": "A categoria pertence a outro referencial."})
