"""Os dois cartoes do painel levam a duas listas diferentes.

Antes os dois abriam a MESMA lista, com tudo: o cartao dizia "2 publicados" e a
tela mostrava os cinco cursos da pessoa. O numero e o recorte tem que ser o
mesmo dos dois lados.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso


@pytest.fixture
def tres_cursos(dados_curso, professor, aluno, coordenador):
    """Um publicado, um em producao e um substituido."""
    from apps.catalogo.tests.test_catalogo import publica

    publicado = services.criar_curso(**dados_curso)
    publica(publicado, aluno, professor, coordenador)
    publicado.titulo = "Curso publicado"
    publicado.save(update_fields=["titulo"])

    em_producao = services.criar_curso(**dados_curso)
    em_producao.titulo = "Curso em producao"
    em_producao.save(update_fields=["titulo"])

    antigo = services.criar_curso(**dados_curso)
    antigo.titulo = "Versao antiga"
    antigo.status = StatusCurso.SUBSTITUIDO
    antigo.save(update_fields=["titulo", "status"])
    return publicado, em_producao, antigo


def lista(client, **parametros):
    url = reverse("meus_cursos")
    if parametros:
        url += "?" + "&".join(f"{c}={v}" for c, v in parametros.items())
    return client.get(url).content.decode()


@pytest.mark.django_db
def test_publicados_mostra_so_os_publicados(client, tres_cursos, professor):
    client.force_login(professor)
    html = lista(client, estado="publicados")
    assert "Curso publicado" in html
    assert "Curso em producao" not in html
    assert "Versao antiga" not in html


@pytest.mark.django_db
def test_desenvolvimento_mostra_so_os_que_ainda_nao_foram_publicados(
    client, tres_cursos, professor
):
    """Versao substituida nao entra: ja foi publicada uma vez e seguiu adiante,
    entao nao e trabalho por fazer. Mesmo criterio de STATUS_EM_DESENVOLVIMENTO,
    que e o que o cartao conta."""
    client.force_login(professor)
    html = lista(client, estado="desenvolvimento")
    assert "Curso em producao" in html
    assert "Curso publicado" not in html
    assert "Versao antiga" not in html


@pytest.mark.django_db
def test_sem_filtro_a_lista_continua_inteira(client, tres_cursos, professor):
    client.force_login(professor)
    html = lista(client)
    for titulo in ("Curso publicado", "Curso em producao", "Versao antiga"):
        assert titulo in html, titulo


@pytest.mark.django_db
def test_estado_desconhecido_mostra_tudo_em_vez_de_nada(client, tres_cursos, professor):
    """Igualdade explicita nos dois ramos, sem pega-tudo: um valor inesperado nao
    pode cair num filtro que esconde os cursos da pessoa sem dizer por que. O
    mesmo padrao ja mordeu este projeto em `decidir_curso` e nas solicitacoes."""
    client.force_login(professor)
    html = lista(client, estado="qualquer-coisa")
    for titulo in ("Curso publicado", "Curso em producao", "Versao antiga"):
        assert titulo in html, titulo


@pytest.mark.django_db
def test_o_cartao_leva_a_lista_ja_filtrada(client, tres_cursos, professor):
    """Prende os dois lados juntos: o cartao conta um recorte e precisa abrir esse
    recorte, e nao a lista inteira."""
    client.force_login(professor)
    painel = client.get(reverse("painel")).content.decode()
    destino = reverse("meus_cursos")
    assert f'href="{destino}?estado=publicados"' in painel
    assert f'href="{destino}?estado=desenvolvimento"' in painel


@pytest.mark.django_db
def test_a_lista_tem_volta_para_o_painel(client, tres_cursos, professor):
    client.force_login(professor)
    html = lista(client)
    assert reverse("painel") in html
    assert "Voltar ao painel" in html
