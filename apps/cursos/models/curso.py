from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce

from apps.cursos.busca import CONFIG_TEXTO
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

    # Versionamento (spec 4.5). `raiz` fica vazia na propria v1 - e ela a raiz -,
    # entao a linhagem inteira e COALESCE(raiz_id, id): ver linhagem_id abaixo e a
    # constraint no Meta, que dependem os dois dessa mesma expressao.
    raiz = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="versoes",
        verbose_name="primeira versão desta linhagem",
    )
    versao = models.PositiveSmallIntegerField("versão", default=1)
    motivo_versao = models.TextField("motivo desta versão", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)
    publicado_em = models.DateTimeField("publicado em", null=True, blank=True)

    # Coluna gerada: cobre os campos da propria linha. Coluna gerada nao faz JOIN,
    # entao os temas NAO cabem aqui e vivem em vetor_temas (spec 4.4).
    search_vector = models.GeneratedField(
        expression=SearchVector(
            # output_field explicito: titulo/palavras_chave sao CharField e resumo
            # e TextField - sem isto, Coalesce nao sabe resolver um output_field
            # unico para os tres e o Django recusa a expressao (FieldError: mixed
            # types) antes mesmo de chegar no banco.
            Coalesce(F("titulo"), Value(""), output_field=models.TextField()),
            Coalesce(F("resumo"), Value(""), output_field=models.TextField()),
            Coalesce(F("palavras_chave"), Value(""), output_field=models.TextField()),
            config=CONFIG_TEXTO,
        ),
        output_field=SearchVectorField(),
        db_persist=True,
    )
    vetor_temas = SearchVectorField("vetor dos temas", null=True, editable=False)

    class Meta:
        verbose_name = "curso"
        verbose_name_plural = "cursos"
        ordering = ["-criado_em"]
        indexes = [
            GinIndex(fields=["search_vector"], name="curso_busca_idx"),
            GinIndex(fields=["vetor_temas"], name="curso_busca_temas_idx"),
        ]
        constraints = [
            # No maximo UMA versao publicada por linhagem (spec 4.5: "o catalogo
            # mostra, de cada linhagem, apenas a versao publicada"). E essa
            # invariante que deixa o catalogo ser um filter(status=PUBLICADO)
            # simples, sem DISTINCT ON: quem a quebrar poe o mesmo curso duas
            # vezes na listagem publica, em silencio.
            #
            # Quem a mantem no dia a dia e o laco de substituicao de
            # services.publicar_curso; esta constraint e a rede embaixo dele, para
            # um comando, uma migracao de dados ou um .update() futuro que passe
            # ao largo do service. Indexa COALESCE(raiz_id, id) e nao raiz_id: na
            # v1 raiz e NULL, e no Postgres NULL nunca colide com nada - um indice
            # parcial sobre raiz_id deixaria a v1 e a v2 publicadas lado a lado,
            # que e exatamente o caso que precisa ser barrado.
            models.UniqueConstraint(
                Coalesce(F("raiz_id"), F("id")),
                condition=Q(status=StatusCurso.PUBLICADO),
                name="uma_versao_publicada_por_linhagem",
            )
        ]

    def __str__(self):
        return self.titulo

    @property
    def linhagem_id(self):
        """Identifica a linhagem: a v1 e a propria raiz das demais (spec 4.5)."""
        return self.raiz_id or self.pk

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

    @property
    def pronto_para_o_coordenador(self):
        """Os cinco entregaveis aprovados liberam o curso para o coordenador (spec 5)."""
        from apps.cursos.choices import StatusEntregavel, TipoEntregavel

        aprovados = self.entregaveis.filter(status=StatusEntregavel.APROVADO).count()
        return aprovados == len(TipoEntregavel.values)

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
