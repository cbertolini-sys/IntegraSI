"""A página Sobre: o que o sistema é e como cada pessoa o percorre.

Pública como o catálogo - quem vai solicitar um curso precisa entender o que
está pedindo antes de ter conta, e provavelmente nunca terá uma.
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_a_pagina_e_publica(client):
    assert client.get(reverse("sobre")).status_code == 200


@pytest.mark.django_db
def test_traz_os_quatro_fluxogramas(client):
    """Comunidade, coordenação, professor e estudante -- os quatro papéis que o
    sistema conhece."""
    conteudo = client.get(reverse("sobre")).content.decode()
    # Cada fluxo leva o modificador do papel, que e o que da a cor: `fluxograma
    # comunidade`, `fluxograma coordenacao`, e assim por diante.
    for papel in ("comunidade", "coordenacao", "professor", "estudante"):
        assert f'class="fluxograma {papel}"' in conteudo


@pytest.mark.django_db
def test_o_link_esta_na_barra(client):
    conteudo = client.get(reverse("catalogo")).content.decode()
    assert reverse("sobre") in conteudo


@pytest.mark.django_db
def test_metodo_errado_e_rejeitado(client):
    assert client.delete(reverse("sobre")).status_code == 405
