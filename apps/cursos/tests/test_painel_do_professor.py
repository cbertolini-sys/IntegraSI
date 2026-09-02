"""Os cartoes do painel de quem entra como professor.

Eram tres, e dois nao serviam: "Cursos sob sua responsabilidade" somava
publicados e em producao no mesmo numero, e "Turmas sob sua conducao" e execucao,
nao producao. E "Entregaveis para revisar" contava CURSOS - o rotulo dizia uma
coisa e o numero era outro, entao ele nunca batia com a fila em que clicar leva.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel


def cartoes(client):
    """Os rotulos dos cartoes do painel, na ordem em que a tela os mostra."""
    import re

    html = client.get(reverse("painel")).content.decode()
    lista = html[html.index('class="indicadores"') : html.index("</ul>", html.index('class="indicadores"'))]
    return re.findall(r'<a href="[^"]*">([^<]+)</a>', lista)


def valor_do_cartao(client, rotulo):
    import re

    html = client.get(reverse("painel")).content.decode()
    achado = re.search(
        r"<strong>(\d+)</strong>\s*<a[^>]*>" + re.escape(rotulo) + "</a>", html
    )
    assert achado, f"cartão {rotulo!r} não está na tela"
    return int(achado.group(1))


@pytest.mark.django_db
def test_o_professor_ve_exatamente_estes_tres_cartoes(client, professor):
    client.force_login(professor)
    assert cartoes(client) == [
        "Cursos publicados",
        "Cursos em desenvolvimento",
        "Entregáveis para revisar",
    ]


@pytest.mark.django_db
def test_publicados_e_em_desenvolvimento_sao_contas_separadas(
    client, dados_curso, professor, aluno, coordenador
):
    from apps.catalogo.tests.test_catalogo import publica

    em_producao = services.criar_curso(**dados_curso)
    publicado = services.criar_curso(**dados_curso)
    publica(publicado, aluno, professor, coordenador)

    client.force_login(professor)
    assert valor_do_cartao(client, "Cursos publicados") == 1
    assert valor_do_cartao(client, "Cursos em desenvolvimento") == 1
    assert em_producao.status != StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_curso_substituido_nao_conta_como_em_desenvolvimento(
    client, dados_curso, professor
):
    """Versao antiga e historico, e nao trabalho por fazer. Mesma coisa para o
    despublicado: ele ja foi ao catalogo e voltou, nao esta sendo produzido."""
    curso = services.criar_curso(**dados_curso)
    curso.status = StatusCurso.SUBSTITUIDO
    curso.save(update_fields=["status"])

    client.force_login(professor)
    assert valor_do_cartao(client, "Cursos em desenvolvimento") == 0
    assert valor_do_cartao(client, "Cursos publicados") == 0


@pytest.mark.django_db
def test_entregaveis_para_revisar_conta_entregaveis_e_nao_cursos(
    client, dados_curso, professor, aluno
):
    """O numero precisa bater com a fila que o cartao abre: dois entregaveis do
    MESMO curso sao dois itens la, e o `.distinct()` por curso dizia um."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.filter(
        tipo__in=[TipoEntregavel.SLIDES, TipoEntregavel.CARDS]
    ).update(status=StatusEntregavel.EM_REVISAO)

    client.force_login(professor)
    assert valor_do_cartao(client, "Entregáveis para revisar") == 2

    fila = client.get(reverse("fila_revisao")).content.decode()
    assert fila.count("Slides e Apresentações") == 1
    assert fila.count("Infográficos e Cards Educativos") == 1


@pytest.mark.django_db
def test_o_painel_do_coordenador_nao_mudou(client, coordenador):
    """A troca e do professor. O coordenador tem outro recorte, e `e_professor`
    tambem vale para ele - trocar o ramo errado levaria os cartoes dele junto."""
    client.force_login(coordenador)
    # "Turmas agendadas" saiu a pedido: turmas viraram modulo de outra etapa.
    assert cartoes(client) == [
        "Aguardando aprovação",
        "Solicitações a responder",
        "Cursos no catálogo",
    ]


@pytest.mark.django_db
def test_o_painel_do_aluno_nao_mudou(client, aluno):
    client.force_login(aluno)
    assert cartoes(client) == ["Cursos em que você produz"]
