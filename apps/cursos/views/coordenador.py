from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.cursos import permissions, services
from apps.cursos.choices import StatusCurso
from apps.cursos.models import Curso


@login_required
def fila_coordenacao(request):
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    cursos = Curso.objects.filter(status=StatusCurso.AGUARDANDO_COORDENADOR).select_related(
        "professor_responsavel", "edicao"
    )
    return render(request, "cursos/fila_coordenacao.html", {"cursos": cursos})


@login_required
def analisar_curso(request, pk):
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    curso = get_object_or_404(Curso, pk=pk)
    return render(
        request,
        "cursos/analisar_curso.html",
        {"curso": curso, "entregaveis": curso.entregaveis.prefetch_related("secoes", "anexos")},
    )


@login_required
@require_POST
def decidir_curso(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    comentario = request.POST.get("comentario", "")
    try:
        if request.POST.get("decisao") == "PUBLICAR":
            services.publicar_curso(curso, por=request.user)
            messages.success(request, "Curso publicado no catálogo.")
        else:
            services.devolver_curso(curso, por=request.user, comentario=comentario)
            messages.success(request, "Curso devolvido ao professor.")
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect("analisar_curso", pk=curso.pk)
    return redirect("fila_coordenacao")
