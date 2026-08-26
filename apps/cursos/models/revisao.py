from django.conf import settings
from django.db import models


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

    def __str__(self):
        return f"{self.get_decisao_display()} em {self.entregavel}"
