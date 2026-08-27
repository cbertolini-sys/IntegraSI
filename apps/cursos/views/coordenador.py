from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.cursos import permissions, services
from apps.cursos.choices import StatusCurso
from apps.cursos.models import Curso

# Valores transmitidos pelo formulario: sem acento e nunca alterados por passada
# de texto (CLAUDE.md). So os rotulos dos botoes sao portugues acentuado.
PUBLICAR = "PUBLICAR"
DEVOLVER = "DEVOLVER"
DESPUBLICAR = "DESPUBLICAR"

NO_CATALOGO = [StatusCurso.PUBLICADO, StatusCurso.DESPUBLICADO]


@login_required
def fila_coordenacao(request):
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    cursos = Curso.objects.filter(status=StatusCurso.AGUARDANDO_COORDENADOR).select_related(
        "professor_responsavel", "edicao"
    )
    return render(request, "cursos/fila_coordenacao.html", {"cursos": cursos})


@login_required
def cursos_no_catalogo(request):
    """Cursos que ja passaram pela fila: os publicados e os despublicados.

    Sem esta listagem, despublicar e republicar seriam capacidades sem porta -
    fila_coordenacao mostra so AGUARDANDO_COORDENADOR, entao nao havia de onde
    partir para um curso publicado (achado Importante 2 da revisao de branch).
    Tela separada da fila de proposito: a fila e uma caixa de entrada que esvazia,
    esta e um inventario do catalogo.
    """
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    cursos = Curso.objects.filter(status__in=NO_CATALOGO).select_related(
        "professor_responsavel", "edicao"
    )
    return render(request, "cursos/cursos_no_catalogo.html", {"cursos": cursos})


@login_required
def analisar_curso(request, pk):
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    curso = get_object_or_404(Curso, pk=pk)
    return render(
        request,
        "cursos/analisar_curso.html",
        {
            "curso": curso,
            "entregaveis": curso.entregaveis.prefetch_related("secoes", "anexos"),
            # Quais decisoes cabem neste curso agora. Calculado aqui, e nao
            # comparando status por string no template: o valor gravado nao
            # aparece no HTML, e quem manda continua sendo services.py - estes
            # booleanos so escondem um botao que o servico recusaria.
            "pode_decidir": curso.status == StatusCurso.AGUARDANDO_COORDENADOR,
            "pode_despublicar": curso.status == StatusCurso.PUBLICADO,
            "pode_republicar": curso.status == StatusCurso.DESPUBLICADO,
        },
    )


@login_required
@require_POST
def decidir_curso(request, pk):
    # Antes do get_object_or_404, e nao depois: a ordem e a regra. Com a busca
    # primeiro, quem nao e coordenador distinguia curso existente de inexistente
    # pela resposta (302 num caminho que nao chama servico nenhum, contra 404), o
    # que e mais do que ele pode saber - analisar_curso devolve 403 nos dois casos.
    #
    # Nao e guarda em dobro com a do servico: no ramo de decisao desconhecida
    # nenhum servico e chamado, entao aqui esta guarda carrega o peso sozinha e um
    # POST basta para prende-la. Nos ramos que chamam servico, ela passa a ser a
    # primeira das duas - por isso quem prende a guarda de publicar_curso continua
    # sendo test_professor_nao_publica, no nivel do servico.
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    curso = get_object_or_404(Curso, pk=pk)
    decisao = request.POST.get("decisao")
    comentario = request.POST.get("comentario", "")
    # De onde o curso saiu decide para onde a tela volta - e precisa ser lido
    # antes de o servico mudar o status.
    veio_da_fila = curso.status == StatusCurso.AGUARDANDO_COORDENADOR
    try:
        if decisao == PUBLICAR:
            services.publicar_curso(curso, por=request.user)
            messages.success(request, "Curso publicado no catálogo.")
        elif decisao == DEVOLVER:
            services.devolver_curso(curso, por=request.user, comentario=comentario)
            messages.success(request, "Curso devolvido ao professor.")
        elif decisao == DESPUBLICAR:
            services.despublicar_curso(curso, por=request.user, motivo=comentario)
            messages.success(request, "Curso retirado do catálogo.")
        else:
            # Roteamento explicito, e nao "tudo que nao e publicar e devolver": com
            # o else como pega-tudo, um POST com decisao ausente ou desconhecida
            # (botao novo no template, formulario submetido por Enter, requisicao
            # forjada) devolvia o curso ao professor e reabria os cinco
            # entregaveis em silencio. Mesmo defeito ja corrigido em
            # turmas.views.responder_solicitacao.
            messages.error(request, "Decisão não reconhecida.")
            return redirect("analisar_curso", pk=curso.pk)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect("analisar_curso", pk=curso.pk)
    return redirect("fila_coordenacao" if veio_da_fila else "cursos_no_catalogo")
