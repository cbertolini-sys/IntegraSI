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
def test_o_coordenador_continua_vendo(client, coordenador):
    """Pessoas, Revisao e Meus cursos so tem porta por ali. Tirar a secao dele
    nao seria enxugar repeticao, seria deixar tres telas sem caminho."""
    from django.urls import reverse

    client.force_login(coordenador)
    html = client.get(reverse("painel")).content.decode()
    assert "Onde trabalhar" in html
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

    client.force_login(professor)
    html = client.get(reverse("painel")).content.decode()
    cabecalho = html[: html.index("</header>")]
    assert reverse("catalogo") in cabecalho


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
