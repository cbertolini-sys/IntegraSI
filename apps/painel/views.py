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

from apps.catalogo.models import Solicitacao, SugestaoDeCurso
from apps.cursos.choices import STATUS_EM_DESENVOLVIMENTO, StatusCurso
from apps.cursos.models import Curso, Entregavel


def _resumo(usuario):
    """Os números que a pessoa precisa ver ao entrar.

    Um recorte só para professor e coordenador, e não dois: no modelo o
    coordenador JA e um professor (`Usuario.e_professor` vale para ele), e o
    painel trocava um conjunto de cartoes pelo outro como se fossem papeis
    excludentes - o coordenador perdia de vista os proprios cursos e a propria
    fila de revisao. O que ele tem A MAIS vive em `_coordenacao`.

    Só contagens: o painel é uma porta, não um relatório. Cada número leva a uma
    tela que já existe e já sabe filtrar - repetir a lista aqui seria manter duas
    definições do mesmo recorte.
    """
    if not usuario.e_professor:
        return [
            {
                "rotulo": "Cursos em que você produz",
                "valor": Curso.objects.filter(membros__pessoa=usuario).distinct().count(),
                "url": "meus_cursos",
            },
        ]

    # Por vinculo de equipe, e nao por `professor_responsavel`: e o mesmo recorte
    # de `meus_cursos`, que e a tela para onde os dois cartoes levam. Contado de um
    # jeito e listado de outro, o numero do cartao nunca batia com o que a pessoa
    # via depois de clicar.
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
            "valor": meus.filter(status__in=STATUS_EM_DESENVOLVIMENTO).distinct().count(),
            "url": "meus_cursos",
            "estado": "desenvolvimento",
        },
        {
            # Conta ENTREGAVEIS, e nao cursos com entregavel em revisao: e o
            # mesmo recorte da `fila_revisao`, que lista um item por entregavel.
            "rotulo": "Entregáveis para revisar",
            "valor": sum(len(g) for g in Entregavel.objects.na_revisao_de(usuario)),
            "url": "fila_revisao",
        },
    ]


def _coordenacao(usuario):
    """O que so o coordenador faz, numa secao propria abaixo do painel comum.

    Lista vazia para quem nao coordena: a decisao fica aqui, e nao num `{% if %}`
    de papel no template (spec 10).
    """
    if not usuario.e_coordenador:
        return []
    return [
        {
            "rotulo": "Aguardando aprovação",
            "valor": Curso.objects.filter(status=StatusCurso.AGUARDANDO_COORDENADOR).count(),
            "url": "fila_coordenacao",
        },
        {
            # "do catálogo" e "novo", nos dois cartoes: sem os qualificadores
            # sobram "solicitações" e "sugestões", que em portugues sao quase
            # sinonimos, lado a lado, com um numero cada e mais nada. A primeira
            # versao desta tela confundiu quem projetou o sistema.
            "rotulo": "Solicitações de curso do catálogo",
            "valor": Solicitacao.objects.filter(
                status__in=[Solicitacao.RECEBIDA, Solicitacao.EM_ANALISE]
            ).count(),
            "url": "solicitacoes",
        },
        {
            # Ao lado das solicitacoes, e nao no lugar delas: sao decisoes
            # diferentes (agendar um curso pronto contra decidir produzir um
            # curso novo), e quem coordena precisa ver as duas filas separadas.
            #
            # Conta TODAS, e nao so as pendentes como o cartao ao lado: a porta
            # que ele abre e a lista inteira do que a comunidade pediu, e um
            # numero que zera quando a ultima e respondida esconderia justamente
            # o historico que da valor a essa tela. Segue o padrao de "Cursos no
            # catálogo", que tambem e inventario e nao fila.
            "rotulo": "Sugestões de curso novo",
            "valor": SugestaoDeCurso.objects.count(),
            "url": "sugestoes",
        },
        {
            "rotulo": "Cursos no catálogo",
            "valor": Curso.objects.filter(status=StatusCurso.PUBLICADO).count(),
            "url": "cursos_no_catalogo",
        },
    ]


@login_required
def painel(request):
    return render(
        request,
        "painel.html",
        {"resumo": _resumo(request.user), "coordenacao": _coordenacao(request.user)},
    )
