import uuid

import nh3

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.cursos.choices import Rotulo, TipoMidia, TipoPratica
from apps.cursos.models.producao import TAGS_PERMITIDAS


def caminho_do_arquivo(instance, filename):
    """Nome em disco por UUID: o nome original e so metadado exibido (spec 8)."""
    return f"materiais/{instance.identificador.hex[:2]}/{instance.identificador.hex}"


class Arquivo(models.Model):
    """O conteudo binario, separado do anexo que o referencia. Versoes diferentes de
    um curso apontam para o MESMO Arquivo: clonar um curso nao pode clonar 3 GB de
    video (spec 4.6). Imutavel apos a criacao - por convencao de quem usa o model
    (services.py so cria, nunca atualiza), igual Revisao: nao ha guarda no save()
    que barre uma alteracao posterior."""

    identificador = models.UUIDField("identificador", default=uuid.uuid4, unique=True, editable=False)
    arquivo = models.FileField("arquivo", upload_to=caminho_do_arquivo, max_length=255)
    nome_original = models.CharField("nome original", max_length=255)
    tamanho = models.PositiveBigIntegerField("tamanho em bytes")
    mime = models.CharField("tipo", max_length=100)
    hash_conteudo = models.CharField("hash do conteúdo", max_length=64)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="arquivos_enviados"
    )
    enviado_em = models.DateTimeField("enviado em", auto_now_add=True)

    class Meta:
        verbose_name = "arquivo"
        verbose_name_plural = "arquivos"
        ordering = ["-enviado_em"]
        indexes = [models.Index(fields=["hash_conteudo"])]

    def __str__(self):
        return self.nome_original


class Anexo(models.Model):
    entregavel = models.ForeignKey(
        "cursos.Entregavel", on_delete=models.CASCADE, related_name="anexos", verbose_name="entregável"
    )
    secao = models.ForeignKey(
        "cursos.Secao",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anexos",
        verbose_name="seção",
    )
    tipo_midia = models.CharField("tipo", max_length=20, choices=TipoMidia.choices)
    arquivo = models.ForeignKey(
        Arquivo, on_delete=models.PROTECT, null=True, blank=True, related_name="anexos"
    )
    url = models.URLField("link", blank=True)
    titulo = models.CharField("título", max_length=200)
    descricao = models.TextField("descrição", blank=True)
    referencia_bibliografica = models.TextField("referência bibliográfica", blank=True)
    rotulo = models.CharField("rótulo", max_length=20, choices=Rotulo.choices, default=Rotulo.NENHUM)
    tipo_pratica = models.CharField(
        "tipo de prática", max_length=20, choices=TipoPratica.choices, default=TipoPratica.NENHUM
    )
    duracao_minutos = models.PositiveSmallIntegerField("duração em minutos", null=True, blank=True)
    enviado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="anexos_enviados"
    )
    enviado_em = models.DateTimeField("enviado em", auto_now_add=True)

    class Meta:
        verbose_name = "anexo"
        verbose_name_plural = "anexos"
        ordering = ["entregavel", "id"]

    def __str__(self):
        return self.titulo

    def clean(self):
        super().clean()
        erros = {}
        if self.tipo_midia == TipoMidia.LINK:
            if not self.url:
                erros["url"] = "Informe o endereço do link."
            if self.arquivo_id:
                erros["arquivo"] = "Anexo de link não tem arquivo."
        else:
            if not self.arquivo_id:
                erros["arquivo"] = "Envie o arquivo."
            if self.url:
                erros["url"] = "Anexo de arquivo não tem link."
        if self.tipo_midia == TipoMidia.VIDEO and not self.duracao_minutos:
            erros["duracao_minutos"] = "Informe a duração do vídeo em minutos."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        # Sanitiza sempre, pelo mesmo motivo de `Secao.save()`: a descricao e
        # escrita num editor de texto rico e renderizada com |safe na lista de
        # materiais, entao esta linha e a unica barreira entre ela e um script no
        # navegador de quem le. Fica FORA do guarda do update_fields - um save
        # direcionado e justamente o caminho de uma edicao rapida.
        self.descricao = nh3.clean(self.descricao or "", tags=TAGS_PERMITIDAS)
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
