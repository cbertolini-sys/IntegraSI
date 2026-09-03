"""Endpoints do upload em blocos (spec 8).

Quatro rotas: abrir o upload, mandar um bloco, perguntar onde parou e concluir. O
que justifica todas elas e a retomada: 1 GB no upstream domestico de um aluno leva
perto de meia hora, e um POST unico que morre aos 90% e entrega perdida.

Nenhuma delas devolve HTML - quem as chama e o `static/js/upload.js` da Task 3.
"""

import json
from functools import wraps

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.cursos import permissions, services
from apps.cursos.arquivos import valida_declaracao
from apps.cursos.choices import TipoEntregavel
from apps.cursos.models import Entregavel, UploadEmAndamento

# UUID de enfeite para o template reverter, com `{% url %}`, as tres rotas que
# dependem do identificador; o JS troca esta marca pelo identificador de verdade
# assim que o tem. E o que mantem `urls.py` como unica fonte das URLs: sem isto o
# JS montaria "/uploads/<id>/bloco/" na mao e uma mudanca de rota quebraria o
# navegador com a suite inteira verde.
UUID_MODELO = "00000000-0000-0000-0000-000000000000"


def _corpo_json(request):
    """Corpo da requisicao como dicionario.

    Cliente que manda lixo tem que ouvir 400. Um `json.loads` cru levantaria
    JSONDecodeError e viraria 500 - erro do servidor por culpa do cliente, ruido
    no log de producao e nenhuma explicacao para quem chamou.
    """
    try:
        dados = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValidationError("Corpo da requisição não é JSON válido.")
    if not isinstance(dados, dict):
        raise ValidationError("Corpo da requisição precisa ser um objeto JSON.")
    return dados


def _campo(dados, chave):
    """Campo obrigatorio. `dados[chave]` cru viraria KeyError, ou seja, 500."""
    if chave not in dados:
        raise ValidationError(f"Informe o campo {chave}.")
    return dados[chave]


def _texto(dados, chave):
    valor = _campo(dados, chave)
    if not isinstance(valor, str):
        raise ValidationError(f"O campo {chave} precisa ser texto.")
    return valor


def _texto_opcional(dados, chave):
    """Campo que pode nao vir: ausente vale "", presente precisa ser texto.

    Ausente nao pode virar 400. A aba que o aluno deixou aberta antes do deploy
    manda o corpo antigo, e ali dentro pode haver meia hora de upload ja no disco.
    """
    if chave not in dados:
        return ""
    valor = dados[chave]
    if not isinstance(valor, str):
        raise ValidationError(f"O campo {chave} precisa ser texto.")
    return valor


def _inteiro(dados, chave):
    """`int(...)` cru sobre texto do cliente viraria ValueError, ou seja, 500."""
    try:
        return int(_campo(dados, chave))
    except (TypeError, ValueError):
        raise ValidationError(f"O campo {chave} precisa ser um número.")


def _recusa(erro):
    return JsonResponse({"erro": erro.messages[0]}, status=400)


def _json_ou_401_e_403(view):
    """Substitui `@login_required` nestas quatro rotas: nunca deixa a sessao
    expirada ou uma permissao recusada escapar do contrato JSON.

    `@login_required` redireciona (302) para o login. static/js/upload.js so fala
    com estas rotas por `fetch`, que SEGUE o redirecionamento: a resposta final
    chega como 200 com o HTML da tela de login, `resposta.ok` fica verdadeiro e o
    `.json()` do cliente estoura com erro de sintaxe - depois de, possivelmente,
    meia hora de upload de video, quando a sessao expira no meio do envio.

    `PermissionDenied` tem o mesmo problema do outro lado: `upload_iniciar` chama
    `permissions.garante` fora do try/except (regra 2/3), e `upload_concluir`
    chama um servico que faz o mesmo dentro do try (regra 15) - mas o except so
    cobre `ValidationError`. Nos dois casos a excecao atravessa a view e cai no
    handler padrao do Django, que renderiza `403.html` (HTML, nao JSON).

    A verificacao de autenticacao roda ANTES de tudo, na mesma posicao que
    `@login_required` ja ocupava: e o que impede `_meu_upload` de filtrar por
    `usuario=AnonymousUser` (erro de banco) e as rotas de POST responderem 405 em
    vez de dizer que e preciso entrar de novo.
    """

    @wraps(view)
    def interno(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"erro": "Sua sessão expirou. Entre de novo e reenvie."}, status=401
            )
        try:
            return view(request, *args, **kwargs)
        except PermissionDenied as erro:
            return JsonResponse({"erro": str(erro)}, status=403)

    return interno


def _meu_upload(request, identificador):
    """Upload e sempre do proprio usuario: 404 para qualquer outro, e nao 403, para
    nao confirmar a existencia do identificador a quem nao e dono."""
    return get_object_or_404(
        UploadEmAndamento, identificador=identificador, usuario=request.user
    )


def _progresso(upload):
    return JsonResponse({"recebido": upload.tamanho_recebido, "total": upload.tamanho_total})


@_json_ou_401_e_403
@require_POST
def upload_iniciar(request):
    try:
        dados = _corpo_json(request)
        entregavel_pk = _inteiro(dados, "entregavel")
        nome = _texto(dados, "nome")
        tamanho = _inteiro(dados, "tamanho")
    except ValidationError as erro:
        return _recusa(erro)

    entregavel = get_object_or_404(Entregavel, pk=entregavel_pk)
    permissions.garante(
        permissions.pode_editar_producao(request.user, entregavel),
        "Este entregável não está aberto para edição.",
    )
    try:
        # Antes de criar o registro: o que da para saber sem ver um byte (extensao
        # conhecida, tamanho dentro do teto DAQUELE tipo, entregavel que comporta um
        # video) tem que ser dito agora, e nao depois de meia hora de upload. O
        # conteudo so na conclusao.
        #
        # `concluir_upload` reconfere o tipo do entregavel - a mesma dupla de guardas
        # que `pode_editar_producao` ja tem nas duas pontas, e pelo mesmo motivo: o
        # registro tambem nasce por outros caminhos que nao esta view.
        if entregavel.tipo != TipoEntregavel.VIDEOS:
            raise ValidationError("O upload em blocos é só do entregável de vídeo-aulas.")
        valida_declaracao(nome, tamanho)
        upload = UploadEmAndamento.objects.create(
            usuario=request.user,
            entregavel=entregavel,
            nome_original=nome,
            tamanho_total=tamanho,
        )
    except ValidationError as erro:
        return _recusa(erro)
    return JsonResponse({"identificador": str(upload.identificador), "recebido": 0})


@_json_ou_401_e_403
@require_POST
def upload_bloco(request, identificador):
    upload = _meu_upload(request, identificador)
    try:
        upload.acrescentar(request.body)
    except ValidationError as erro:
        return _recusa(erro)
    return _progresso(upload)


@_json_ou_401_e_403
@require_GET
def upload_estado(request, identificador):
    """Onde o upload parou. E o que permite ao navegador retomar do byte certo."""
    return _progresso(_meu_upload(request, identificador))


@_json_ou_401_e_403
@require_POST
def upload_concluir(request, identificador):
    upload = _meu_upload(request, identificador)
    try:
        dados = _corpo_json(request)
        titulo = _texto(dados, "titulo")
        duracao = _inteiro(dados, "duracao_minutos")
        descricao = _texto_opcional(dados, "descricao")
        anexo = services.concluir_upload(
            upload, titulo=titulo, duracao_minutos=duracao, descricao=descricao
        )
    except ValidationError as erro:
        return _recusa(erro)
    return JsonResponse({"anexo": anexo.pk, "titulo": anexo.titulo})
