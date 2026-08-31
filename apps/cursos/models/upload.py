import os
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.cursos.arquivos import LIMITE_VIDEO


class UploadEmAndamento(models.Model):
    """Progresso de um upload fatiado. Um GB no upstream domestico de um aluno leva
    perto de meia hora: um POST unico que falha aos 90% significa entrega perdida
    (spec 8)."""

    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="uploads"
    )
    entregavel = models.ForeignKey(
        "cursos.Entregavel", on_delete=models.CASCADE, related_name="uploads"
    )
    nome_original = models.CharField("nome original", max_length=255)
    tamanho_total = models.PositiveBigIntegerField("tamanho total declarado")
    tamanho_recebido = models.PositiveBigIntegerField("recebido", default=0)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "upload em andamento"
        verbose_name_plural = "uploads em andamento"
        ordering = ["-atualizado_em"]

    def __str__(self):
        return f"{self.nome_original} ({self.tamanho_recebido}/{self.tamanho_total})"

    def clean(self):
        super().clean()
        if self.tamanho_total > LIMITE_VIDEO:
            raise ValidationError({"tamanho_total": "Arquivo acima do limite de 1 GB."})

    def save(self, *args, **kwargs):
        # Guarda de `update_fields` como no resto do projeto (docs/onde-mora-a-validacao.md,
        # armadilha 2). Aqui nao e so estilo: `acrescentar()` grava uma vez por bloco de
        # 5 MB, e sem o guarda cada bloco arrastaria um `full_clean()` inteiro - inclusive
        # o `validate_unique()` de `identificador`, uma ida ao banco por bloco, ~200 por GB.
        # A criacao nao passa `update_fields`, entao continua validando.
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)

    def caminho(self):
        """Arquivo parcial em disco. O nome sai do `identificador` e SO dele:
        `nome_original` e texto livre do cliente, e usa-lo aqui deixaria um
        `../../../etc/passwd` escapar de MEDIA_ROOT."""
        pasta = Path(settings.MEDIA_ROOT) / "uploads"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta / f"{self.identificador.hex}.parcial"

    @property
    def completo(self):
        return self.tamanho_recebido >= self.tamanho_total

    def acrescentar(self, bloco):
        """Grava o bloco na posicao ja registrada e avanca o progresso.

        Idempotente por bloco, e e o ponto da tarefa: a escrita e posicionada em
        `tamanho_recebido` em vez de ser um append cego. Se os bytes chegam ao disco
        mas o registro nao avanca - o `save()` falha, o cliente nao recebe a
        confirmacao e reenvia - , o reenvio reescreve os mesmos bytes no mesmo lugar
        em vez de duplica-los. Com append cego o arquivo ficaria corrompido em
        silencio, com `tamanho_recebido` parecendo certo.

        Ordem obrigatoria: bytes primeiro, registro depois. O registro pode ficar
        atras do disco (o reenvio conserta); se ficasse na frente, o arquivo teria
        um buraco que nada detecta.
        """
        inicio = self.tamanho_recebido
        if inicio + len(bloco) > self.tamanho_total:
            raise ValidationError("Bloco ultrapassa o tamanho declarado do arquivo.")

        descritor = os.open(self.caminho(), os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(descritor, "r+b") as parcial:
            parcial.seek(inicio)
            parcial.write(bloco)
            # Corta o que houver depois: sobra de um bloco anterior cuja escrita
            # morreu no meio. O parcial tem sempre exatamente `tamanho_recebido` bytes.
            parcial.truncate()
            parcial.flush()
            os.fsync(parcial.fileno())

        self.tamanho_recebido = inicio + len(bloco)
        try:
            self.save(update_fields=["tamanho_recebido", "atualizado_em"])
        except Exception:
            # Quem manda e o registro. Se ele nao avancou, a instancia em memoria
            # tambem nao pode avancar, ou o proximo bloco gravaria no offset errado.
            self.tamanho_recebido = inicio
            raise
