from django.db import models


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
