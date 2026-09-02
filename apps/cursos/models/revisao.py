import nh3
from django.conf import settings
from django.db import models

from apps.cursos.models.producao import TAGS_PERMITIDAS


class Revisao(models.Model):
    """Registro imutavel de cada decisao do professor. Nunca sobrescrito: e o
    historico das idas e vindas (spec 4.6)."""

    APROVADO = "APROVADO"
    DEVOLVIDO = "DEVOLVIDO"
    DECISOES = [(APROVADO, "Aprovado"), (DEVOLVIDO, "Devolvido")]

    entregavel = models.ForeignKey(
        "cursos.Entregavel", on_delete=models.CASCADE, related_name="revisoes", verbose_name="entregável"
    )
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="revisoes", verbose_name="revisor"
    )
    decisao = models.CharField("decisão", max_length=20, choices=DECISOES)
    comentario = models.TextField("comentário", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "revisão"
        verbose_name_plural = "revisões"
        ordering = ["criado_em"]

    def save(self, *args, **kwargs):
        # Sanitiza sempre, como `Secao.save()` e `Anexo.save()`: o comentario e
        # escrito num editor de texto rico e renderizado com |safe na devolutiva
        # que a equipe le, entao esta linha e a unica barreira entre ele e um
        # script no navegador de quem produz. Fora do guarda do update_fields.
        #
        # So a sanitizacao, sem `full_clean()`: esta linha nasce de `services` e
        # nunca e reescrita (o historico das idas e vindas e imutavel), o mesmo
        # motivo pelo qual `Arquivo` tambem nao tem guarda no save.
        self.comentario = nh3.clean(self.comentario or "", tags=TAGS_PERMITIDAS)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_decisao_display()} em {self.entregavel}"
