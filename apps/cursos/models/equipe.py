from django.conf import settings
from django.db import models


class MembroEquipe(models.Model):
    """Quem produz um curso: alunos e professores, inclusive o responsavel.

    O campo se chama `pessoa`, e nao `aluno`, porque guarda professor tambem
    (spec 4.1). Nao ha `clean()`: com a equipe aceitando aluno e professor, e
    todo Usuario sendo um dos dois, qualquer guarda de papel aqui seria uma
    guarda incapaz de falhar. A unicidade por (curso, pessoa) fica com a
    UniqueConstraint, que vale tambem para escrita em massa.
    """

    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.CASCADE, related_name="membros", verbose_name="curso"
    )
    pessoa = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="equipes", verbose_name="pessoa"
    )
    adicionado_em = models.DateTimeField("adicionado em", auto_now_add=True)

    class Meta:
        verbose_name = "membro da equipe"
        verbose_name_plural = "membros da equipe"
        ordering = ["pessoa__nome_completo"]
        constraints = [
            models.UniqueConstraint(fields=["curso", "pessoa"], name="membro_unico_por_curso")
        ]

    def __str__(self):
        return f"{self.pessoa.nome_completo} em {self.curso.titulo}"

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
