from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.catalogo.models import Solicitacao
from apps.contas import services
from apps.contas.forms_convite import PrimeiroAcessoForm
from apps.contas.models import ConviteAluno, Usuario
from apps.cursos.choices import StatusCurso, StatusEntregavel
from apps.cursos.models import Curso
from apps.turmas.models import Turma


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
        meus = Curso.objects.filter(professor_responsavel=usuario)
        return [
            {
                "rotulo": "Cursos sob sua responsabilidade",
                "valor": meus.count(),
                "url": "meus_cursos",
            },
            {
                "rotulo": "Entregáveis para revisar",
                "valor": meus.filter(
                    entregaveis__status=StatusEntregavel.EM_REVISAO
                ).distinct().count(),
                "url": "fila_revisao",
            },
            {
                "rotulo": "Turmas sob sua condução",
                "valor": Turma.objects.filter(professor=usuario).count(),
                "url": "minhas_turmas",
            },
        ]

    return [
        {
            "rotulo": "Cursos em que você produz",
            "valor": Curso.objects.filter(membros__aluno=usuario).distinct().count(),
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
