"""A secao "Onde trabalhar" repetia, para professor e aluno, o que os cartoes ja
diziam. Para o coordenador nao: tres dos links dela nao existem em lugar nenhum."""

import pytest


@pytest.mark.django_db
def test_o_professor_nao_ve_mais_onde_trabalhar(client, professor):
    from django.urls import reverse

    client.force_login(professor)
    html = client.get(reverse("painel")).content.decode()
    assert "Onde trabalhar" not in html


@pytest.mark.django_db
def test_o_aluno_tambem_nao(client, aluno):
    from django.urls import reverse

    client.force_login(aluno)
    html = client.get(reverse("painel")).content.decode()
    assert "Onde trabalhar" not in html


@pytest.mark.django_db
def test_o_coordenador_ve_a_secao_de_coordenacao(client, coordenador):
    """"Onde trabalhar" deu lugar a "Coordenação".

    A secao antiga repetia, em atalho, destinos que os cartoes ja abriam: agora o
    coordenador ve os cartoes DO PROFESSOR em cima (que cobrem meus cursos e a
    fila de revisao) e, embaixo, os dele. So Pessoas continua como atalho, porque
    nao e contagem de trabalho pendente e nao vira cartao.
    """
    from django.urls import reverse

    client.force_login(coordenador)
    html = client.get(reverse("painel")).content.decode()
    assert "Onde trabalhar" not in html
    assert "Coordenação" in html
    for destino in (reverse("pessoas"), reverse("fila_revisao"), reverse("meus_cursos")):
        assert destino in html, destino


@pytest.mark.django_db
def test_o_painel_do_professor_so_oferece_nova_proposta(client, professor):
    """Um botao so no cabecalho. "Ver o catálogo" saiu porque a marca do topo leva
    la em toda pagina, e "Turmas" saiu a pedido."""
    from django.urls import reverse

    client.force_login(professor)
    html = client.get(reverse("painel")).content.decode()
    acoes = html[html.index('<div class="acoes">') : html.index("corpo-trabalho")]
    assert "Nova proposta" in acoes
    assert "Ver o catálogo" not in acoes
    assert "Turmas" not in acoes


@pytest.mark.django_db
def test_o_catalogo_continua_alcancavel_de_qualquer_pagina(client, professor):
    """O que torna a remocao do botao segura: a marca do topo e o rodape levam ao
    catalogo em toda pagina que estende `base.html`. Sem esta garantia, tirar o
    botao seria tirar o caminho."""
    from django.urls import reverse

    import re

    client.force_login(professor)
    html = client.get(reverse("painel")).content.decode()
    cabecalho = html[: html.index("</header>")]
    # A MARCA, e nao a presenca do endereco: `reverse("catalogo")` e `"/"`, e
    # `"/" in html` e verdade para qualquer pagina - a primeira versao deste teste
    # nao afirmava nada e passava com a marca apontando para outro lugar. Achado
    # na campanha de delecao.
    marca = re.search(r'<a class="marca" href="([^"]*)"', cabecalho)
    assert marca, "a marca sumiu do cabeçalho"
    assert marca.group(1) == reverse("catalogo")


@pytest.mark.django_db
def test_o_professor_nao_tem_mais_porta_para_turmas(client, professor):
    """Registra o que a remocao custou, em vez de deixar por descobrir.

    `minhas_turmas` continua existindo e o professor continua autorizado a abri-la
    (`e_professor or e_coordenador`), mas nenhum template linka para la no painel
    dele: so digitando o endereco. A pagina Sobre ainda diz que ele conduz as
    turmas - as duas coisas nao podem ficar assim, e a escolha e do produto.
    """
    import re
    import subprocess
    from pathlib import Path
    from django.urls import reverse

    client.force_login(professor)
    assert reverse("minhas_turmas") not in client.get(reverse("painel")).content.decode()
    # A tela em si continua de pe: o que sumiu foi o caminho, nao a permissao.
    assert client.get(reverse("minhas_turmas")).status_code == 200
