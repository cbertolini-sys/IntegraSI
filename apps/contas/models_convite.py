import datetime
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ConviteAluno(models.Model):
    """Convite de primeiro acesso, com prazo e uso único.

    Modelo próprio, e não o `PasswordResetTokenGenerator` do Django: aquele
    gerador tira o prazo de `PASSWORD_RESET_TIMEOUT`, que é global e vale também
    para o "esqueci minha senha". Um convite de sete dias e um reset de poucas
    horas são políticas diferentes, e amarrá-las na mesma chave faria uma mudança
    mexer na outra sem aviso. Aqui o prazo é por registro, e o convite fica
    auditável: quem convidou, quando, e se já foi usado.
    """

    PRAZO = datetime.timedelta(days=7)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="convites",
        verbose_name="aluno",
    )
    token = models.UUIDField("token", default=uuid.uuid4, unique=True, editable=False)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="convites_enviados",
        verbose_name="convidado por",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    expira_em = models.DateTimeField("expira em")
    usado_em = models.DateTimeField("usado em", null=True, blank=True)
    cancelado_em = models.DateTimeField("cancelado em", null=True, blank=True)

    class Meta:
        verbose_name = "convite de aluno"
        verbose_name_plural = "convites de aluno"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["token"])]

    def __str__(self):
        return f"Convite de {self.usuario.nome_completo}"

    @property
    def valido(self):
        """Três condições, escritas separadas para que apagar qualquer uma
        derrube o seu próprio teste."""
        if self.usado_em is not None:
            return False
        if self.cancelado_em is not None:
            return False
        return self.expira_em > timezone.now()

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            if not self.expira_em:
                self.expira_em = timezone.now() + self.PRAZO
            self.full_clean()
        super().save(*args, **kwargs)
