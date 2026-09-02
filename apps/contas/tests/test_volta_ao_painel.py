"""Toda tela que o painel abre precisa saber voltar para ele.

O painel e a porta do sistema, e as telas que ele abre sao folhas: quem chega
numa delas so tem o botao do navegador para sair. Ficou visivel na fila de
revisao, que depois de aprovar o ultimo entregavel mostra "Nada aguardando
revisão." e nenhum caminho.

Uma tela so seria pior que nenhuma: `meus_cursos` ja tinha a volta e as outras
seis nao, o que e a inconsistencia que as ultimas rodadas foram tirar.
"""

import pytest
from django.urls import reverse


# Os destinos que `painel.html` oferece.
DESTINOS = [
    "meus_cursos",
    "fila_revisao",
    "fila_coordenacao",
    "solicitacoes",
    "pessoas",
    # `minhas_turmas` saiu: turmas viraram modulo de outra etapa, a desenvolver,
    # e o painel deixou de oferecer o caminho para os dois papeis.
    "nova_proposta",
]


@pytest.mark.django_db
@pytest.mark.parametrize("nome", DESTINOS)
def test_a_tela_do_painel_tem_volta(client, coordenador, nome):
    """Entra como coordenador porque e o unico papel que alcanca as sete."""
    client.force_login(coordenador)
    resposta = client.get(reverse(nome))
    assert resposta.status_code == 200, nome
    html = resposta.content.decode()
    assert f'href="{reverse("painel")}"' in html, nome
    assert "Voltar ao painel" in html, nome


def test_a_lista_de_destinos_acompanha_o_painel():
    """Um destino novo em `painel.html` e esquecido aqui nunca seria conferido.

    Le os `{% url %}` do proprio template: a lista acima deixa de ser lembranca e
    passa a ser cobrada.
    """
    import re
    from pathlib import Path

    from django.conf import settings

    painel = (Path(settings.BASE_DIR) / "templates" / "painel.html").read_text(
        encoding="utf-8"
    )
    oferecidos = set(re.findall(r"{% url '([a-z_]+)' %}", painel))
    # Sem `catalogo`: o botao "Ver o catálogo" saiu do painel, porque a marca do
    # topo leva la em toda pagina. Se ele voltar, este teste avisa.
    esperados = set(DESTINOS)
    assert oferecidos == esperados, (
        f"o painel mudou de destinos: só nele {oferecidos - esperados}, "
        f"só na lista {esperados - oferecidos}"
    )
