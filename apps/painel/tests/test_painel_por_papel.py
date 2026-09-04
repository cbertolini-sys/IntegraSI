"""O painel do coordenador e o do professor, mais a coordenacao.

No modelo o coordenador JA e um professor: `Usuario.e_professor` vale para ele
(CLAUDE.md, Papeis). O painel nao refletia isso - trocava um conjunto de cartoes
pelo outro, como se fossem papeis excludentes, e o coordenador perdia de vista os
proprios cursos e a propria fila de revisao.

Agora ele ve o painel do professor e, ABAIXO, uma secao "Coordenação" com o que
so ele faz.
"""

import pytest
from django.urls import reverse

from apps.painel.views import _coordenacao, _resumo


def cartoes(html, depois_de=None):
    """Os rotulos dos cartoes, opcionalmente so os que vem depois de um titulo."""
    import re

    if depois_de:
        html = html[html.index(depois_de) :]
    lista = html[html.index('class="indicadores"') : html.index("</ul>", html.index('class="indicadores"'))]
    return re.findall(r'<a href="[^"]*">([^<]+)</a>', lista)


DO_PROFESSOR = ["Cursos publicados", "Cursos em desenvolvimento", "Entregáveis para revisar"]
DA_COORDENACAO = [
    "Aguardando aprovação",
    "Solicitações a responder",
    "Sugestões a responder",
    "Cursos no catálogo",
]


@pytest.mark.django_db
def test_o_coordenador_ve_os_cartoes_do_professor(client, coordenador):
    client.force_login(coordenador)
    html = client.get(reverse("painel")).content.decode()
    assert cartoes(html) == DO_PROFESSOR


@pytest.mark.django_db
def test_e_abaixo_a_secao_de_coordenacao(client, coordenador):
    client.force_login(coordenador)
    html = client.get(reverse("painel")).content.decode()
    assert "Coordenação" in html
    assert cartoes(html, depois_de="Coordenação") == DA_COORDENACAO
    # A secao vem DEPOIS: sao as funcoes a mais, e nao as principais.
    assert html.index("Cursos publicados") < html.index("Coordenação")


@pytest.mark.django_db
def test_a_secao_traz_o_atalho_que_nao_tem_cartao(client, coordenador):
    """Pessoas nao e contagem de trabalho pendente, entao nao vira cartao - mas
    precisa de porta, e esta e a unica."""
    client.force_login(coordenador)
    html = client.get(reverse("painel")).content.decode()
    assert reverse("pessoas") in html


@pytest.mark.django_db
def test_o_professor_nao_ve_a_secao(client, professor):
    client.force_login(professor)
    html = client.get(reverse("painel")).content.decode()
    assert cartoes(html) == DO_PROFESSOR
    assert "Coordenação" not in html
    assert reverse("pessoas") not in html


@pytest.mark.django_db
def test_o_aluno_ve_so_o_dele(client, aluno):
    client.force_login(aluno)
    html = client.get(reverse("painel")).content.decode()
    assert cartoes(html) == ["Cursos em que você produz"]
    assert "Coordenação" not in html


@pytest.mark.django_db
def test_a_coordenacao_e_vazia_para_quem_nao_coordena(professor, aluno):
    """A decisao fica no Python, e nao num `{% if %}` de papel no template."""
    assert _coordenacao(professor) == []
    assert _coordenacao(aluno) == []


@pytest.mark.django_db
def test_o_resumo_do_coordenador_e_o_mesmo_do_professor(coordenador, professor):
    """Literalmente o mesmo recorte: se um dia divergirem, foi por decisao."""
    assert [i["rotulo"] for i in _resumo(coordenador)] == [
        i["rotulo"] for i in _resumo(professor)
    ]
