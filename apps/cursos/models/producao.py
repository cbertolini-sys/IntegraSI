from typing import NamedTuple

import nh3
from django.conf import settings
from django.db import models

from apps.cursos.choices import StatusEntregavel, TipoEntregavel

class Situacao(NamedTuple):
    """O que o selo da lista mostra: o texto e o tom (ok, espera, atencao)."""

    rotulo: str
    tom: str


TAGS_PERMITIDAS = {
    "p", "br", "strong", "em", "u", "ul", "ol", "li",
    "h2", "h3", "h4", "blockquote", "a", "table", "thead",
    "tbody", "tr", "th", "td",
}


# A ordem em que o roteiro pede os entregaveis, que e a dos rotulos ("A - Plano de
# Ensino", "B - Infograficos"...). Nao da para ordenar pela coluna `tipo`: ela guarda
# o valor sem a letra e sem acento (CADERNO, CARDS, PLANO_ENSINO, SLIDES, VIDEOS), e
# ordenar por ele exibia C, B, A, E, D na tela. Tambem nao da para ordenar pelo
# rotulo, que nao existe no banco. O Case traduz um no outro dentro da consulta.
#
# Aplicado por um Manager, e NAO por Meta.ordering: expressao em Meta.ordering
# rebenta assim que o modelo e alcancado por relacao (curso.entregaveis, um
# prefetch, um filtro que atravessa a FK), porque o Django tenta prefixar a
# expressao com o caminho do join e levanta "'Q' object has no attribute
# 'prefix_references'". Foram 140 testes vermelhos ate isso ficar claro.
ORDEM_DO_ROTEIRO = models.Case(
    *[
        models.When(tipo=valor, then=models.Value(posicao))
        for posicao, valor in enumerate(TipoEntregavel.values)
    ],
    output_field=models.PositiveSmallIntegerField(),
)


class EntregavelManager(models.Manager):
    """Entrega os entregaveis na ordem do roteiro, sempre.

    No manager e nao em cada view: o Django monta o manager reverso
    (`curso.entregaveis`) a partir desta classe, entao a ordem vale igual na pagina
    do curso, na fila de revisao, na analise da coordenacao e em qualquer tela nova,
    sem que ninguem precise lembrar de um order_by.
    """

    def get_queryset(self):
        return super().get_queryset().order_by("curso", ORDEM_DO_ROTEIRO)

    def na_revisao_de(self, usuario):
        """Os dois grupos da fila do professor: o que espera decisao dele e o que
        voltou para a equipe por decisao dele.

        Um metodo so porque a fila e o cartao do painel precisam da MESMA conta -
        numero que nao bate com a tela que ele abre ja foi defeito duas vezes
        nesta base.

        O segundo grupo sai filtrado em Python: "a ultima revisao nao foi
        aprovacao" nao cabe num filtro sem subconsulta, e sao poucos entregaveis
        por professor. O `prefetch` e o que impede uma consulta por linha.
        """
        base = (
            self.filter(curso__professor_responsavel=usuario)
            .select_related("curso")
            .prefetch_related("revisoes")
        )
        esperando = list(base.filter(status=StatusEntregavel.EM_REVISAO))
        com_a_equipe = [
            e for e in base.filter(status=StatusEntregavel.RASCUNHO)
            if e.voltou_para_a_equipe
        ]
        return esperando, com_a_equipe


class Entregavel(models.Model):
    """Um dos cinco pacotes obrigatorios do roteiro. E a unidade de revisao:
    o professor aprova ou devolve o entregavel, nunca item por item (spec 4.6)."""

    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.CASCADE, related_name="entregaveis", verbose_name="curso"
    )
    tipo = models.CharField("tipo", max_length=20, choices=TipoEntregavel.choices)
    status = models.CharField(
        "situação", max_length=20, choices=StatusEntregavel.choices, default=StatusEntregavel.RASCUNHO
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entregaveis_sob_responsabilidade",
        verbose_name="aluno responsável",
    )
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    objects = EntregavelManager()

    class Meta:
        verbose_name = "entregável"
        verbose_name_plural = "entregáveis"
        ordering = ["curso", "tipo"]
        constraints = [
            models.UniqueConstraint(fields=["curso", "tipo"], name="entregavel_unico_por_curso")
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.curso.titulo}"

    @property
    def numero(self):
        """A posicao no roteiro, de 1 a 6.

        Lida da ordem de declaracao de TipoEntregavel, a MESMA fonte de
        ORDEM_DO_ROTEIRO: dois lugares lendo a mesma lista nao saem de sincronia,
        e reordenar o enum reordena a tela e renumera os selos de uma vez.
        """
        return TipoEntregavel.values.index(self.tipo) + 1

    @property
    def nome(self):
        """O rotulo sem o numero.

        A tela mostra "Etapa 1" num selo ao lado; repetir o numero no titulo o
        diria duas vezes na mesma linha. Se um rotulo futuro nao tiver o prefixo,
        devolve o rotulo inteiro em vez de recortar errado.
        """
        return self.get_tipo_display().split(" - ", 1)[-1]

    @property
    def voltou_para_a_equipe(self):
        """Esta com a equipe por DECISAO do professor, e nao por nunca ter saido
        do rascunho.

        Depois que DEVOLVIDO virou leitura do historico, esta e a unica pergunta
        que distingue "devolvido/reaberto" de "ainda nem foi enviado" - e e o que
        a fila do professor precisa para nao perder de vista o que ele mandou
        corrigir.
        """
        from apps.cursos.models.revisao import Revisao

        if self.status != StatusEntregavel.RASCUNHO:
            return False
        revisoes = list(self.revisoes.all())
        return bool(revisoes) and revisoes[-1].decisao != Revisao.APROVADO

    @property
    def situacao(self):
        """O que a LISTA mostra: o estado atual, mais o que o historico explica.

        Enquanto o entregavel esta com a equipe (RASCUNHO), a ultima decisao diz
        se ele nunca saiu dali ou se voltou - devolvido depois de um envio,
        reaberto depois de uma aprovacao. Nos outros estados o proprio status
        responde, e o historico nao tem o que acrescentar.

        Le por `.all()` de proposito, para aproveitar o `prefetch_related` das
        telas: `.last()` desceria ao banco de novo, uma consulta por cartao.
        """
        tons = {
            StatusEntregavel.APROVADO: "ok",
            StatusEntregavel.EM_REVISAO: "espera",
        }
        if self.status != StatusEntregavel.RASCUNHO:
            return Situacao(self.get_status_display(), tons.get(self.status, ""))
        if not self.voltou_para_a_equipe:
            return Situacao(self.get_status_display(), "")
        return Situacao(list(self.revisoes.all())[-1].get_decisao_display(), "atencao")

    @property
    def editavel(self):
        return self.status == StatusEntregavel.RASCUNHO

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)


class Secao(models.Model):
    entregavel = models.ForeignKey(
        Entregavel, on_delete=models.CASCADE, related_name="secoes", verbose_name="entregável"
    )
    titulo = models.CharField("título", max_length=120)
    ordem = models.PositiveSmallIntegerField("ordem", default=0)
    conteudo = models.TextField("conteúdo", blank=True)
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="secoes_atualizadas",
        verbose_name="atualizado por",
    )
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "seção"
        verbose_name_plural = "seções"
        ordering = ["entregavel", "ordem", "id"]

    @property
    def ajuda(self):
        """O que escrever nesta secao, para o balao da tela.

        Import adiado: `services` importa `models`, e trazer o dicionario no topo
        fecharia o ciclo. Devolve vazio para secao que o professor criou por conta
        propria, e a tela simplesmente nao desenha balao nenhum.
        """
        from apps.cursos.services import AJUDA_DAS_SECOES

        return AJUDA_DAS_SECOES.get(self.titulo, "")

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        # Sanitiza sempre, inclusive quando o texto vem de um servico e nao de um form,
        # e mesmo em um save(update_fields=[...]) direcionado: e a unica barreira entre
        # o editor de texto rico e um script no navegador do professor, e por isso roda
        # fora do guarda do update_fields, nunca dentro dele.
        self.conteudo = nh3.clean(self.conteudo or "", tags=TAGS_PERMITIDAS)
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
