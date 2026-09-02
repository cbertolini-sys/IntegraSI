import datetime

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.catalogo.forms import SolicitacaoForm
from apps.contas.paginacao import paginar
from apps.contas.rede import ip_da_requisicao
from apps.catalogo.models import Solicitacao
from apps.cursos.busca import buscar
from apps.cursos.choices import Formato, StatusCurso, TipoPublico
from apps.cursos.models import Curso, Tema
from apps.notificacoes.services import enfileirar
from apps.referenciais.choices import ETAPAS
from apps.referenciais.models import Referencial

LIMITE_POR_IP_POR_HORA = 5

# Quantos cursos o carrossel do heroi mostra. O corte e do servidor, e nao do CSS:
# esconder o excedente com overflow mandaria a lista inteira pelo fio.
CURSOS_NA_VITRINE = 10


def cursos_publicados():
    """Visitante enxerga exclusivamente cursos PUBLICADO (spec 10).

    O prefetch dos anexos e para `Curso.praticas`, que a listagem chama uma vez por
    curso: sem ele, o indicador de "precisa de computador?" custaria duas consultas
    por cartao.
    """
    return (
        Curso.objects.filter(status=StatusCurso.PUBLICADO)
        .select_related("referencial")
        .prefetch_related("entregaveis__anexos")
    )


@require_http_methods(["GET"])
def sobre(request):
    """O que o sistema e e como cada papel o percorre.

    Publica como o catalogo: quem vai solicitar um curso precisa entender o que
    esta pedindo antes de ter conta -- e provavelmente nunca tera uma.

    Sem contexto: os fluxogramas sao SVG estatico, gerados de `docs/fluxos/*.mmd`
    por `deploy/gerar-fluxogramas.sh`. O texto vive no template porque e texto, e
    nao dado.
    """
    return render(request, "catalogo/sobre.html")


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

    pagina = paginar(request, cursos)
    return render(
        request,
        "catalogo/lista.html",
        {
            "cursos": pagina,
            "pagina": pagina,
            "etapas": ETAPAS,
            "temas": Tema.objects.filter(ativo=True),
            "referenciais": Referencial.objects.filter(ativo=True),
            "formatos": Formato.choices,
            "filtros": request.GET,
            # O total do catalogo inteiro, nao do resultado filtrado: no heroi ele
            # informa o tamanho da oferta, e mudaria de sentido se seguisse o filtro.
            "total_cursos": cursos_publicados().count(),
            # A vitrine do heroi ignora os filtros de proposito: ela mostra a
            # novidade do catalogo, e quem responde a busca e a grade abaixo. Sem
            # isso, um termo que nao casa com nada esvaziaria a primeira dobra da
            # pagina.
            #
            # Passa pelo mesmo `cursos_publicados()` das outras portas publicas, e
            # nao por uma consulta propria: e a unica definicao de "o que o
            # visitante enxerga" (spec 10), e duplica-la aqui e como um dia ela
            # divergiria.
            "vitrine": cursos_publicados()[:CURSOS_NA_VITRINE],
        },
    )


def catalogo_curso(request, pk):
    curso = get_object_or_404(
        # `membros__pessoa`: a autoria le o nome de cada membro, e sem isto e uma
        # consulta por pessoa. O painel interno do curso ja tinha aprendido isso.
        cursos_publicados().prefetch_related("temas", "competencias", "membros__pessoa"),
        pk=pk,
    )
    return render(request, "catalogo/curso.html", {"curso": curso})


@login_required
@require_http_methods(["GET"])
def previa_do_curso(request, pk):
    """A pagina publica de um curso que ainda nao esta no catalogo.

    A equipe precisa ver como o curso vai aparecer ANTES de publicar, que e quando
    ainda da para corrigir. Usa o MESMO template da pagina publica de proposito:
    uma previa desenhada a parte mostraria uma tela que nao existe.

    A permissao e a do curso, e nao a do catalogo: isto e material que ainda nao
    foi aprovado, e material nao aprovado nao circula (spec 10). Por isso tambem
    nao ha `cursos_publicados()` aqui - a previa existe justamente para o que nao
    esta publicado.
    """
    from apps.cursos import permissions

    curso = get_object_or_404(
        # `membros__pessoa` entrou com a autoria, que le o nome de cada membro:
        # sem ele e uma consulta por pessoa. `entregaveis__anexos` continua sendo
        # do `praticas`.
        Curso.objects.select_related("professor_responsavel").prefetch_related(
            "temas", "competencias", "entregaveis__anexos", "membros__pessoa",
        ),
        pk=pk,
    )
    permissions.garante(
        permissions.pode_ver_curso(request.user, curso), "Curso de outra equipe."
    )
    return render(request, "catalogo/curso.html", {"curso": curso, "previa": True})


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

    ip = ip_da_requisicao(request)
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
