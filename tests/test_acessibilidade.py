"""O esqueleto que toda tela herda do `base.html`, do ponto de vista de quem nao
usa mouse.

O sistema ja acerta a base: um `<header>`, um `<nav>`, um `<main>` e um
`<footer>` por pagina, `alt` em toda imagem, nenhum botao falso, e todo
`outline: none` do CSS acompanhado de substituto visivel. O que faltava eram
duas coisas que so existem no `base.html` e portanto valem para o sistema
inteiro: uma forma de pular o cabecalho, e uma regiao de mensagens que anuncie
o que aparece nela.

Testes sobre a pagina renderizada, e nao sobre o texto do template: o
`{% if %}` que envolvia a lista de mensagens era invisivel a uma varredura de
regex, e e justamente ele o defeito.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

RAIZ = Path(settings.BASE_DIR)
CSS = (RAIZ / "static" / "css" / "integrasi.css").read_text(encoding="utf-8")


@pytest.fixture
def pagina(client, db):
    """O catalogo publico: a unica tela que qualquer pessoa alcanca sem login, e
    que herda o mesmo `base.html` de todas as outras."""
    return client.get(reverse("catalogo")).content.decode()


# --- Pular o cabecalho --------------------------------------------------------


def test_a_pagina_oferece_um_atalho_para_o_conteudo(pagina):
    """WCAG 2.4.1. O cabecalho e a navegacao vem antes do `<main>` em todas as
    telas, e sem atalho quem navega por teclado os atravessa inteiros a cada
    troca de pagina."""
    assert 'href="#conteudo"' in pagina, "nenhum link para pular ao conteúdo"


def test_o_atalho_e_a_primeira_coisa_da_pagina(pagina):
    """Atalho depois do cabecalho nao serve para nada: a pessoa so o encontraria
    depois de ja ter tabulado por tudo que ele existe para pular."""
    corpo = pagina[pagina.index("<body>") :]
    assert corpo.index('href="#conteudo"') < corpo.index("<header"), (
        "o atalho aparece depois do cabeçalho que ele deveria pular"
    )


def test_o_destino_do_atalho_existe(pagina):
    """Atalho apontando para âncora inexistente é pior que atalho nenhum: o foco
    fica onde estava, sem aviso nenhum de que o salto não aconteceu.

    Separado do teste de foco logo abaixo de propósito. Um teste só, cobrando as
    duas coisas, ficaria verde com qualquer uma das duas presente e não prenderia
    nenhuma das duas sozinha.
    """
    assert 'id="conteudo"' in pagina


def test_o_destino_do_atalho_e_focavel(pagina):
    """Safari e Chrome movem a rolagem ate a ancora mas NAO movem o foco quando o
    alvo nao e focavel: a pessoa ve o conteudo e continua tabulando dentro do
    menu que acabou de pular. `tabindex="-1"` no `<main>` resolve, e nao
    acrescenta parada de tabulacao nenhuma."""
    principal = pagina[pagina.index("<main") : pagina.index(">", pagina.index("<main")) + 1]
    assert 'tabindex="-1"' in principal, f"<main> não é focável: {principal}"


def test_o_atalho_fica_escondido_ate_receber_foco():
    """Se aparecesse sempre, seria um link estranho no topo de toda tela para
    quem usa mouse. A regra que o revela precisa ser a do foco: um `display:
    none` o esconderia tambem do teclado, que e justamente quem precisa dele."""
    assert ".pular-para-conteudo {" in CSS, "o atalho não tem estilo nenhum"

    # A chave faz parte do alvo de propósito: sem ela, `:focus-within` satisfaz a
    # busca por `:focus` e o teste fica verde com uma regra que nunca dispara
    # (o atalho não tem filho nenhum para receber foco). Encontrado quebrando
    # esta guarda: era exatamente a mutação que passava.
    assert ".pular-para-conteudo:focus {" in CSS, "o atalho não volta à tela ao receber foco"

    inicio = CSS.index(".pular-para-conteudo {")
    repouso = CSS[inicio : CSS.index("}", inicio)]
    assert "display: none" not in repouso and "visibility: hidden" not in repouso, (
        "escondido assim, o atalho sai também da ordem de tabulação, que é quem "
        "precisa dele"
    )

    inicio_foco = CSS.index(".pular-para-conteudo:focus {")
    ao_focar = CSS[inicio_foco : CSS.index("}", inicio_foco)]
    assert "left: 0" in ao_focar, (
        "a regra de foco existe mas não traz o atalho de volta à tela"
    )


# --- A regiao de mensagens ----------------------------------------------------


def test_as_mensagens_sao_anunciadas(pagina):
    """WCAG 4.1.3. `role="status"` e nao `role="alert"`: estas mensagens
    confirmam algo que a propria pessoa acabou de fazer ("Curso submetido a
    coordenacao"), e nao sao emergencia que justifique interromper a leitura em
    curso."""
    assert 'class="mensagens" role="status"' in pagina, (
        "a região de mensagens não é anunciada"
    )


def test_a_regiao_de_mensagens_existe_mesmo_vazia(pagina):
    """Este e o ponto do ajuste, e nao um detalhe.

    Uma regiao viva so anuncia o que ENTRA nela depois de ela existir: criada
    junto com o proprio conteudo, como acontecia com o `{% if messages %}` em
    volta da lista, nao dispara anuncio nenhum. O catalogo publico nunca tem
    mensagem, entao esta pagina prova o caso vazio.
    """
    inicio = pagina.index('class="mensagens"')
    regiao = pagina[inicio : pagina.index("</ul>", inicio)]
    assert "<li>" not in regiao, (
        "esta página deveria estar sem mensagem nenhuma; o teste perdeu o alvo"
    )


def test_a_regiao_vazia_nao_ocupa_espaco_na_tela():
    """A regiao passou a existir sempre; sem isto ela abriria um vao no topo de
    toda pagina do sistema, que e o preco que nao vale a pena pagar pelo
    anuncio."""
    assert ".mensagens:empty" in CSS, "lista vazia sem regra de ocultação"
