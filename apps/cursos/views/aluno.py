import hashlib

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.cursos import permissions, services, validacoes
from apps.cursos.choices import TipoMidia
from apps.cursos.forms import AnexoForm, SecaoForm
from apps.cursos.models import Anexo, Arquivo, Curso, Entregavel, Secao


@login_required
def meus_cursos(request):
    cursos = Curso.objects.filter(
        Q(membros__aluno=request.user) | Q(professor_responsavel=request.user)
    ).distinct()
    return render(request, "cursos/meus_cursos.html", {"cursos": cursos})


@login_required
def curso(request, pk):
    obj = get_object_or_404(Curso, pk=pk)
    permissions.garante(permissions.pode_ver_curso(request.user, obj), "Curso de outra equipe.")
    entregaveis = obj.entregaveis.all()
    return render(request, "cursos/curso.html", {"curso": obj, "entregaveis": entregaveis})


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
            "form_anexo": AnexoForm(),
            "pode_editar": permissions.pode_editar_producao(request.user, obj),
            "ultima_revisao": obj.revisoes.last(),
        },
    )


@login_required
def salvar_secao(request, pk):
    secao = get_object_or_404(Secao, pk=pk)
    permissions.garante(
        permissions.pode_editar_producao(request.user, secao.entregavel),
        "Este entregável não está aberto para edição.",
    )
    form = SecaoForm(request.POST, instance=secao)
    if not form.is_valid():
        return render(request, "cursos/_secao.html", {"secao": secao, "erro": "Não foi possível salvar."})
    secao = form.save(commit=False)
    secao.atualizado_por = request.user
    secao.save()
    return render(request, "cursos/_secao.html", {"secao": secao, "salvo": True})


@login_required
def anexar(request, pk):
    obj = get_object_or_404(Entregavel, pk=pk)
    permissions.garante(
        permissions.pode_editar_producao(request.user, obj), "Este entregável não está aberto para edição."
    )
    form = AnexoForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "; ".join(m for lista in form.errors.values() for m in lista))
        return redirect("entregavel", pk=obj.pk)

    upload = form.cleaned_data.get("upload")
    anexo = form.save(commit=False)
    anexo.entregavel = obj
    anexo.enviado_por = request.user
    if upload:
        conteudo = upload.read()
        upload.seek(0)
        arquivo = Arquivo(
            nome_original=upload.name,
            tamanho=upload.size,
            mime=form.cleaned_data["mime"],
            hash_conteudo=hashlib.sha256(conteudo).hexdigest(),
            enviado_por=request.user,
        )
        arquivo.arquivo.save(upload.name, upload, save=False)
        arquivo.save()
        anexo.arquivo = arquivo
        anexo.tipo_midia = TipoMidia.ARQUIVO
    else:
        anexo.tipo_midia = TipoMidia.LINK
    anexo.save()
    messages.success(request, "Material anexado.")
    return redirect("entregavel", pk=obj.pk)


@login_required
def enviar_entregavel(request, pk):
    obj = get_object_or_404(Entregavel, pk=pk)
    try:
        services.enviar_para_revisao(obj, por=request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, "Entregável enviado para revisão do professor.")
    return redirect("entregavel", pk=obj.pk)
