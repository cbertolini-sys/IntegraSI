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
    # Restrito a professor (spec 3): Curso.clean() exige professor_responsavel.
    # e_professor, e esta view sempre chama services.criar_curso com
    # professor_responsavel=request.user. Deixar coordenador entrar aqui so faria
    # sentido com uma tela para ele escolher outro professor responsavel - isso e
    # tela nova, nao conserto.
    permissions.garante(request.user.e_professor, "Somente professor cria proposta de curso.")
    form = CursoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dados = dict(form.cleaned_data)
        temas = dados.pop("temas", [])
        curso = services.criar_curso(professor_responsavel=request.user, **dados)
        # services.definir_temas, nao curso.temas.set() direto: alem de checar
        # permissao, e quem reindexa vetor_temas (Task 4). Escrever a M2M aqui na
        # mao deixava todo curso proposto com tema por esta tela invisivel na
        # busca por tema ate alguem, por coincidencia, renomear um dos temas pelo
        # Admin - achado da revisao do Task 4. A checagem de permissao dentro do
        # servico e redundante aqui (quem propos o curso e sempre o responsavel),
        # mas concentrar a escrita num lugar so e o que evita a proxima tela
        # repetir o mesmo esquecimento.
        services.definir_temas(curso, temas, por=request.user)
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
            for mensagem in erro.messages:
                messages.error(request, mensagem)
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
