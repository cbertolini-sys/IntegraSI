from django.core.exceptions import ValidationError
from django.db import models


class EdicaoManager(models.Manager):
    def corrente(self):
        """A edição em andamento, ou None se o coordenador ainda não abriu nenhuma."""
        return self.filter(ativa=True).first()


class Edicao(models.Model):
    codigo = models.CharField("código", max_length=10, unique=True, help_text="Ex.: 2026/2")
    descricao = models.CharField("descrição", max_length=200)
    data_inicio = models.DateField("início")
    data_fim = models.DateField("fim")
    ativa = models.BooleanField("edição corrente", default=False)

    objects = EdicaoManager()

    class Meta:
        verbose_name = "edição"
        verbose_name_plural = "edições"
        ordering = ["-data_inicio"]

    def __str__(self):
        return self.codigo

    def clean(self):
        super().clean()
        if self.data_inicio and self.data_fim and self.data_fim <= self.data_inicio:
            raise ValidationError({"data_fim": "O fim deve ser posterior ao início."})
        if self.ativa:
            outras = Edicao.objects.filter(ativa=True).exclude(pk=self.pk)
            if outras.exists():
                raise ValidationError(
                    {"ativa": f"A edição {outras.first().codigo} já está ativa. Desative-a antes."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
