from django.db import models
from django.utils.text import slugify


class Tema(models.Model):
    """Vocabulário controlado usado como filtro no catálogo público (spec 4.4).
    É controlado de propósito: com texto livre, 'robótica' e 'Robótica' viram dois
    filtros diferentes e nenhum deles encontra tudo."""

    nome = models.CharField("nome", max_length=80, unique=True)
    slug = models.SlugField("slug", max_length=80, unique=True, blank=True)
    ativo = models.BooleanField("ativo", default=True)

    class Meta:
        verbose_name = "tema"
        verbose_name_plural = "temas"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def full_clean(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().full_clean(*args, **kwargs)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
