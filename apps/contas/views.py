from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.catalogo.models import Solicitacao
from apps.cursos.choices import StatusCurso, StatusEntregavel
from apps.cursos.models import Curso
from apps.turmas.models import Turma


def _resumo(usuario):
    """Os números que cada papel precisa ver ao entrar.

    Só contagens: o painel é uma porta, não um relatório. Cada número leva a uma
    tela que já existe e já sabe filtrar — repetir a lista aqui seria manter duas
    definições do mesmo recorte.
    """
    if usuario.e_coordenador:
        return [
            {
                "rotulo": "Aguardando aprovação",
                "valor": Curso.objects.filter(status=StatusCurso.AGUARDANDO_COORDENADOR).count(),
                "url": "fila_coordenacao",
            },
            {
                "rotulo": "Solicitações a responder",
                "valor": Solicitacao.objects.filter(
                    status__in=[Solicitacao.RECEBIDA, Solicitacao.EM_ANALISE]
                ).count(),
                "url": "solicitacoes",
            },
            {
                "rotulo": "Cursos no catálogo",
                "valor": Curso.objects.filter(status=StatusCurso.PUBLICADO).count(),
                "url": "cursos_no_catalogo",
            },
            {
                "rotulo": "Turmas agendadas",
                "valor": Turma.objects.filter(status=Turma.AGENDADA).count(),
                "url": "minhas_turmas",
            },
        ]

    if usuario.e_professor:
        meus = Curso.objects.filter(professor_responsavel=usuario)
        return [
            {
                "rotulo": "Cursos sob sua responsabilidade",
                "valor": meus.count(),
                "url": "meus_cursos",
            },
            {
                "rotulo": "Entregáveis para revisar",
                "valor": meus.filter(
                    entregaveis__status=StatusEntregavel.EM_REVISAO
                ).distinct().count(),
                "url": "fila_revisao",
            },
            {
                "rotulo": "Turmas sob sua condução",
                "valor": Turma.objects.filter(professor=usuario).count(),
                "url": "minhas_turmas",
            },
        ]

    return [
        {
            "rotulo": "Cursos em que você produz",
            "valor": Curso.objects.filter(membros__aluno=usuario).distinct().count(),
            "url": "meus_cursos",
        },
    ]


@login_required
def painel(request):
    return render(request, "painel.html", {"resumo": _resumo(request.user)})
