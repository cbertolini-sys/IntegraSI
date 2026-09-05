"""Nenhuma tela pula um nivel de titulo.

Quem navega por titulos (um modo de leitura comum em leitor de tela) usa a
sequencia h1, h2, h3 como sumario da pagina: um salto de h1 para h3 anuncia uma
secao intermediaria que a tela nao tem, e a pessoa procura o que nao existe.
WCAG 2.1, criterio 1.3.1.

Sobre a PAGINA RENDERIZADA, e nao sobre o texto do template, porque a varredura
estatica erra nos dois sentidos neste projeto: `entregavel.html` nao tem `<h1>`
nenhum e recebe o dele de um `{% include %}`, e `meus_cursos.html` tem tres, que
sao ramos exclusivos do mesmo `{% if %}`. Os dois seriam acusados por engano.

Mora em `painel` porque e o app que pode conhecer todos os outros, e as seis
telas do achado vem de quatro apps diferentes.
"""

import datetime
import re

import pytest
from django.urls import reverse

from apps.catalogo.models import Solicitacao
from apps.turmas import services as servicos_turma

# As fixtures de curso moram em `cursos`, e as de turma em `turmas`, que ja as
# reimporta de la. `professor` e `coordenador` chegam pelo conftest ao lado, que
# os traz de `contas` - o mesmo arranjo que catalogo e turmas usam entre si.
from apps.cursos.tests.conftest import (  # noqa: F401
    dados_curso,
    media_root_isolado,
    outro_aluno,
)
from apps.turmas.tests.conftest import (  # noqa: F401
    curso_publicado,
    solicitacao,
)

_TITULO = re.compile(r"<h([1-6])\b", re.I)


def saltos(html):
    """Os pontos onde a sequencia de titulos pula um nivel.

    Descer varios niveis de uma vez e normal e nao entra aqui: depois de um h3,
    voltar para h2 fecha uma secao e abre outra. O que confunde e SUBIR pulando,
    porque anuncia um nivel que a pagina nunca declarou.
    """
    niveis = [int(n) for n in _TITULO.findall(html)]
    return [
        f"h{anterior} seguido de h{seguinte}"
        for anterior, seguinte in zip(niveis, niveis[1:])
        if seguinte > anterior + 1
    ]


@pytest.fixture
def telas(client, curso_publicado, solicitacao, professor, coordenador):
    """As telas do achado, cada uma com quem consegue abri-la.

    O curso precisa estar publicado, com solicitacao recebida E com turma
    aberta: tela vazia nao tem cartao nenhum, e o salto de nivel mora justamente
    entre o titulo da pagina e o titulo do cartao. Sem a turma, `minhas_turmas`
    rendia so o `<h1>` e nao provava nada - o que o terceiro teste deste arquivo
    pega.

    Duas solicitacoes, e nao uma: aceitar a unica a move para "Ja respondidas",
    que tem `<h2>` proprio, e a lista de pendentes (a que nao tem) esvazia. Com
    uma so, a tela de solicitacoes saia da lista de acusadas sem ter sido
    corrigida.
    """
    Solicitacao.objects.create(
        curso=curso_publicado, nome="Escola Nova", email="direcao@nova.exemplo.br",
        num_participantes=18, instituicao="EMEF Nova",
    )
    servicos_turma.aceitar_solicitacao(
        solicitacao,
        professor=professor,
        dados_turma={
            "data_inicio": datetime.date(2027, 3, 1),
            "data_fim": datetime.date(2027, 3, 30),
            "local": "EMEF São José",
            "vagas": 25,
        },
        por=coordenador,
    )

    def como(pessoa, url):
        client.force_login(pessoa)
        resposta = client.get(url)
        assert resposta.status_code == 200, f"{url} devolveu {resposta.status_code}"
        return resposta.content.decode()

    publico = client.get(reverse("catalogo"))
    assert publico.status_code == 200

    return {
        "catálogo (público)": publico.content.decode(),
        "meus cursos": como(professor, reverse("meus_cursos")),
        "fila de revisão": como(professor, reverse("fila_revisao")),
        "ficha do curso": como(professor, reverse("curso", args=[curso_publicado.pk])),
        # Nao estava no achado original, e entrou junto: os titulos de secao dela
        # eram `h3` e passaram a `h2` na mesma uniformizacao. Sem cobri-la aqui,
        # a unica coisa prendendo o nivel seria o teste da ficha, que olha outra
        # tela.
        "entregável": como(
            professor, reverse("entregavel", args=[curso_publicado.entregaveis.first().pk])
        ),
        "solicitações": como(coordenador, reverse("solicitacoes")),
        "turmas": como(coordenador, reverse("minhas_turmas")),
    }


def test_nenhuma_tela_pula_um_nivel_de_titulo(telas):
    achados = [
        f"{nome}: {', '.join(pulos)}"
        for nome, html in telas.items()
        if (pulos := saltos(html))
    ]
    assert achados == [], "salto de nível de título em:\n" + "\n".join(achados)


def test_toda_tela_comeca_por_um_h1(telas):
    """Guarda separada da de cima de proposito. Uma pagina cujo primeiro titulo
    fosse h2 nao teria salto NENHUM pela regra acima, e ainda assim comecaria
    sem raiz: o leitor de tela nao teria por onde entrar no sumario."""
    sem_raiz = [
        f"{nome}: começa em h{_TITULO.findall(html)[0]}"
        for nome, html in telas.items()
        if _TITULO.findall(html) and _TITULO.findall(html)[0] != "1"
    ]
    assert sem_raiz == [], "tela que não começa por h1:\n" + "\n".join(sem_raiz)


def test_a_varredura_enxerga_os_titulos_das_seis_telas(telas):
    """Um seletor errado devolveria zero titulos e os dois testes acima ficariam
    verdes para sempre, com o sistema inteiro livre para pular niveis."""
    for nome, html in telas.items():
        assert len(_TITULO.findall(html)) >= 2, f"{nome} rendeu títulos de menos"
