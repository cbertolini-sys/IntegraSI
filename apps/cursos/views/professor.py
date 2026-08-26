from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from apps.contas.models import Usuario
from apps.cursos import permissions, services, validacoes
from apps.cursos.choices import StatusEntregavel
from apps.cursos.forms import CursoForm
from apps.cursos.models import Curso, Entregavel


@login_required
@require_http_methods(["GET", "POST"])
def nova_proposta(request):
    permissions.garante(
        request.user.e_professor or request.user.e_coordenador,
        "Somente professor cria proposta de curso.",
    )
    form = CursoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dados = dict(form.cleaned_data)
        temas = dados.pop("temas", [])
        curso = services.criar_curso(professor_responsavel=request.user, **dados)
        curso.temas.set(temas)
        messages.success(request, "Proposta criada. Monte a equipe para começar a produção.")
        return redirect("equipe", pk=curso.pk)
    return render(request, "cursos/nova_proposta.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def equipe(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(permissions.pode_gerir_equipe(request.user, curso), "Curso de outro professor.")
    if request.method == "POST":
        aluno_pk = request.POST.get("aluno")
        if not aluno_pk:
            messages.error(request, "Selecione um aluno para adicionar.")
            return redirect("equipe", pk=curso.pk)
        aluno = get_object_or_404(Usuario, pk=aluno_pk)
        try:
            services.adicionar_membro(curso, aluno, por=request.user)
        except ValidationError as erro:
            messages.error(request, erro.messages[0])
        else:
            messages.success(request, f"{aluno.nome_completo} entrou na equipe.")
        return redirect("equipe", pk=curso.pk)
    candidatos = Usuario.objects.filter(papel=Usuario.ALUNO, is_active=True).exclude(
        equipes__curso=curso
    )
    return render(request, "cursos/equipe.html", {"curso": curso, "candidatos": candidatos})


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
        messages.error(request, erro.messages[0])
        return redirect("revisar", pk=entregavel.pk)
    return redirect("fila_revisao")
