from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.catalogo.models import Solicitacao, SugestaoDeCurso
from apps.cursos import permissions
from apps.turmas import services
from apps.turmas.forms import TurmaForm
from apps.contas.paginacao import paginar
from apps.turmas.models import Turma

# Valores enviados pelo formulário: gravados/transmitidos sem acento e nunca
# alterados por passada de texto (CLAUDE.md). Só os rótulos dos botões são
# português acentuado.
ACEITAR = "ACEITAR"
RECUSAR = "RECUSAR"

PENDENTES = [Solicitacao.RECEBIDA, Solicitacao.EM_ANALISE]
PENDENTES_SUGESTAO = [SugestaoDeCurso.RECEBIDA, SugestaoDeCurso.EM_ANALISE]


@login_required
def solicitacoes(request):
    # @login_required vem antes de propósito: pode_publicar lê usuario.e_coordenador,
    # que AnonymousUser não tem. Sem o redirecionamento primeiro, um visitante
    # anônimo receberia AttributeError (500) em vez da tela de login.
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    pendentes = Solicitacao.objects.filter(status__in=PENDENTES).select_related("curso")
    # A fila de pendentes fica INTEIRA: e trabalho a fazer, e esconder metade do
    # que espera resposta seria pior que a pagina longa. O historico das
    # respondidas pagina, e com isso perde o `[:20]` que cortava sem dizer.
    respondidas = Solicitacao.objects.exclude(status__in=PENDENTES).select_related("curso")
    pagina = paginar(request, respondidas)
    return render(
        request,
        "turmas/solicitacoes.html",
        {"pendentes": pendentes, "respondidas": pagina, "pagina": pagina},
    )


@login_required
def responder_solicitacao(request, pk):
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    solicitacao = get_object_or_404(Solicitacao.objects.select_related("curso"), pk=pk)
    decisao = request.POST.get("decisao") if request.method == "POST" else None

    # A página tem dois formulários. Ligar o de aceitar a request.POST em toda
    # requisição o deixaria *bound* e vazio quando quem postou queria recusar, e
    # o ramo de recusa não chama is_valid() - a pessoa voltaria para a tela com
    # "Este campo é obrigatório." em campos que não tocou. Ele só se liga aos
    # dados quando a decisão é, de fato, aceitar.
    if decisao == ACEITAR:
        form = TurmaForm(request.POST)
    else:
        form = TurmaForm(initial={"vagas": solicitacao.num_participantes})

    if decisao == ACEITAR and form.is_valid():
        dados = dict(form.cleaned_data)
        professor = dados.pop("professor")
        try:
            services.aceitar_solicitacao(
                solicitacao, professor=professor, dados_turma=dados, por=request.user
            )
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        else:
            messages.success(request, "Turma agendada e solicitante avisado.")
            return redirect("solicitacoes")
    elif decisao == RECUSAR:
        # Nada de "tudo que não é aceitar é recusa": um POST sem decisao recusaria
        # a solicitação e dispararia o e-mail ao solicitante por omissão.
        try:
            services.recusar_solicitacao(
                solicitacao, por=request.user, resposta=request.POST.get("resposta", "")
            )
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
        else:
            messages.success(request, "Solicitante avisado.")
            return redirect("solicitacoes")

    return render(request, "turmas/responder.html", {"solicitacao": solicitacao, "form": form})


@login_required
def minhas_turmas(request):
    # Guarda explícita, e não o recorte por professor sozinho: sem ela o aluno
    # recebe uma página vazia só porque Turma.professor nunca aponta para um
    # aluno - proteção por acidente de dado, que nenhum teste consegue prender
    # porque não há guarda para apagar.
    permissions.garante(
        request.user.e_professor or request.user.e_coordenador,
        "Área do professor e da coordenação.",
    )
    turmas = Turma.objects.select_related("curso")
    if not request.user.e_coordenador:
        turmas = turmas.filter(professor=request.user)
    pagina = paginar(request, turmas)
    return render(
        request, "turmas/minhas_turmas.html", {"turmas": pagina, "pagina": pagina}
    )


@login_required
def sugestoes(request):
    """As demandas por cursos que ainda nao existem.

    Tela separada da de solicitacoes de proposito: sao decisoes diferentes.
    Responder uma solicitacao e agendar; responder uma sugestao e decidir se a
    universidade vai produzir um curso novo. Juntar as duas obrigaria quem
    responde a separar na cabeca o que o sistema pode separar na tela.
    """
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    pendentes = SugestaoDeCurso.objects.filter(status__in=PENDENTES_SUGESTAO)
    respondidas = SugestaoDeCurso.objects.exclude(status__in=PENDENTES_SUGESTAO)
    pagina = paginar(request, respondidas)
    return render(
        request,
        "turmas/sugestoes.html",
        {"pendentes": pendentes, "respondidas": pagina, "pagina": pagina},
    )


@login_required
@require_http_methods(["GET", "POST"])
def responder_sugestao(request, pk):
    permissions.garante(permissions.pode_publicar(request.user), "Área da coordenação.")
    sugestao = get_object_or_404(SugestaoDeCurso, pk=pk)

    if request.method == "POST":
        # Igualdade explicita nos dois ramos, sem pega-tudo: uma `decisao`
        # inesperada nao pode cair em nenhum dos dois. O ramo pega-tudo ja mordeu
        # este projeto tres vezes (decidir_curso, o RECUSAR das solicitacoes e a
        # alocacao de aluno na tela de equipe).
        decisao = request.POST.get("decisao")
        resposta = request.POST.get("resposta", "")
        servico = None
        if decisao == "ACEITAR":
            servico = services.aceitar_sugestao
        elif decisao == "RECUSAR":
            servico = services.recusar_sugestao

        if servico is None:
            messages.error(request, "Ação não reconhecida.")
        else:
            try:
                servico(sugestao, por=request.user, resposta=resposta)
            except ValidationError as erro:
                for mensagem in erro.messages:
                    messages.error(request, mensagem)
            else:
                messages.success(request, "Sugestão respondida. Quem sugeriu foi avisado por e-mail.")
                return redirect("sugestoes")

    return render(request, "turmas/responder_sugestao.html", {"sugestao": sugestao})
