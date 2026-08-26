from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.cursos.choices import Formato, StatusCurso, TipoPublico
from apps.referenciais.choices import ETAPAS


class Curso(models.Model):
    titulo = models.CharField("título", max_length=200)
    resumo = models.TextField("resumo")
    edicao = models.ForeignKey(
        "edicoes.Edicao", on_delete=models.PROTECT, related_name="cursos", verbose_name="edição"
    )
    professor_responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cursos_como_responsavel",
        verbose_name="professor responsável",
    )

    tipo_publico = models.CharField("tipo de público", max_length=20, choices=TipoPublico.choices)
    etapa_ano = models.CharField("etapa ou ano escolar", max_length=4, choices=ETAPAS, blank=True)
    publico_descricao = models.CharField("descrição do público", max_length=200, blank=True)

    referencial = models.ForeignKey(
        "referenciais.Referencial",
        on_delete=models.PROTECT,
        related_name="cursos",
        null=True,
        blank=True,
        verbose_name="referencial pedagógico",
    )
    competencias = models.ManyToManyField(
        "referenciais.Competencia", related_name="cursos", blank=True, verbose_name="competências"
    )

    carga_horaria = models.PositiveSmallIntegerField(
        "carga horária (horas)", validators=[MinValueValidator(1)]
    )
    formato = models.CharField("formato", max_length=20, choices=Formato.choices)
    pre_requisitos = models.TextField("pré-requisitos", blank=True)

    temas = models.ManyToManyField("cursos.Tema", related_name="cursos", blank=True, verbose_name="temas")
    palavras_chave = models.CharField("palavras-chave", max_length=300, blank=True)

    status = models.CharField(
        "situação", max_length=30, choices=StatusCurso.choices, default=StatusCurso.RASCUNHO
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)
    publicado_em = models.DateTimeField("publicado em", null=True, blank=True)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["-criado_em"]

    def __str__(self):
        return self.titulo

    @property
    def publico_alvo(self):
        """Texto legível do público, seja etapa escolar ou grupo comunitário."""
        if self.tipo_publico == TipoPublico.ESCOLAR:
            return self.get_etapa_ano_display()
        return self.publico_descricao

    def clean(self):
        super().clean()
        erros = {}
        if self.tipo_publico == TipoPublico.ESCOLAR:
            if not self.etapa_ano:
                erros["etapa_ano"] = "Informe a etapa ou ano escolar."
            if self.publico_descricao:
                erros["publico_descricao"] = "Deixe vazio quando o público é escolar."
        elif self.tipo_publico == TipoPublico.COMUNITARIO:
            if not self.publico_descricao:
                erros["publico_descricao"] = "Descreva o público da comunidade."
            if self.etapa_ano:
                erros["etapa_ano"] = "Deixe vazio quando o público é comunitário."
        if self.professor_responsavel_id and not self.professor_responsavel.e_professor:
            erros["professor_responsavel"] = "O responsável precisa ter papel de professor."
        if erros:
            raise ValidationError(erros)

    def tem_membro(self, usuario):
        return self.membros.filter(aluno=usuario).exists()

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
