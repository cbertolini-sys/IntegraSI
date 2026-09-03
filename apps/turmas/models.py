from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.cursos.models.producao import Situacao


class Turma(models.Model):
    """O agendamento de uma realização do curso.

    Forma mínima de propósito (spec 1.1): este é o módulo de produção. Frequência,
    avaliação e certificado são do módulo de execução, que será construído a partir
    daqui. Nenhum campo desses entra neste modelo.
    """

    AGENDADA = "AGENDADA"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"
    # Valor gravado sem acento e nunca alterado por passada de texto; só o rótulo
    # é português acentuado (CLAUDE.md).
    SITUACOES = [
        (AGENDADA, "Agendada"),
        (EM_ANDAMENTO, "Em andamento"),
        (CONCLUIDA, "Concluída"),
        (CANCELADA, "Cancelada"),
    ]
    # O tom de cada status (M3 da auditoria). `[self.status]`, e nao `.get(...,
    # "")`: um quinto status sem entrada aqui precisa estourar KeyError, e nao
    # sair com o selo sem cor - o defeito que a cadeia de `{% if %}` do template
    # tinha e ninguem via, porque EM_ANDAMENTO nunca aparecia nos cenarios de
    # teste manual.
    TONS = {
        AGENDADA: "info",
        EM_ANDAMENTO: "info",
        CONCLUIDA: "ok",
        CANCELADA: "atencao",
    }

    # Aponta para a versão específica do curso, nunca para a linhagem: é o que
    # permitirá dizer, lá na frente, qual material foi aplicado nesta turma (spec 1.1).
    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.PROTECT, related_name="turmas", verbose_name="curso"
    )
    solicitacao = models.OneToOneField(
        "catalogo.Solicitacao",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="turma",
        verbose_name="solicitação de origem",
    )
    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="turmas",
        verbose_name="professor",
    )
    data_inicio = models.DateField("início")
    data_fim = models.DateField("fim")
    local = models.CharField("local", max_length=200)
    vagas = models.PositiveSmallIntegerField("vagas")
    status = models.CharField("situação", max_length=20, choices=SITUACOES, default=AGENDADA)
    observacoes = models.TextField("observações", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "turma"
        verbose_name_plural = "turmas"
        ordering = ["-data_inicio"]

    def __str__(self):
        return f"{self.curso.titulo} em {self.local}"

    @property
    def situacao(self):
        """Rótulo e tom, como em `cursos.models.producao.Entregavel` e `Curso`:
        a decisão fica em Python, onde dá para testar, e não numa cadeia de
        `{% if %}` no template - a mesma unificação de `_selo.html` (A4/A5/A6),
        agora estendida a `turmas`."""
        return Situacao(rotulo=self.get_status_display(), tom=self.TONS[self.status])

    def clean(self):
        super().clean()
        erros = {}
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            erros["data_fim"] = "O fim não pode ser anterior ao início."
        if self.professor_id:
            # Duas regras distintas, escritas como if/elif para que cada uma possa
            # ser apagada sozinha e derrubar o proprio teste: um aluno (ativo) so
            # aciona a primeira, um professor desativado so aciona a segunda.
            if not self.professor.e_professor:
                erros["professor"] = "Somente professor conduz turma."
            elif not self.professor.is_active:
                # Mora aqui, e nao so no queryset de TurmaForm: desativar uma conta
                # e como este sistema desliga alguem (Usuario nao e apagado, por
                # causa dos PROTECT), e a tela nao e a guarda - services.py, o
                # Admin e o shell tambem criam Turma. Regra que cruza campos do
                # mesmo objeto => Model.clean() (docs/onde-mora-a-validacao.md, 2).
                erros["professor"] = "Professor desativado não conduz turma."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        # Guarda de update_fields (docs/onde-mora-a-validacao.md, armadilha 2): uma
        # escrita direcionada num objeto já persistido não revalida o objeto inteiro.
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)


class Participante(models.Model):
    """Quem assiste ao curso na realização. Dado pessoal de terceiro externo, que
    nunca faz login: só o professor da turma e a coordenação enxergam (spec 10)."""

    turma = models.ForeignKey(
        Turma, on_delete=models.CASCADE, related_name="participantes", verbose_name="turma"
    )
    nome = models.CharField("nome", max_length=150)
    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "participante"
        verbose_name_plural = "participantes"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if "update_fields" not in kwargs:
            self.full_clean()
        super().save(*args, **kwargs)
