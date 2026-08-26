from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class MembroEquipe(models.Model):
    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.CASCADE, related_name="membros", verbose_name="curso"
    )
    aluno = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="equipes", verbose_name="aluno"
    )
    adicionado_em = models.DateTimeField("adicionado em", auto_now_add=True)

    class Meta:
        verbose_name = "membro da equipe"
        verbose_name_plural = "membros da equipe"
        ordering = ["aluno__nome_completo"]
        constraints = [
            models.UniqueConstraint(fields=["curso", "aluno"], name="membro_unico_por_curso")
        ]

    def __str__(self):
        return f"{self.aluno.nome_completo} em {self.curso.titulo}"

    def clean(self):
        super().clean()
        if self.aluno_id and not self.aluno.e_aluno:
            raise ValidationError({"aluno": "Só aluno pode compor a equipe de produção."})

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
