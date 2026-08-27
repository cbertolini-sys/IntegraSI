import datetime

from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.catalogo.forms import SolicitacaoForm
from apps.catalogo.models import Solicitacao
from apps.cursos.busca import buscar
from apps.cursos.choices import Formato, StatusCurso, TipoPublico
from apps.cursos.models import Curso, Tema
from apps.notificacoes.services import enfileirar
from apps.referenciais.choices import ETAPAS
from apps.referenciais.models import Referencial

LIMITE_POR_IP_POR_HORA = 5


def cursos_publicados():
    """Visitante enxerga exclusivamente cursos PUBLICADO (spec 10)."""
    return Curso.objects.filter(status=StatusCurso.PUBLICADO).select_related("referencial")


def catalogo(request):
    cursos = cursos_publicados()

    etapa = request.GET.get("etapa", "")
    if etapa:
        cursos = cursos.filter(tipo_publico=TipoPublico.ESCOLAR, etapa_ano=etapa)
    if request.GET.get("comunitario"):
        cursos = cursos.filter(tipo_publico=TipoPublico.COMUNITARIO)

    tema = request.GET.get("tema", "")
    if tema:
        cursos = cursos.filter(temas__slug=tema)

    referencial = request.GET.get("referencial", "")
    if referencial:
        cursos = cursos.filter(referencial__sigla=referencial)

    formato = request.GET.get("formato", "")
    if formato:
        cursos = cursos.filter(formato=formato)

    cursos = buscar(cursos, request.GET.get("q", "")).distinct()

    return render(
        request,
        "catalogo/lista.html",
        {
            "cursos": cursos,
            "etapas": ETAPAS,
            "temas": Tema.objects.filter(ativo=True),
            "referenciais": Referencial.objects.filter(ativo=True),
            "formatos": Formato.choices,
            "filtros": request.GET,
        },
    )


def catalogo_curso(request, pk):
    curso = get_object_or_404(cursos_publicados().prefetch_related("temas", "competencias"), pk=pk)
    return render(request, "catalogo/curso.html", {"curso": curso})


def _ip_da_requisicao(request):
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _emails_dos_coordenadores():
    from apps.contas.models import Usuario

    return list(
        Usuario.objects.filter(papel=Usuario.COORDENADOR, is_active=True).values_list("email", flat=True)
    )


@require_http_methods(["GET", "POST"])
def solicitar(request, pk):
    # Só curso PUBLICADO pode ser solicitado, e é cursos_publicados() - a mesma
    # porta que catalogo() e catalogo_curso() usam - quem garante isso; não uma
    # segunda checagem de status escrita aqui (spec 10).
    curso = get_object_or_404(cursos_publicados(), pk=pk)

    if request.method != "POST":
        form = SolicitacaoForm()
        return render(request, "catalogo/solicitar.html", {"curso": curso, "form": form})

    form = SolicitacaoForm(request.POST)

    if form.e_robo():
        # Descarte silencioso: responder com erro só ensina o robô a acertar da
        # próxima vez (spec 10). A pessoa real nunca vê essa diferença.
        return render(request, "catalogo/solicitacao_recebida.html", {"curso": curso})

    ip = _ip_da_requisicao(request)
    uma_hora_atras = timezone.now() - datetime.timedelta(hours=1)
    if Solicitacao.objects.filter(ip_origem=ip, criado_em__gte=uma_hora_atras).count() >= LIMITE_POR_IP_POR_HORA:
        return render(
            request,
            "catalogo/solicitar.html",
            {
                "curso": curso,
                "form": form,
                "erro": "Muitas solicitações deste endereço. Tente novamente mais tarde.",
            },
        )

    if not form.is_valid():
        return render(request, "catalogo/solicitar.html", {"curso": curso, "form": form})

    solicitacao = form.save(commit=False)
    solicitacao.curso = curso
    solicitacao.ip_origem = ip
    solicitacao.save()

    enfileirar(
        evento="SOLICITACAO_RECEBIDA",
        destinatarios=[curso.professor_responsavel.email] + _emails_dos_coordenadores(),
        assunto=f"Nova solicitação: {curso.titulo}",
        corpo=(
            f"{solicitacao.nome} ({solicitacao.instituicao}) solicitou o curso {curso.titulo} "
            f"para {solicitacao.num_participantes} participantes.\n\n{solicitacao.mensagem}"
        ),
    )
    return render(request, "catalogo/solicitacao_recebida.html", {"curso": curso})
