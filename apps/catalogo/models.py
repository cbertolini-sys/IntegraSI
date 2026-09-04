from django.db import models

from apps.cursos.models.producao import Situacao


class Solicitacao(models.Model):
    """Pedido de realização de um curso, vindo da comunidade externa.

    Guarda dado pessoal de terceiro: finalidade declarada no formulário, acesso
    restrito ao professor responsável e ao coordenador (spec 10).
    """

    RECEBIDA = "RECEBIDA"
    EM_ANALISE = "EM_ANALISE"
    ACEITA = "ACEITA"
    RECUSADA = "RECUSADA"
    SITUACOES = [
        (RECEBIDA, "Recebida"),
        (EM_ANALISE, "Em análise"),
        (ACEITA, "Aceita"),
        (RECUSADA, "Recusada"),
    ]

    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.PROTECT, related_name="solicitacoes", verbose_name="curso"
    )
    nome = models.CharField("nome do solicitante", max_length=150)
    email = models.EmailField("e-mail")
    telefone = models.CharField("telefone", max_length=20, blank=True)
    instituicao = models.CharField("instituição", max_length=150, blank=True)
    num_participantes = models.PositiveSmallIntegerField("participantes previstos")
    periodo_pretendido = models.CharField("período pretendido", max_length=100, blank=True)
    mensagem = models.TextField("mensagem", max_length=2000, blank=True)
    status = models.CharField("situação", max_length=20, choices=SITUACOES, default=RECEBIDA)
    resposta = models.TextField("resposta", blank=True)
    ip_origem = models.GenericIPAddressField("IP de origem", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "solicitação"
        verbose_name_plural = "solicitações"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.nome} pediu {self.curso.titulo}"

    @property
    def situacao(self):
        """Rótulo e tom, como em `cursos` (M3 da auditoria).

        RECEBIDA e EM_ANALISE respondem o mesmo par - "A responder", em espera -
        porque é o que a lista de pendentes já mostrava: a pessoa que responde não
        precisa distinguir as duas, as duas pedem a mesma ação dela. ACEITA e
        RECUSADA continuam com o rótulo do próprio status, como a lista de
        respondidas já fazia.
        """
        if self.status in (self.RECEBIDA, self.EM_ANALISE):
            return Situacao(rotulo="A responder", tom="espera")
        if self.status == self.ACEITA:
            return Situacao(rotulo=self.get_status_display(), tom="ok")
        return Situacao(rotulo=self.get_status_display(), tom="atencao")


class SugestaoDeCurso(models.Model):
    """Demanda por um curso que AINDA NAO EXISTE, vinda da comunidade externa.

    Modelo proprio, e nao `Solicitacao` com `curso` nulo, por tres razoes. O
    `Solicitacao.curso` e obrigatorio e PROTECT, e a frase que identifica o objeto
    e "X pediu {curso.titulo}": torna-lo nulo enfraqueceria uma invariante real
    para acomodar um caso que nao e o mesmo. As duas coisas pedem acoes diferentes
    da coordenacao - aceitar uma solicitacao e agendar turma de um curso pronto,
    aceitar uma sugestao e convidar um professor a propor um curso que nao existe.
    E a sugestao tem um campo que a solicitacao nao tem, a demanda em si, que
    enfiada em `mensagem` nao viraria filtro nem relatorio.

    Guarda dado pessoal de terceiro: finalidade declarada no formulario, acesso
    restrito a coordenacao (spec 10).
    """

    RECEBIDA = "RECEBIDA"
    EM_ANALISE = "EM_ANALISE"
    ACEITA = "ACEITA"
    RECUSADA = "RECUSADA"
    SITUACOES = [
        (RECEBIDA, "Recebida"),
        (EM_ANALISE, "Em análise"),
        (ACEITA, "Aceita"),
        (RECUSADA, "Recusada"),
    ]

    SIM = "SIM"
    NAO = "NAO"
    NAO_SEI = "NAO_SEI"
    LABORATORIO = [
        (SIM, "Sim"),
        (NAO, "Não"),
        (NAO_SEI, "Não sei informar"),
    ]

    nome = models.CharField("nome de quem sugere", max_length=150)
    email = models.EmailField("e-mail")
    telefone = models.CharField("telefone", max_length=20, blank=True)
    instituicao = models.CharField("instituição", max_length=150)
    # Vocabulario de tres, e nao um booleano: quem preenche o formulario pode ser
    # a secretaria da escola, que nao tem como saber. Booleano obrigatorio forcaria
    # essa pessoa a chutar, e chute vira planejamento errado; booleano opcional
    # confundiria "nao tem" com "nao respondeu".
    tem_laboratorio = models.CharField(
        "laboratório de informática", max_length=10, choices=LABORATORIO
    )
    publico_alvo = models.CharField("público-alvo", max_length=200)
    demanda = models.TextField("demanda", max_length=2000)
    status = models.CharField("situação", max_length=20, choices=SITUACOES, default=RECEBIDA)
    resposta = models.TextField("resposta", blank=True)
    ip_origem = models.GenericIPAddressField("IP de origem", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "sugestão de curso"
        verbose_name_plural = "sugestões de curso"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.nome} sugeriu um curso para {self.publico_alvo}"

    @property
    def situacao(self):
        """O mesmo par rotulo/tom de `Solicitacao`, pela mesma razao: quem responde
        nao precisa distinguir Recebida de Em análise, as duas pedem a mesma acao."""
        if self.status in (self.RECEBIDA, self.EM_ANALISE):
            return Situacao(rotulo="A responder", tom="espera")
        if self.status == self.ACEITA:
            return Situacao(rotulo=self.get_status_display(), tom="ok")
        return Situacao(rotulo=self.get_status_display(), tom="recusa")
