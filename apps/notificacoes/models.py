from django.db import models


class Notificacao(models.Model):
    """Fila persistente de e-mail. A ação grava aqui e commita; o envio acontece
    depois, por cron. SMTP fora do ar não pode travar uma aprovação (spec 9)."""

    destinatario = models.EmailField("destinatário")
    assunto = models.CharField("assunto", max_length=200)
    corpo = models.TextField("corpo")
    evento = models.CharField("evento", max_length=50)
    tentativas = models.PositiveSmallIntegerField("tentativas", default=0)
    enviado_em = models.DateTimeField("enviado em", null=True, blank=True)
    ultimo_erro = models.TextField("último erro", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "notificação"
        verbose_name_plural = "notificações"
        ordering = ["criado_em"]
        indexes = [models.Index(fields=["enviado_em", "tentativas"])]

    def __str__(self):
        return f"{self.assunto} para {self.destinatario}"
