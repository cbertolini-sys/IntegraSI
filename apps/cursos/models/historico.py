from django.conf import settings
from django.db import models

from apps.cursos.choices import StatusCurso


class LogTransicaoCurso(models.Model):
    """Rastro administrativo das mudanças de situação do curso. Responde
    'por que este curso saiu do ar?' seis meses depois (spec 11)."""

    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.CASCADE, related_name="transicoes", verbose_name="curso"
    )
    de_status = models.CharField("de", max_length=30, choices=StatusCurso.choices)
    para_status = models.CharField("para", max_length=30, choices=StatusCurso.choices)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transicoes_de_curso"
    )
    observacao = models.TextField("observação", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "transição de curso"
        verbose_name_plural = "transições de curso"
        ordering = ["criado_em"]

    def __str__(self):
        return f"{self.curso}: {self.de_status} -> {self.para_status}"
