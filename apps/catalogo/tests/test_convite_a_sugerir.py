"""Onde a comunidade encontra o "Sugerir um curso".

O formulario nasceu com uma porta so: o resultado vazio da busca. Isso cobre quem
procurou e nao achou, e deixa de fora quem chega sem saber o que procurar, ou
quem nem chega a buscar. Duas portas a mais, a pedido: a barra do topo e um
cartao no carrossel do heroi.

O cartao do carrossel tem uma armadilha propria, e e o que o teste do pareamento
prende: `static/js/vitrine.js` casa cada `.ponto` com um `.vitrine-slide` PELO
INDICE. Acrescentar um slide e esquecer o ponto nao quebra a pagina - ela carrega
inteira, bonita, e a navegacao por pontos passa a apontar para o slide errado a
partir do ultimo. Defeito que so aparece clicando.
"""

import re

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso
from apps.cursos.models import Curso


@pytest.fixture
def com_cursos_publicados(dados_curso, professor, db):
    for i in range(3):
        services.criar_curso(**dict(dados_curso, titulo=f"Curso publicado {i}"))
    Curso.objects.update(status=StatusCurso.PUBLICADO)


# --- a barra do topo ----------------------------------------------------------


@pytest.mark.django_db
def test_a_barra_do_topo_oferece_sugerir_a_quem_nao_tem_conta(client):
    """A demanda vem de fora: quem sugere e justamente quem nao tem login."""
    html = client.get(reverse("catalogo")).content.decode()
    barra = html[html.index('<nav class="menu">') : html.index("</nav>")]

    assert reverse("sugerir") in barra, barra


@pytest.mark.django_db
def test_a_barra_do_topo_continua_oferecendo_a_quem_esta_logado(client, professor):
    """O professor tambem circula pelo catalogo publico, e ver a porta o ajuda a
    saber que ela existe quando alguem perguntar."""
    client.force_login(professor)
    html = client.get(reverse("catalogo")).content.decode()
    barra = html[html.index('<nav class="menu">') : html.index("</nav>")]

    assert reverse("sugerir") in barra


# --- o cartao no carrossel ----------------------------------------------------


@pytest.mark.django_db
def test_o_carrossel_termina_com_o_convite_a_sugerir(client, com_cursos_publicados):
    html = client.get(reverse("catalogo")).content.decode()
    slides = re.findall(r'<li class="vitrine-slide.*?</li>', html, re.S)

    assert len(slides) == 4, f"3 cursos e o convite dão 4 slides, vi {len(slides)}"
    assert reverse("sugerir") in slides[-1], slides[-1]


@pytest.mark.django_db
def pontos_do_carrossel(html):
    """So os pontos do carrossel.

    Contar por `class="ponto"` conta errado, e a primeira versao deste teste
    contava: a classe e usada em DOIS sentidos no projeto, o ponto navegavel do
    carrossel e um marcador decorativo dentro dos cartoes de curso e da pagina
    publica. O recorte pelo contêiner `data-pontos` e o que separa os dois.
    """
    inicio = html.index("data-pontos")
    return re.findall(r'role="tab"', html[inicio : html.index("</div>", inicio)])


@pytest.mark.django_db
def test_cada_slide_tem_o_seu_ponto(client, com_cursos_publicados):
    """A invariante de que o `vitrine.js` depende: ele casa ponto e slide PELO
    INDICE. Slide sem ponto nao quebra a pagina, quebra a navegacao, e so
    clicando se descobre."""
    html = client.get(reverse("catalogo")).content.decode()
    slides = re.findall(r'<li class="vitrine-slide', html)

    assert len(slides) == len(pontos_do_carrossel(html)), (
        f"{len(slides)} slides e {len(pontos_do_carrossel(html))} pontos"
    )


@pytest.mark.django_db
def test_o_convite_aparece_mesmo_com_um_curso_so(client, dados_curso, professor):
    """Com um curso o carrossel nao mostrava setas nem pontos, porque um slide so
    nao se navega. Com o convite sempre presente sao dois, e a navegacao volta a
    fazer sentido."""
    services.criar_curso(**dados_curso)
    Curso.objects.update(status=StatusCurso.PUBLICADO)

    html = client.get(reverse("catalogo")).content.decode()

    assert len(re.findall(r'<li class="vitrine-slide', html)) == 2
    assert len(pontos_do_carrossel(html)) == 2


@pytest.mark.django_db
def test_catalogo_vazio_tambem_convida(client):
    """Catalogo sem curso nenhum e quando MAIS importa perguntar o que falta, e
    era exatamente a tela que so dizia "está sendo montado" e parava ali."""
    html = client.get(reverse("catalogo")).content.decode()
    inicio = html.index("vazio-vitrine")
    cartao = html[inicio : html.index("</div>", inicio)]

    assert "está sendo montado" in cartao
    assert reverse("sugerir") in cartao, cartao
