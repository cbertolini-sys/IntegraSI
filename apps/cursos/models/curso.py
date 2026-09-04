from typing import NamedTuple

from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce

from apps.cursos.busca import CONFIG_TEXTO
from apps.cursos.choices import Formato, StatusCurso, TipoPratica, TipoPublico
from apps.referenciais.choices import ETAPAS


class Progresso(NamedTuple):
    """Quanto do curso esta feito, em duas medidas que nao sao a mesma.

    `prontos` e ausencia de pendencia: o material daquele entregavel esta
    completo segundo a regra dele. `revisados` e o status APROVADO: o professor
    olhou e aceitou. Um entregavel pode estar completo e ainda nao revisado, e e
    por isso que sao dois numeros e nao um.

    O percentual acompanha `prontos`, e nao `revisados`: a pergunta e quanto do
    material esta terminado. Ver `pronto_para_o_coordenador` para a outra
    pergunta, a de quando o curso pode subir.
    """

    total: int
    prontos: int
    revisados: int

    @property
    def percentual(self):
        """Quanto do material esta terminado."""
        return self._parte(self.prontos)

    @property
    def percentual_revisado(self):
        """Quanto o professor ja aprovou. Anda atras do outro, e nao junto: da
        para ter tudo pronto e nada revisado."""
        return self._parte(self.revisados)

    def _parte(self, quantos):
        # `total` vem de uma consulta, e curso sem entregavel e estado alcancavel
        # (uma migracao, um comando): a divisao por zero moraria na propriedade.
        if not self.total:
            return 0
        return round(100 * quantos / self.total)


class Praticas(NamedTuple):
    """Resposta a "precisa de computador?", nas duas dimensoes que nao se excluem:
    um curso pode ter as duas metades, uma so, ou -- enquanto o caderno nao foi
    montado -- nenhuma."""

    plugada: bool
    desplugada: bool

    @property
    def rotulo(self):
        if self.plugada and self.desplugada:
            return "Com e sem computador"
        if self.desplugada:
            return "Funciona sem computador"
        if self.plugada:
            return "Precisa de computador"
        return "Não informado"


class Curso(models.Model):
    titulo = models.CharField("título", max_length=200)
    resumo = models.TextField("resumo", blank=True)
    professor_responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cursos_como_responsavel",
        verbose_name="professor responsável",
    )

    tipo_publico = models.CharField(
        "tipo de público", max_length=20, choices=TipoPublico.choices, blank=True
    )
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

    # null=True porque e numerico: em campo numerico o vazio do banco e NULL, e
    # blank=True sozinho so afeta formulario. MinValueValidator(1) fica: ele nao
    # roda sobre None, entao continua barrando carga horaria zero.
    carga_horaria = models.PositiveSmallIntegerField(
        "carga horária (horas)", null=True, blank=True, validators=[MinValueValidator(1)]
    )
    formato = models.CharField("formato", max_length=20, choices=Formato.choices, blank=True)
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
            # O catalogo publico e os tres cartoes do painel filtram por status
            # (nove lugares, entre eles a unica tela que gente de fora visita) - e
            # a coluna mais consultada do sistema, e nao tinha indice proprio.
            models.Index(fields=["status"], name="curso_status_idx"),
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
            ),
            # Numero de versao unico dentro da linhagem. `services.abrir_nova_versao`
            # calcula `ultima.versao + 1` depois de um `exists()` sem trava: duas
            # chamadas simultaneas na mesma linhagem - o coordenador e o professor
            # clicando junto, ou um duplo-submit - leem a mesma "ultima" e criam duas
            # "v2" em RASCUNHO. A constraint de cima nao pega: as duas nascem em
            # RASCUNHO e o indice parcial dela so olha PUBLICADO.
            #
            # Mesma expressao COALESCE(raiz_id, id) e pelo mesmo motivo: na v1 raiz e
            # NULL, e NULL nunca colide com nada no Postgres. Sobre COALESCE, a v1 de
            # cada linhagem cai no proprio id, entao duas linhagens diferentes podem
            # perfeitamente ter as duas a versao 1.
            #
            # Nao ha `select_for_update` na linhagem alem disto, de proposito: ele
            # daria a mensagem amigavel no lugar do IntegrityError, mas so a constraint
            # vale para quem escreve por fora do service (admin, shell, migracao de
            # dados), e um lock que so o service respeita nao e invariante nenhuma.
            #
            # O preco assumido: `nova_versao` so captura ValidationError, entao o
            # perdedor da corrida ve um 500 em vez de mensagem. E a troca certa --
            # duas "v2" silenciosas na mesma linhagem sao piores que um erro visivel
            # num clique duplo -- mas fica dito para quem vier depois nao achar que
            # o 500 e descuido.
            models.UniqueConstraint(
                Coalesce(F("raiz_id"), F("id")),
                "versao",
                name="uma_numeracao_por_linhagem",
            ),
        ]

    def __str__(self):
        return self.titulo

    @property
    def linhagem_id(self):
        """Identifica a linhagem: a v1 e a propria raiz das demais (spec 4.5)."""
        return self.raiz_id or self.pk

    @property
    def publico_alvo(self):
        """Texto legível do público: a etapa escolar, a descrição, ou as duas.

        Junta as duas de propósito. Escolher uma só escondia a outra, e desde que a
        descrição virou complemento da etapa ("5º ano" mais "turmas da escola do
        campo") esconder qualquer uma delas é perder informação que a equipe
        escreveu.

        Cai para o rótulo do tipo **só no público comunitário**, onde a descrição
        deixou de ser obrigatória e o catálogo não pode ficar sem dizer para quem o
        curso é. No escolar não cai: lá a etapa é obrigatória, e devolver "Etapa
        escolar" faria o portão de completude dar por resolvido um curso que não
        diz de que ano é.
        """
        partes = []
        if self.etapa_ano:
            partes.append(self.get_etapa_ano_display())
        if self.publico_descricao:
            partes.append(self.publico_descricao)
        if not partes and self.tipo_publico == TipoPublico.COMUNITARIO:
            partes.append(self.get_tipo_publico_display())
        return " \u00b7 ".join(partes)

    @property
    def identidade(self):
        """Publico, carga horaria e formato numa linha, so com o que ja existe.

        A proposta nasce com a ficha vazia (spec 4.3), e os cabecalhos
        interpolavam os campos direto: um curso recem-criado mostrava
        " . Noneh . " no lugar da linha, porque o template do Django renderiza
        None como o texto "None". Achado olhando a tela, nao pela suite.

        Monta em Python, e nao com `if` no template, pela mesma razao de
        pode_abrir_versao na view do curso: a decisao fica onde da para testar.
        """
        partes = [self.publico_alvo]
        if self.carga_horaria:
            partes.append(f"{self.carga_horaria}h")
        if self.formato:
            partes.append(self.get_formato_display())
        partes = [p for p in partes if p]
        return " \u00b7 ".join(partes) if partes else "Ficha ainda não preenchida"

    @property
    def lista_de_palavras_chave(self):
        """As palavras-chave repartidas, para a tela mostrar uma por etiqueta.

        O banco guarda um texto so porque e ele que alimenta o `search_vector`
        (spec 4.4); quem reparte para exibir e esta propriedade, e nao o template,
        porque `split` com limpeza nao cabe em linguagem de template.
        """
        return [p.strip() for p in (self.palavras_chave or "").split(",") if p.strip()]

    @property
    def rotulo_da_versao(self):
        """"Versão N", para a lista do inventario do catalogo.

        Aqui, e nao no template, porque juntar palavra e numero em linguagem de
        template exige o filtro `add`, que faz conversao implicita e falha calado.
        """
        return f"Versão {self.versao}"

    @property
    def situacao(self):
        """O rotulo e o tom do selo, como `Entregavel.situacao`.

        A cadeia de `{% if curso.status == ... %}` estava em quatro templates, e
        eles ja tinham divergido: um deles pintava so PUBLICADO e mostrava um
        curso despublicado sem cor nenhuma. A regra passa a morar aqui, onde ha
        um lugar so para mudar.
        """
        from apps.cursos.models.producao import Situacao

        tons = {
            StatusCurso.PUBLICADO: "ok",
            StatusCurso.AGUARDANDO_COORDENADOR: "espera",
            StatusCurso.DEVOLVIDO: "atencao",
            # Saiu do catalogo e precisa de alguem: o mesmo tom do devolvido.
            StatusCurso.DESPUBLICADO: "atencao",
        }
        return Situacao(self.get_status_display(), tons.get(self.status, ""))

    @property
    def praticas(self):
        """Este curso precisa de computador?

        A pergunta que uma escola municipal do interior faz primeiro, e que o
        catalogo nao respondia: o dado ja existia em `Anexo.tipo_pratica`, no
        caderno de exercicios, e nunca saia da tela de producao. Uma escola com um
        laboratorio compartilhado -- ou nenhum -- decide por aqui.

        Usa `.all()` de proposito, para aproveitar o `prefetch_related` das telas
        do catalogo; sem ele seriam duas consultas por curso na listagem.
        """
        tipos = {
            anexo.tipo_pratica
            for entregavel in self.entregaveis.all()
            for anexo in entregavel.anexos.all()
        }
        return Praticas(
            plugada=bool(tipos & {TipoPratica.PLUGADA, TipoPratica.AMBAS}),
            desplugada=bool(tipos & {TipoPratica.DESPLUGADA, TipoPratica.AMBAS}),
        )

    def clean(self):
        super().clean()
        erros = {}
        # A descricao do publico e livre em qualquer tipo: era proibida junto com a
        # etapa e obrigatoria no comunitario, e as duas regras cairam a pedido de
        # quem preenche. "5o ano" e "turmas da escola do campo" dizem mais juntos
        # do que separados, e o catalogo nao fica sem publico porque
        # `publico_alvo` cai para o tipo quando nao ha descricao.
        #
        # As regras da ETAPA continuam: e ela que liga o curso ao referencial
        # organizado por etapa (spec 4.2).
        if self.tipo_publico == TipoPublico.ESCOLAR and not self.etapa_ano:
            erros["etapa_ano"] = "Informe a etapa ou ano escolar."
        if self.tipo_publico == TipoPublico.COMUNITARIO and self.etapa_ano:
            erros["etapa_ano"] = "Deixe vazio quando o público é comunitário."
        if self.professor_responsavel_id and not self.professor_responsavel.e_professor:
            erros["professor_responsavel"] = "O responsável precisa ter papel de professor."
        if erros:
            raise ValidationError(erros)

    def tem_membro(self, usuario):
        return self.membros.filter(pessoa=usuario).exists()

    @property
    def equipe(self):
        """Os membros alem do responsavel.

        Desde o Plano 6 o responsavel e membro da equipe do curso que responde
        (spec 4.1), entao listar `membros` cru imprime o nome dele duas vezes: uma
        como responsavel e outra no meio da equipe.

        Usa `.all()` de proposito, para aproveitar o `prefetch_related` das telas;
        um `.exclude()` aqui dispararia consulta nova e desfaria o prefetch.
        """
        return [m for m in self.membros.all() if m.pessoa_id != self.professor_responsavel_id]

    @property
    def progresso(self):
        """Quantos dos seis entregaveis estao prontos e quantos ja foram revisados.

        `pendencias` cobra a regra de cada entregavel (o roteiro do Plano 2), que e
        a mesma que o envio para revisao usa: o numero da tela e o mesmo criterio
        que barra o envio, e nao uma segunda contagem que divergiria dele.
        """
        from apps.cursos import validacoes
        from apps.cursos.choices import StatusEntregavel

        entregaveis = list(self.entregaveis.all())
        return Progresso(
            total=len(entregaveis),
            prontos=sum(1 for e in entregaveis if not validacoes.pendencias(e)),
            revisados=sum(1 for e in entregaveis if e.status == StatusEntregavel.APROVADO),
        )

    @property
    def pronto_para_o_coordenador(self):
        """Os seis entregaveis aprovados liberam o curso para o coordenador (spec 5)."""
        from apps.cursos.choices import StatusEntregavel, TipoEntregavel

        aprovados = self.entregaveis.filter(status=StatusEntregavel.APROVADO).count()
        return aprovados == len(TipoEntregavel.values)

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
