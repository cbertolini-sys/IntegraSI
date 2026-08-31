"""A página Sobre: o que o sistema é e como cada pessoa o percorre.

Pública como o catálogo — quem vai solicitar um curso precisa entender o que
está pedindo antes de ter conta, e provavelmente nunca terá uma.
"""

import pathlib

import pytest
from django.conf import settings
from django.urls import reverse

FLUXOS = pathlib.Path(settings.BASE_DIR) / "static" / "img" / "fluxos"


@pytest.mark.django_db
def test_a_pagina_e_publica(client):
    assert client.get(reverse("sobre")).status_code == 200


@pytest.mark.django_db
def test_traz_os_quatro_fluxogramas(client):
    """Comunidade, coordenação, professor e estudante -- os quatro papéis que o
    sistema conhece."""
    conteudo = client.get(reverse("sobre")).content.decode()
    for arquivo in ("01-comunidade", "02-coordenacao", "03-professor", "04-estudante"):
        assert f"fluxos/{arquivo}.svg" in conteudo


@pytest.mark.django_db
def test_o_link_esta_na_barra(client):
    conteudo = client.get(reverse("catalogo")).content.decode()
    assert reverse("sobre") in conteudo


@pytest.mark.django_db
def test_metodo_errado_e_rejeitado(client):
    assert client.delete(reverse("sobre")).status_code == 405


def test_os_svg_existem_e_sao_xml_valido():
    """Gerados por `deploy/gerar-fluxogramas.sh` a partir de `docs/fluxos/*.mmd`.

    A validade importa: `<img src="*.svg">` e lido em XML estrito, e um SVG
    malformado vira imagem quebrada SEM erro no console. Ja aconteceu duas vezes
    ao montar esta pagina -- `role` duplicado e `<br>` sem fechar dentro de
    foreignObject.
    """
    import xml.etree.ElementTree as ET

    encontrados = sorted(FLUXOS.glob("*.svg"))
    assert len(encontrados) == 4, f"esperava 4 fluxogramas, achei {len(encontrados)}"
    for arquivo in encontrados:
        ET.fromstring(arquivo.read_text())


def test_cada_svg_tem_uma_fonte_mermaid():
    """O `.mmd` e a fonte da verdade; o `.svg` e o que se serve. Um SVG sem fonte
    nao pode ser regenerado por ninguem."""
    fontes = {p.stem for p in (pathlib.Path(settings.BASE_DIR) / "docs" / "fluxos").glob("*.mmd")}
    desenhos = {p.stem for p in FLUXOS.glob("*.svg")}
    assert desenhos == fontes, f"sem par: {desenhos ^ fontes}"
