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


@pytest.mark.django_db
def test_as_secoes_da_pagina_fecham(client):
    """A seção dos fluxogramas não fechava, e a chamada final ficava aninhada
    dentro dela.

    O navegador conserta sozinho e a tela parece certa, então o defeito só
    apareceria no dia em que alguém estilizasse `.bloco-sobre > *` ou lesse a
    página com leitor de tela. A página é estática (só `{% url %}`), então contar
    as tags aqui é uma medida honesta.
    """
    import re

    conteudo = client.get(reverse("sobre")).content.decode()
    # Do `<div` que abre a pagina, e nao de dentro dele: comecando na classe, o
    # recorte pegava o `</div>` da propria faixa sem o `<div>` correspondente e a
    # conta nascia torta por construcao.
    corpo = conteudo[conteudo.rindex("<div", 0, conteudo.index("pagina-sobre")) : conteudo.index("</main>")]
    for tag in ("section", "article", "ol", "ul", "li", "div"):
        abre = len(re.findall(rf"<{tag}\b", corpo))
        fecha = len(re.findall(rf"</{tag}>", corpo))
        assert abre == fecha, f"<{tag}>: {abre} abrem, {fecha} fecham"


@pytest.mark.django_db
def test_a_pagina_nomeia_os_seis_entregaveis(client):
    """Lida do enum, e não de uma lista escrita à mão: a página já falou em cinco
    depois que o roteiro passou a ter seis, e um sétimo entregável precisa
    reprovar aqui em vez de sair calado numa página pública."""
    from apps.cursos.choices import TipoEntregavel

    conteudo = client.get(reverse("sobre")).content.decode()
    # NO PASSO que enumera os seis, e nao na pagina inteira: varrendo tudo, o
    # teste passava com "avaliação" apagada da lista, porque a palavra aparece
    # tambem na lista dos pilares, mais acima. Achado na campanha de deleção.
    inicio = conteudo.index("Nasce com os seis entregáveis")
    passo = conteudo[inicio : conteudo.index("</li>", inicio)].lower()
    faltando = [
        t.label for t in TipoEntregavel
        # O rótulo é "2 - Slides e Apresentações"; a página fala em prosa, então
        # a comparação é pela primeira palavra significativa de cada nome.
        if t.label.split(" - ", 1)[-1].split()[0].lower() not in passo
    ]
    assert faltando == [], f"o passo não menciona: {faltando}"


@pytest.mark.django_db
def test_a_pagina_nao_promete_uma_proposta_que_o_formulario_nao_pede(client):
    """A página listava "título, resumo, público-alvo, carga horária, formato e
    temas" como o que a proposta pede. Desde o Plano 6 ela nasce só com o título,
    e o resto é trabalho da equipe: a página prometia à comunidade um passo que o
    sistema não tem."""
    from apps.cursos.forms import PropostaForm

    conteudo = client.get(reverse("sobre")).content.decode()
    assert list(PropostaForm().fields) == ["titulo"], "a proposta mudou de campos"
    # O PASSO do fluxograma, e nao a primeira ocorrencia do texto: "Cria a
    # proposta" aparece antes, no paragrafo de apresentacao do professor, e uma
    # janela a partir dali nem alcancava a lista de campos.
    inicio = conteudo.index("<h4>Cria a proposta</h4>")
    trecho = conteudo[inicio : conteudo.index("</li>", inicio)]
    # Afirmar sobre a palavra "carga horária" nao serve: a frase CERTA tambem a
    # usa, para dizer que ela e trabalho da equipe. O que o passo precisa dizer e
    # que a proposta pede o titulo e mais nada.
    assert "Só o título" in trecho, trecho


@pytest.mark.django_db
def test_as_voltas_do_fluxograma_apontam_para_passos_que_existem(client):
    """"volta ao passo N" é um número escrito à mão sobre uma lista numerada pelo
    `<ol>`: acrescentar um passo no meio desloca todos os seguintes e as voltas
    passam a apontar para a etapa errada, calada.

    Aconteceu agora: o fluxo do professor ganhou "Produz junto com a equipe" e as
    três voltas apontavam para a fila de revisão, que virou o passo 7.
    """
    import re

    conteudo = client.get(reverse("sobre")).content.decode()
    for fluxo in re.findall(r'<ol class="fluxograma \w+">(.*?)</ol>', conteudo, re.S):
        passos = re.findall(r"<h4>(.*?)</h4>", fluxo, re.S)
        for numero in re.findall(r"volta ao passo (\d+)", fluxo):
            assert 1 <= int(numero) <= len(passos), (
                f"volta ao passo {numero}, mas o fluxo tem {len(passos)} passos"
            )

    # A faixa sozinha nao basta: acrescentar um passo no meio mantem todos os
    # numeros DENTRO da faixa e faz cada volta apontar para o passo de cima. As
    # tres voltas do professor levam a fila de revisao, e e isso que se prende.
    inicio = conteudo.index('<ol class="fluxograma professor">')
    fluxo = conteudo[inicio : conteudo.index("</ol>", inicio)]
    passos = re.findall(r"<h4>(.*?)</h4>", fluxo, re.S)
    voltas = re.findall(r"volta ao passo (\d+)", fluxo)
    assert voltas, "o fluxo do professor perdeu as voltas"
    for numero in voltas:
        alvo = passos[int(numero) - 1]
        assert "fila de revisão" in alvo.lower(), (
            f"volta ao passo {numero} aponta para {alvo!r}, e não para a fila"
        )


@pytest.mark.django_db
def test_o_fluxo_do_professor_cita_as_tres_decisoes(client):
    """Aprovar, devolver e reabrir sao os tres valores de `Revisao.DECISOES`, e os
    tres tem botao na tela. A pagina descrevia so os dois primeiros."""
    from apps.cursos.models import Revisao

    conteudo = client.get(reverse("sobre")).content.decode()
    inicio = conteudo.index('<ol class="fluxograma professor">')
    fluxo = conteudo[inicio : conteudo.index("</ol>", inicio)].lower()
    for _, rotulo in Revisao.DECISOES:
        # Quatro letras: o enum diz "Reaberto" e a prosa diz "reabre", entao o
        # radical comum e "reab". Com seis letras o teste cobrava "reabe", que a
        # prosa correta nao tem - e reprovava a pagina certa.
        assert rotulo.lower()[:4] in fluxo, rotulo
