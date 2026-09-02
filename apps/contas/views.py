from django.contrib import messages
import datetime

from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.catalogo.models import Solicitacao
from apps.contas import services
from apps.contas.forms_convite import PrimeiroAcessoForm
from apps.contas.models import ConviteAluno, TentativaDeLogin, Usuario
from apps.contas.rede import ip_da_requisicao
from apps.cursos.choices import STATUS_EM_DESENVOLVIMENTO, StatusCurso, StatusEntregavel
from apps.cursos.models import Curso, Entregavel
from apps.turmas.models import Turma


# Dez tentativas em quinze minutos. O numero e mais generoso que o da
# solicitacao publica (cinco por hora) porque errar a propria senha algumas vezes
# e comum, e trancar quem digitou errado seria pior que o problema. Ainda assim
# derruba a forca bruta: a lista de e-mails institucionais e adivinhavel, mas
# quarenta tentativas por hora nao quebram senha nenhuma.
LIMITE_DE_TENTATIVAS = 10
JANELA_DE_TENTATIVAS = datetime.timedelta(minutes=15)


class LoginComLimite(LoginView):
    """O `LoginView` do Django, com limite de tentativas por IP.

    Conta por IP e ignora o e-mail tentado: sem isso, quem gira a lista de
    enderecos do mesmo lugar ganha cota nova a cada endereco.

    O GET nunca e bloqueado - trancar a propria tela deixaria a pessoa sem nem
    ler a mensagem que explica o bloqueio.
    """

    def post(self, request, *args, **kwargs):
        if self._excedeu(request):
            return self.render_to_response(
                self.get_context_data(
                    form=self.get_form(),
                    # A mesma resposta para conta que existe e conta que nao
                    # existe: a diferenca seria um oraculo de enderecos validos.
                    erro="Muitas tentativas deste endereço. Tente novamente mais tarde.",
                )
            )
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        self._registrar(self.request)
        return super().form_invalid(form)

    def _excedeu(self, request):
        desde = timezone.now() - JANELA_DE_TENTATIVAS
        return (
            TentativaDeLogin.objects.filter(
                ip=ip_da_requisicao(request), criado_em__gte=desde
            ).count()
            >= LIMITE_DE_TENTATIVAS
        )

    def _registrar(self, request):
        ip = ip_da_requisicao(request)
        TentativaDeLogin.objects.create(ip=ip)
        # Limpa o que saiu da janela na mesma passada: a tabela so guarda o que a
        # regra ainda le, e nao precisa de rotina de limpeza.
        TentativaDeLogin.objects.filter(
            ip=ip, criado_em__lt=timezone.now() - JANELA_DE_TENTATIVAS
        ).delete()


def _resumo(usuario):
    """Os números que cada papel precisa ver ao entrar.

    Só contagens: o painel é uma porta, não um relatório. Cada número leva a uma
    tela que já existe e já sabe filtrar - repetir a lista aqui seria manter duas
    definições do mesmo recorte.
    """
    if usuario.e_coordenador:
        return [
            {
                "rotulo": "Aguardando aprovação",
                "valor": Curso.objects.filter(status=StatusCurso.AGUARDANDO_COORDENADOR).count(),
                "url": "fila_coordenacao",
            },
            {
                "rotulo": "Solicitações a responder",
                "valor": Solicitacao.objects.filter(
                    status__in=[Solicitacao.RECEBIDA, Solicitacao.EM_ANALISE]
                ).count(),
                "url": "solicitacoes",
            },
            {
                "rotulo": "Cursos no catálogo",
                "valor": Curso.objects.filter(status=StatusCurso.PUBLICADO).count(),
                "url": "cursos_no_catalogo",
            },
            {
                "rotulo": "Turmas agendadas",
                "valor": Turma.objects.filter(status=Turma.AGENDADA).count(),
                "url": "minhas_turmas",
            },
        ]

    if usuario.e_professor:
        # Por vinculo de equipe, e nao por `professor_responsavel`: e o mesmo
        # recorte de `meus_cursos`, que e a tela para onde os dois cartoes levam.
        # Contado de um jeito e listado de outro, o numero do cartao nunca batia
        # com o que a pessoa via depois de clicar.
        meus = Curso.objects.filter(membros__pessoa=usuario)
        return [
            {
                "rotulo": "Cursos publicados",
                "valor": meus.filter(status=StatusCurso.PUBLICADO).distinct().count(),
                "url": "meus_cursos",
                # O recorte viaja com o cartao: `meus_cursos` filtra pelo mesmo
                # criterio, entao o numero e a lista nao tem como divergir.
                "estado": "publicados",
            },
            {
                "rotulo": "Cursos em desenvolvimento",
                "valor": meus.filter(
                    status__in=STATUS_EM_DESENVOLVIMENTO
                ).distinct().count(),
                "url": "meus_cursos",
                "estado": "desenvolvimento",
            },
            {
                # Conta ENTREGAVEIS, e nao cursos com entregavel em revisao: e o
                # mesmo recorte da `fila_revisao`, que lista um item por
                # entregavel. Dois entregaveis do mesmo curso sao dois na fila, e
                # o `.distinct()` por curso que havia aqui dizia um.
                "rotulo": "Entregáveis para revisar",
                # O mesmo recorte que a tela lista, e nao uma segunda contagem:
                # os que esperam decisao MAIS os que voltaram para a equipe.
                "valor": sum(len(g) for g in Entregavel.objects.na_revisao_de(usuario)),
                "url": "fila_revisao",
            },
        ]

    return [
        {
            "rotulo": "Cursos em que você produz",
            "valor": Curso.objects.filter(membros__pessoa=usuario).distinct().count(),
            "url": "meus_cursos",
        },
    ]


@login_required
def painel(request):
    return render(request, "painel.html", {"resumo": _resumo(request.user)})


@require_http_methods(["GET", "POST"])
def primeiro_acesso(request, token):
    """Tela do convite: cria a senha e completa o cadastro.

    Aberta sem login de proposito -- quem chega aqui ainda nao tem senha. O token
    e a credencial, e `consumir_convite` e quem confere se ele ainda vale.
    """
    convite = ConviteAluno.objects.filter(token=token).first()
    if convite is None or not convite.valido:
        return render(request, "contas/convite_invalido.html")

    form = PrimeiroAcessoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            usuario = services.consumir_convite(
                token,
                senha=form.cleaned_data["senha"],
                cpf=form.cleaned_data["cpf"],
                matricula=form.cleaned_data["matricula"],
                telefone=form.cleaned_data["telefone"],
            )
        except ValidationError as erro:
            for mensagem in erro.messages:
                form.add_error(None, mensagem)
        else:
            login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
            return redirect("painel")

    return render(
        request, "contas/primeiro_acesso.html", {"form": form, "convite": convite}
    )


@login_required
@require_http_methods(["GET", "POST"])
def pessoas(request):
    """Quem e professor, quem e coordenacao, e o botao para mudar isso."""
    # Checagem local pelo mesmo motivo de `_garante_coordenacao`: `contas` nao
    # importa `cursos`.
    if not request.user.e_coordenador:
        raise PermissionDenied("Área da coordenação.")

    if request.method == "POST":
        alvo = get_object_or_404(Usuario, pk=request.POST.get("usuario"))
        acao = request.POST.get("acao")
        try:
            # Igualdade explicita nos dois ramos, sem pega-tudo: um valor
            # inesperado nao pode cair na acao destrutiva. O mesmo defeito ja
            # apareceu duas vezes neste projeto (decidir_curso e o ramo RECUSAR
            # das solicitacoes).
            if acao == "PROMOVER":
                services.promover_a_coordenador(alvo, por=request.user)
                messages.success(request, f"{alvo.nome_completo} agora é coordenador.")
            elif acao == "REBAIXAR":
                services.rebaixar_a_professor(alvo, por=request.user)
                messages.success(request, f"{alvo.nome_completo} voltou a ser professor.")
            else:
                messages.error(request, "Ação não reconhecida.")
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        return redirect("pessoas")

    equipe = Usuario.objects.filter(
        papel__in=[Usuario.PROFESSOR, Usuario.COORDENADOR]
    ).order_by("nome_completo")
    return render(request, "contas/pessoas.html", {"equipe": equipe})
