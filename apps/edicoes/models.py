from django.core.exceptions import ValidationError
from django.db import models


class EdicaoManager(models.Manager):
    def corrente(self):
        """A edicao em andamento, ou None se o coordenador ainda nao abriu nenhuma."""
        return self.filter(ativa=True).first()


class Edicao(models.Model):
    codigo = models.CharField("codigo", max_length=10, unique=True, help_text="Ex.: 2026/2")
    descricao = models.CharField("descricao", max_length=200)
    data_inicio = models.DateField("inicio")
    data_fim = models.DateField("fim")
    ativa = models.BooleanField("edicao corrente", default=False)

    objects = EdicaoManager()

    class Meta:
        verbose_name = "edicao"
        verbose_name_plural = "edicoes"
        ordering = ["-data_inicio"]

    def __str__(self):
        return self.codigo

    def clean(self):
        super().clean()
        if self.data_inicio and self.data_fim and self.data_fim <= self.data_inicio:
            raise ValidationError({"data_fim": "O fim deve ser posterior ao inicio."})
        if self.ativa:
            outras = Edicao.objects.filter(ativa=True).exclude(pk=self.pk)
            if outras.exists():
                raise ValidationError(
                    {"ativa": f"A edicao {outras.first().codigo} ja esta ativa. Desative-a antes."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
