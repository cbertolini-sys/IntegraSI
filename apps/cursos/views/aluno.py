from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.contas.paginacao import paginar
from apps.cursos import permissions, services, validacoes
from apps.cursos.arquivos import TAMANHO_BLOCO, calcula_hash
from apps.cursos.choices import STATUS_EM_DESENVOLVIMENTO, StatusCurso, TipoMidia
from apps.cursos.forms import AnexoForm, EnvioDeVideoForm, SecaoForm, oferece_anexo
from apps.cursos.models import Anexo, Arquivo, Curso, Entregavel, Secao
from apps.cursos.views.upload import UUID_MODELO


@login_required
def meus_cursos(request):
    # So o vinculo de equipe: desde o Plano 6 o professor responsavel e membro do
    # curso que responde (spec 4.1), entao o `| Q(professor_responsavel=...)` que
    # havia aqui virou termo morto. Foi apagado depois de a suite inteira passar
    # sem ele. Quem criar Curso fora de criar_curso precisa criar o MembroEquipe
    # junto, senao o curso some desta tela.
    cursos = Curso.objects.filter(membros__pessoa=request.user).distinct()
    # O mesmo recorte que o cartao do painel conta: contado de um jeito e listado
    # de outro, o numero nunca batia com o que a pessoa via depois de clicar.
    #
    # Igualdade explicita nos dois ramos, sem pega-tudo: um `estado` inesperado
    # mostra a lista inteira, e nao uma tela vazia que a pessoa leria como "perdi
    # meus cursos". O ramo pega-tudo ja mordeu este projeto duas vezes
    # (decidir_curso e o RECUSAR das solicitacoes).
    estado = request.GET.get("estado")
    if estado == "publicados":
        cursos = cursos.filter(status=StatusCurso.PUBLICADO)
    elif estado == "desenvolvimento":
        cursos = cursos.filter(status__in=STATUS_EM_DESENVOLVIMENTO)
    pagina = paginar(request, cursos)
    return render(
        request,
        "cursos/meus_cursos.html",
        {"cursos": pagina, "pagina": pagina, "estado": estado},
    )


@login_required
def curso(request, pk):
    # O cartao de progresso roda `validacoes.pendencias` nos seis entregaveis, e a
    # regra de cada um le anexos ou secoes: sem estes dois prefetch e uma consulta
    # por entregavel, na tela que a equipe mais abre.
    obj = get_object_or_404(
        Curso.objects.prefetch_related(
            "entregaveis__anexos", "entregaveis__secoes", "entregaveis__revisoes"
        ), pk=pk
    )
    permissions.garante(permissions.pode_ver_curso(request.user, obj), "Curso de outra equipe.")
    entregaveis = obj.entregaveis.all()
    # select_related("pessoa"): o template le membro.pessoa|como_pessoa para cada
    # membro da equipe - sem isto, uma consulta a mais por membro (fila_revisao.html
    # ja faz isto certo).
    membros = obj.membros.select_related("pessoa")
    return render(
        request,
        "cursos/curso.html",
        {
            "curso": obj,
            "entregaveis": entregaveis,
            "membros": membros,
            # Um booleano, e nao a condicao composta do plano
            # (`status == "PUBLICADO" and user.e_coordenador or status ==
            # "PUBLICADO" and user == curso.professor_responsavel`): aquela
            # repetia o status literal duas vezes no HTML, dependia da precedencia
            # entre `and` e `or` do template e reescrevia a mao a regra que
            # permissions.pode_abrir_versao ja diz. Calculado aqui, as duas
            # metades sao apagaveis uma de cada vez - e o valor gravado nao
            # aparece no template (mesmo padrao de analisar_curso).
            "pode_abrir_versao": obj.status == StatusCurso.PUBLICADO
            and permissions.pode_abrir_versao(request.user, obj),
            # Mesmo padrao: a decisao fica no Python, o template so pergunta pelo
            # resultado (spec 10, nada de `if` de permissao em template).
            "pode_editar_ficha": permissions.pode_editar_ficha(request.user, obj),
            # Mesmo padrao: a decisao no Python, o template so pergunta pelo
            # resultado. A tela de equipe existia desde o Plano 6 e nenhum
            # template linkava para ela - quem quisesse acrescentar um aluno
            # tinha que digitar a URL.
            "pode_gerir_equipe": permissions.pode_gerir_equipe(request.user, obj),
            # O rastro administrativo (spec 11), do mais novo para o mais antigo:
            # a ultima decisao e a que explica o estado de agora. O `ordering` do
            # model e cronologico porque ele serve ao historico, nao a leitura.
            "transicoes": obj.transicoes.select_related("usuario").order_by("-criado_em"),
        },
    )


def _rotulo_da_revisao(usuario, entregavel):
    """O que o professor pode fazer com este entregavel, ou None se nao for dele.

    Tres estados, um rotulo cada: decidir o que foi enviado, desfazer uma
    aprovacao enquanto o curso nao subiu, ou apenas ler o historico. O ultimo
    ainda vale a porta: e o historico que explica por que o entregavel esta como
    esta.
    """
    from apps.cursos.choices import STATUS_EDITAVEIS, StatusEntregavel

    if not permissions.pode_revisar(usuario, entregavel.curso):
        return None
    if entregavel.status == StatusEntregavel.EM_REVISAO:
        return "Revisar"
    if (
        entregavel.status == StatusEntregavel.APROVADO
        and entregavel.curso.status in STATUS_EDITAVEIS
    ):
        return "Reabrir"
    return "Ver decisões"


@login_required
def entregavel(request, pk):
    obj = get_object_or_404(Entregavel, pk=pk)
    permissions.garante(permissions.pode_ver_curso(request.user, obj.curso), "Curso de outra equipe.")
    return render(
        request,
        "cursos/entregavel.html",
        {
            "entregavel": obj,
            "pendencias": validacoes.pendencias(obj),
            # None quando o entregavel nao recebe anexo comum: e o template
            # perguntando pelo resultado, em vez de repetir a lista de tipos que
            # CAMPOS_DO_ANEXO ja tem (spec 10, nada de regra escrita no HTML).
            "form_anexo": AnexoForm(tipo=obj.tipo) if oferece_anexo(obj.tipo) else None,
            "pode_editar": permissions.pode_editar_producao(request.user, obj),
            # O caminho ate a tela de decisao. Ela so era alcancavel pela fila de
            # revisao, e a fila lista, por definicao, o que esta EM_REVISAO: um
            # entregavel aprovado nao tinha porta nenhuma, e o professor caia
            # aqui, na tela de PRODUCAO, sem revisao nem reabertura. O rotulo diz
            # o que cabe agora, e sai do Python porque e decisao, nao desenho.
            "rotulo_da_revisao": _rotulo_da_revisao(request.user, obj),
            "ultima_revisao": obj.revisoes.last(),
            # A sequencia das idas e vindas, na mesma marcacao da tela de decisao.
            "revisoes": obj.revisoes.select_related("revisor").order_by("-criado_em"),
            # O formulario de upload em blocos (so em VIDEOS) precisa levar ao JS o
            # tamanho do bloco e a marca que ele troca pelo identificador nas URLs
            # revertidas - nenhum dos dois pode estar escrito de novo dentro do JS.
            "tamanho_bloco": TAMANHO_BLOCO,
            "uuid_modelo": UUID_MODELO,
            # `auto_id` proprio porque os `id_...` do Django colidiriam com os do
            # AnexoForm no dia em que uma tela mostrasse os dois formularios.
            #
            # A faixa de duracao e o `maxlength` do titulo sairam daqui para dentro
            # do formulario, junto da ajuda de cada campo. Continuam vindo do campo
            # do Anexo e das constantes de validacoes, que e o que importa: sem o
            # `maxlength`, um titulo colado depois de meia hora de upload so era
            # recusado no servidor, e o aluno tentava de novo, outro giga em disco.
            "form_video": EnvioDeVideoForm(auto_id="video-%s"),
        },
    )


@login_required
@require_POST
def salvar_secao(request, pk):
    secao = get_object_or_404(Secao, pk=pk)
    permissions.garante(
        permissions.pode_editar_producao(request.user, secao.entregavel),
        "Este entregável não está aberto para edição.",
    )
    form = SecaoForm(request.POST, instance=secao)
    if not form.is_valid():
        mensagens = [mensagem for lista in form.errors.values() for mensagem in lista]
        return render(
            request,
            "cursos/_secao.html",
            {"secao": secao, "erro": " ".join(mensagens), "pode_editar": True},
        )
    secao = form.save(commit=False)
    secao.atualizado_por = request.user
    secao.save()
    return render(request, "cursos/_secao.html", {"secao": secao, "salvo": True, "pode_editar": True})


@login_required
@require_POST
def anexar(request, pk):
    obj = get_object_or_404(Entregavel, pk=pk)
    permissions.garante(
        permissions.pode_editar_producao(request.user, obj), "Este entregável não está aberto para edição."
    )
    # Depois da guarda de estado, e nao antes: as duas respondem 403, e invertida
    # a ordem o teste de entregavel em revisao passaria por este motivo, deixando
    # a outra solta. Sumir da tela tambem nao fecha a rota - sem isto o POST segue
    # valendo, e num formulario sem campos ele criaria Anexo em branco.
    permissions.garante(
        oferece_anexo(obj.tipo), "Este entregável não recebe material anexado."
    )
    form = AnexoForm(request.POST, request.FILES, tipo=obj.tipo)
    if not form.is_valid():
        for lista in form.errors.values():
            for mensagem in lista:
                messages.error(request, mensagem)
        return redirect("entregavel", pk=obj.pk)

    upload = form.cleaned_data.get("upload")
    anexo = form.save(commit=False)
    anexo.entregavel = obj
    anexo.enviado_por = request.user
    if upload:
        arquivo = Arquivo(
            nome_original=upload.name,
            tamanho=upload.size,
            mime=form.cleaned_data["mime"],
            hash_conteudo=calcula_hash(upload),
            enviado_por=request.user,
        )
        arquivo.arquivo.save(upload.name, upload, save=False)
        arquivo.save()
        anexo.arquivo = arquivo
        anexo.tipo_midia = TipoMidia.ARQUIVO
    else:
        anexo.tipo_midia = TipoMidia.LINK
    try:
        anexo.save()
    except ValidationError as erro:
        # AnexoForm nao rejeita a combinacao arquivo+link (so rejeita nem-um-nem-
        # outro; ver AnexoForm.clean()) - de proposito, para nao duplicar a regra
        # que mora em Anexo.clean() (docs/onde-mora-a-validacao.md). Este
        # try/except e o backstop: qualquer coisa que Anexo.clean() rejeitar na
        # instancia ja montada vira mensagem em vez de erro nao tratado.
        if upload:
            # O Arquivo (linha + arquivo em disco) ja foi criado acima, antes deste
            # save() rejeitar o Anexo que apontaria pra ele. Sem isto, cada tentativa
            # com arquivo E link deixa um Arquivo orfao pra tras - e limpar_arquivos_orfaos
            # so existe no Plano 4. So acontece no caminho de upload (o de link nunca
            # cria Arquivo), e nesse ponto nenhum Anexo foi salvo apontando pra ele,
            # entao nao ha nada mais referenciando este registro.
            arquivo.arquivo.delete(save=False)
            arquivo.delete()
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect("entregavel", pk=obj.pk)
    messages.success(request, "Material anexado.")
    return redirect("entregavel", pk=obj.pk)


@login_required
@require_POST
def enviar_entregavel(request, pk):
    obj = get_object_or_404(Entregavel, pk=pk)
    # `e_membro_da_equipe`, e nao `pode_editar_producao`: o servico usa aquele de
    # proposito, porque o segundo ja embute o estado editavel e um reenvio
    # legitimo viraria 403 em vez da mensagem que a regra de negocio quer.
    permissions.garante(
        permissions.e_membro_da_equipe(request.user, obj.curso),
        "Curso de outra equipe.",
    )
    try:
        services.enviar_para_revisao(obj, por=request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, "Entregável enviado para revisão do professor.")
    return redirect("entregavel", pk=obj.pk)
