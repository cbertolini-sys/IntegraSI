from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_http_methods

from apps.contas.models import Usuario
from apps.cursos import permissions, services, validacoes
from apps.cursos.choices import StatusEntregavel
from apps.cursos.forms import FichaCursoForm, PropostaForm
from apps.cursos.models import Curso, Entregavel, MembroEquipe
from apps.referenciais.models import Referencial


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
    contexto = {"curso": curso, "form": form, "pendencias": validacoes.dados_do_curso(curso)}
    contexto.update(contexto_das_habilidades(request, curso))
    contexto["publico_escolar"] = form.publico_e_escolar()
    return render(request, "cursos/ficha.html", contexto)


def contexto_das_habilidades(request, curso):
    """Monta o bloco a partir do que a tela tem AGORA, e nao do que esta gravado:
    a pessoa acabou de trocar o select e ainda nao salvou.

    O agrupamento e sequencial e depende de a ordenacao trazer as competencias de
    uma mesma categoria juntas, o que Competencia.Meta.ordering garante enquanto a
    ordem do CSV seguir o documento (teste em test_bncc.py).
    """
    from apps.referenciais.choices import etapa_do_referencial, rotulo_da_competencia
    from apps.referenciais.models import Referencial

    # `in request.GET` e nao `.get(...) or ...`: os dois campos precisam
    # distinguir "veio vazio" de "nao veio". Com o `or`, escolher Nenhum mandava
    # referencial="" e caia de volta no gravado, entao as habilidades continuavam
    # na tela depois de a pessoa tirar o referencial.
    referencial_id = request.GET["referencial"] if "referencial" in request.GET else curso.referencial_id
    etapa_ano = request.GET["etapa_ano"] if "etapa_ano" in request.GET else curso.etapa_ano
    referencial = Referencial.objects.filter(pk=referencial_id or 0).first()
    etapa = etapa_do_referencial(etapa_ano)

    grupos = []
    if referencial and etapa:
        for competencia in referencial.competencias.filter(etapa=etapa).select_related("categoria"):
            if not grupos or grupos[-1]["categoria"] != competencia.categoria:
                grupos.append({"categoria": competencia.categoria, "itens": []})
            grupos[-1]["itens"].append(competencia)
    return {
        "curso": curso,
        "referencial": referencial,
        "etapa": etapa,
        "grupos": grupos,
        "rotulo": rotulo_da_competencia(etapa, plural=True),
        "escolhidas": set(curso.competencias.values_list("pk", flat=True)),
    }


def publico_da_tela(request, curso):
    """O tipo de publico que a tela tem agora: o enviado, se veio, senao o gravado."""
    return request.GET["tipo_publico"] if "tipo_publico" in request.GET else curso.tipo_publico


@login_required
def ficha_etapa(request, pk):
    """O campo de etapa, trocado quando muda o tipo de publico.

    Regiao propria, e nao junto do referencial: os dois reagem ao mesmo evento mas
    ficam em secoes diferentes da ficha, e uni-los obrigaria a trocar metade do
    formulario para mexer num select.
    """
    from apps.cursos.forms import FichaCursoForm

    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(
        permissions.pode_editar_ficha(request.user, curso),
        "Somente a equipe do curso edita a ficha, e apenas enquanto ele está em produção.",
    )
    form = FichaCursoForm(instance=curso, publico=publico_da_tela(request, curso))
    escolhida = request.GET.get("etapa_ano") or ""
    # A etapa antiga chega na mesma requisicao que o tipo novo, porque o HTMX manda
    # o valor atual do select junto. So continua marcada se ainda existir na lista.
    if escolhida not in dict(form.fields["etapa_ano"].choices):
        escolhida = ""
    form.initial["etapa_ano"] = escolhida
    return render(request, "cursos/_etapa.html", {"curso": curso, "form": form})


@login_required
def ficha_referencial(request, pk):
    """O select de referencial mais o bloco de habilidades, trocados juntos quando
    muda o tipo de publico.

    Juntos porque a troca cascateia: sumindo o referencial, as habilidades dele
    nao podem ficar na tela.
    """
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(
        permissions.pode_editar_ficha(request.user, curso),
        "Somente a equipe do curso edita a ficha, e apenas enquanto ele está em produção.",
    )
    return render(request, "cursos/_referencial.html", contexto_do_referencial(request, curso))


def contexto_do_referencial(request, curso):
    """Monta o formulario com o publico que a tela tem AGORA, para o select de
    referencial ja vir filtrado, e junta o contexto do bloco de habilidades."""
    from apps.cursos.forms import FichaCursoForm

    form = FichaCursoForm(instance=curso, publico=publico_da_tela(request, curso))
    escolar = form.publico_e_escolar()
    # O referencial escolhido so continua marcado se ainda estiver na lista: quando
    # o publico deixa de ser escolar, o select volta para "Nenhum" na cara da
    # pessoa, em vez de manter uma escolha que nao vale mais.
    escolhido = request.GET.get("referencial") or ""
    if escolhido and not form.fields["referencial"].queryset.filter(pk=escolhido).exists():
        escolhido = ""
    form.initial["referencial"] = escolhido or None

    contexto = {"form": form, "publico_escolar": escolar}
    contexto.update(contexto_das_habilidades(request, curso))
    if not escolhido:
        contexto["referencial"] = None
        contexto["grupos"] = []
    return contexto


@login_required
def ficha_habilidades(request, pk):
    """O bloco de habilidades da ficha, trocado por HTMX quando muda o
    referencial ou a etapa.

    Guarda propria: e um GET, e ela responde sozinha. Sem ela, qualquer pessoa
    logada leria a ficha de qualquer curso por esta url.
    """
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(
        permissions.pode_editar_ficha(request.user, curso),
        "Somente a equipe do curso edita a ficha, e apenas enquanto ele está em produção.",
    )
    return render(request, "cursos/_habilidades.html", contexto_das_habilidades(request, curso))


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


@login_required
@require_POST
def remover_da_equipe(request, pk, membro_pk):
    curso = get_object_or_404(Curso, pk=pk)
    permissions.garante(permissions.pode_gerir_equipe(request.user, curso), "Curso de outro professor.")
    membro = get_object_or_404(MembroEquipe, pk=membro_pk)
    try:
        services.remover_membro(curso, membro, por=request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, f"{membro.pessoa.nome_completo} saiu da equipe.")
    return redirect("equipe", pk=curso.pk)


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
