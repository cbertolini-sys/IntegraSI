import datetime
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class RedefinicaoDeSenha(models.Model):
    """Pedido de "esqueci minha senha", com prazo e uso único.

    Modelo próprio, e não o mesmo mecanismo do `ConviteAluno` - o comentário
    daquele modelo já antecipa isto: "um convite de sete dias e um reset de
    poucas horas são políticas diferentes, e amarrá-las na mesma chave faria uma
    mudança mexer na outra sem aviso". Aqui o prazo é de horas, não de dias, e
    não há `criado_por`: ninguém convida, a própria pessoa pede.
    """

    PRAZO = datetime.timedelta(hours=2)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="redefinicoes_de_senha",
        verbose_name="usuário",
    )
    token = models.UUIDField("token", default=uuid.uuid4, unique=True, editable=False)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    expira_em = models.DateTimeField("expira em")
    usado_em = models.DateTimeField("usado em", null=True, blank=True)

    class Meta:
        verbose_name = "redefinição de senha"
        verbose_name_plural = "redefinições de senha"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["token"])]

    def __str__(self):
        return f"Redefinição de {self.usuario.nome_completo}"

    @property
    def valido(self):
        """Duas condições, escritas separadas para que apagar qualquer uma
        derrube o seu próprio teste - o mesmo desenho de `ConviteAluno.valido`."""
        if self.usado_em is not None:
            return False
        return self.expira_em > timezone.now()

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            if not self.expira_em:
                self.expira_em = timezone.now() + self.PRAZO
            self.full_clean()
        super().save(*args, **kwargs)
