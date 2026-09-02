"""O painel: a primeira tela de quem entra.

Mora num app proprio, e nao em `contas`, por causa da dependencia de mao unica do
projeto. O painel conta cursos, solicitacoes e turmas; morando no app base, ele
fazia `contas` importar `cursos`, `catalogo` e `turmas`, e os tres importam
`contas` de volta - tres ciclos. Aqui em cima, ele pode olhar todos sem que
nenhum precise olhar para ele.
"""

import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.catalogo.models import Solicitacao
from apps.cursos.choices import STATUS_EM_DESENVOLVIMENTO, StatusCurso, StatusEntregavel
from apps.cursos.models import Curso, Entregavel
from apps.turmas.models import Turma


def _resumo(usuario):
    """Os números que cada papel precisa ver ao entrar.

    Só contagens: o painel é uma porta, não um relatório. Cada número leva a uma
    tela que já existe e já sabe filtrar - repetir a lista aqui seria manter duas
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
        # Por vinculo de equipe, e nao por `professor_responsavel`: e o mesmo
        # recorte de `meus_cursos`, que e a tela para onde os dois cartoes levam.
        # Contado de um jeito e listado de outro, o numero do cartao nunca batia
        # com o que a pessoa via depois de clicar.
        meus = Curso.objects.filter(membros__pessoa=usuario)
        return [
            {
                "rotulo": "Cursos publicados",
                "valor": meus.filter(status=StatusCurso.PUBLICADO).distinct().count(),
                "url": "meus_cursos",
                # O recorte viaja com o cartao: `meus_cursos` filtra pelo mesmo
                # criterio, entao o numero e a lista nao tem como divergir.
                "estado": "publicados",
            },
            {
                "rotulo": "Cursos em desenvolvimento",
                "valor": meus.filter(
                    status__in=STATUS_EM_DESENVOLVIMENTO
                ).distinct().count(),
                "url": "meus_cursos",
                "estado": "desenvolvimento",
            },
            {
                # Conta ENTREGAVEIS, e nao cursos com entregavel em revisao: e o
                # mesmo recorte da `fila_revisao`, que lista um item por
                # entregavel. Dois entregaveis do mesmo curso sao dois na fila, e
                # o `.distinct()` por curso que havia aqui dizia um.
                "rotulo": "Entregáveis para revisar",
                # O mesmo recorte que a tela lista, e nao uma segunda contagem:
                # os que esperam decisao MAIS os que voltaram para a equipe.
                "valor": sum(len(g) for g in Entregavel.objects.na_revisao_de(usuario)),
                "url": "fila_revisao",
            },
        ]

    return [
        {
            "rotulo": "Cursos em que você produz",
            "valor": Curso.objects.filter(membros__pessoa=usuario).distinct().count(),
            "url": "meus_cursos",
        },
    ]


@login_required
def painel(request):
    return render(request, "painel.html", {"resumo": _resumo(request.user)})
