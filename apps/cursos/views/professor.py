from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from apps.contas.models import Usuario
from apps.cursos import permissions, services, validacoes
from apps.cursos.choices import StatusEntregavel
from apps.cursos.forms import FichaCursoForm, PropostaForm
from apps.cursos.models import Curso, Entregavel


@login_required
@require_http_methods(["GET", "POST"])
def nova_proposta(request):
    # Coordenador entra aqui a partir do Plano 5: ele e professor (regra 1) e a
    # view sempre cria com professor_responsavel=request.user, entao ele fica
    # responsavel pelo proprio curso -- nao e preciso escolher outra pessoa.
    permissions.garante(
        permissions.pode_criar_curso(request.user), "Somente professor cria proposta de curso."
    )
    form = PropostaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        # O try e necessario: sem edicao corrente aberta, criar_curso levanta
        # ValidationError, e sem captura a tela devolveria 500 para o professor.
        try:
            curso = services.criar_curso(professor_responsavel=request.user, **form.cleaned_data)
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        else:
            messages.success(
                request, "Proposta criada. Monte a equipe e preencha a ficha do curso."
            )
            return redirect("equipe", pk=curso.pk)
    return render(request, "cursos/nova_proposta.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def ficha(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    # Guarda propria da view, alem da que atualizar_ficha ja faz: e esta que
    # responde ao GET, onde o servico nem chega a ser chamado.
    permissions.garante(
        permissions.pode_editar_ficha(request.user, curso),
        "Somente a equipe do curso edita a ficha, e apenas enquanto ele está em produção.",
    )
    form = FichaCursoForm(request.POST or None, instance=curso)
    if request.method == "POST" and form.is_valid():
        services.atualizar_ficha(curso, form.cleaned_data, por=request.user)
        messages.success(request, "Ficha do curso atualizada.")
        return redirect("curso", pk=curso.pk)
    return render(
        request,
        "cursos/ficha.html",
        {"curso": curso, "form": form, "pendencias": validacoes.dados_do_curso(curso)},
    )


@login_required
@require_http_methods(["GET", "POST"])
def equipe(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(permissions.pode_gerir_equipe(request.user, curso), "Curso de outro professor.")
    if request.method == "POST":
        # Um campo escondido distingue os dois formularios da tela. Sem ele, o
        # POST do select cairia no ramo do aluno e viraria "informe o nome".
        if request.POST.get("acao") == "professor":
            _alocar_professor(request, curso)
        else:
            _alocar_aluno(request, curso)
        return redirect("equipe", pk=curso.pk)
    return render(
        request,
        "cursos/equipe.html",
        {"curso": curso, "professores": _professores_disponiveis(curso)},
    )


def _professores_disponiveis(curso):
    """Professores e coordenadores que ainda nao estao na equipe deste curso.

    O `exclude` pelo related_name `equipes` tira o responsavel junto: ele e membro
    desde a criacao (spec 4.1), e oferece-lo no select so daria erro de unicidade.
    """
    return (
        Usuario.objects.filter(
            papel__in=(Usuario.PROFESSOR, Usuario.COORDENADOR), is_active=True
        )
        .exclude(equipes__curso=curso)
        .order_by("nome_completo")
    )


def _alocar_professor(request, curso):
    escolhido = Usuario.objects.filter(pk=request.POST.get("professor") or 0).first()
    try:
        membro = services.alocar_professor(curso, escolhido, por=request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, f"{membro.pessoa.nome_completo} entrou na equipe.")


def _alocar_aluno(request, curso):
    try:
        membro = services.alocar_aluno(
            curso,
            nome=request.POST.get("nome", ""),
            email=request.POST.get("email", ""),
            por=request.user,
            # O convite precisa de um endereco absoluto: o e-mail e lido fora
            # do navegador, onde caminho relativo nao resolve.
            base_url=request.build_absolute_uri("/").rstrip("/"),
        )
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(
            request,
            f"{membro.pessoa.nome_completo} entrou na equipe. "
            "Enviamos o convite de primeiro acesso por e-mail.",
        )


@login_required
def fila_revisao(request):
    entregaveis = Entregavel.objects.filter(
        status=StatusEntregavel.EM_REVISAO, curso__professor_responsavel=request.user
    ).select_related("curso")
    return render(request, "cursos/fila_revisao.html", {"entregaveis": entregaveis})


@login_required
def revisar(request, pk):
    entregavel = get_object_or_404(Entregavel, pk=pk)
    permissions.garante(permissions.pode_revisar(request.user, entregavel.curso), "Curso de outro professor.")
    return render(
        request,
        "cursos/revisar.html",
        {"entregavel": entregavel, "pendencias": validacoes.pendencias(entregavel)},
    )


@login_required
@require_POST
def submeter_curso(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    try:
        services.submeter_ao_coordenador(curso, por=request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, "Curso enviado para aprovação da coordenação.")
    return redirect("curso", pk=curso.pk)


@login_required
@require_POST
def decidir(request, pk):
    entregavel = get_object_or_404(Entregavel, pk=pk)
    comentario = request.POST.get("comentario", "")
    try:
        if request.POST.get("decisao") == "APROVAR":
            services.aprovar_entregavel(entregavel, por=request.user, comentario=comentario)
            messages.success(request, "Entregável aprovado.")
        else:
            services.devolver_entregavel(entregavel, por=request.user, comentario=comentario)
            messages.success(request, "Entregável devolvido à equipe.")
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect("revisar", pk=entregavel.pk)
    return redirect("fila_revisao")
