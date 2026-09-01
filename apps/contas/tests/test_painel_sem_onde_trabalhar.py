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
