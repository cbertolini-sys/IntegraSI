from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.contas.paginacao import paginar
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
    # Pagina como as outras seis listagens do sistema. A fila e caixa de entrada
    # que esvazia, entao na pratica cabe numa pagina so - mas "na pratica cabe"
    # nao e garantia, e era a unica listagem sem o corte.
    pagina = paginar(request, cursos)
    return render(
        request,
        "cursos/fila_coordenacao.html",
        {"cursos": pagina, "pagina": pagina},
    )


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
    pagina = paginar(request, cursos)
    return render(
        request,
        "cursos/cursos_no_catalogo.html",
        {"cursos": pagina, "pagina": pagina},
    )


@login_required
def analisar_curso(request, pk):
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    curso = get_object_or_404(Curso, pk=pk)
    # Lista fechada, e nao o endereco que vier no parametro: refletir num `href`
    # um valor de fora e como se abre um redirecionamento para qualquer lugar.
    if request.GET.get("voltar") == "catalogo":
        volta = (reverse("cursos_no_catalogo"), "Voltar aos cursos")
    else:
        volta = (reverse("fila_coordenacao"), "Voltar à fila")
    return render(
        request,
        "cursos/analisar_curso.html",
        {
            "curso": curso,
            "volta_url": volta[0],
            "volta_rotulo": volta[1],
            "transicoes": curso.transicoes.select_related("usuario").order_by("-criado_em"),
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
            # forjada) devolvia o curso ao professor e reabria os seis
            # entregaveis em silencio. Mesmo defeito ja corrigido em
            # turmas.views.responder_solicitacao.
            messages.error(request, "Decisão não reconhecida.")
            return redirect("analisar_curso", pk=curso.pk)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect("analisar_curso", pk=curso.pk)
    return redirect("fila_coordenacao" if veio_da_fila else "cursos_no_catalogo")


@login_required
@require_http_methods(["GET", "POST"])
def nova_versao(request, pk):
    """Abre a proxima versao de um curso publicado (spec 4.5, passo 1).

    A guarda vale na entrada, e nao so no POST: o GET nao chama servico nenhum,
    entao sem ela qualquer pessoa logada abria a pagina e lia o titulo de um curso
    de outra equipe - o plano deixava esse caminho descoberto. No POST ela e a
    primeira de duas (o servico repete a checagem para quem o chama direto), por
    isso quem prende a guarda do servico continua sendo test_versoes.py, com a
    mensagem, e nao um 403 de tela.
    """
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(
        permissions.pode_abrir_versao(request.user, curso),
        "Somente o professor responsável ou a coordenação abre nova versão.",
    )
    if request.method == "POST":
        try:
            nova = services.abrir_nova_versao(
                curso, por=request.user, motivo=request.POST.get("motivo", "")
            )
        except ValidationError as erro:
            # Todas as mensagens, e nao erro.messages[0]: uma recusa com duas
            # razoes mandaria a pessoa corrigir a primeira so para esbarrar na
            # segunda. Mesmo tratamento de decidir_curso, acima.
            for mensagem in erro.messages:
                messages.error(request, mensagem)
            return redirect("curso", pk=curso.pk)
        messages.success(request, f"Versão {nova.versao} aberta. Monte a equipe para começar.")
        # Para a equipe DA NOVA versao: ela nasce sem membros de proposito (spec
        # 4.5, passo 3), e sem equipe ninguem produz nada.
        return redirect("equipe", pk=nova.pk)
    return render(request, "cursos/nova_versao.html", {"curso": curso})
