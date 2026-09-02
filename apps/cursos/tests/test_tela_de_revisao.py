"""A tela onde o professor decide, e o painel do que falta que ela compartilha.

Sem pendencia nenhuma a tela dizia, uma linha embaixo da outra:

    Ainda falta
    Nada. O entregável cumpre o que o roteiro pede.

O titulo era fixo dentro do include compartilhado, e so o texto de baixo vinha do
chamador. Como o painel serve tres telas, o defeito estava nas tres.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel


@pytest.fixture
def plano_em_revisao(dados_curso, professor, aluno):
    """Plano de Ensino escrito por inteiro e enviado: sem pendencia nenhuma."""
    from apps.cursos.tests.test_views_aluno import escrever_o_plano_inteiro

    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    escrever_o_plano_inteiro(plano)
    services.enviar_para_revisao(plano, por=aluno)
    return plano


@pytest.fixture
def slides_em_revisao(dados_curso, professor, aluno):
    """Enviado com pendencia: a equipe pode enviar assim mesmo."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    slides.status = StatusEntregavel.EM_REVISAO
    slides.save(update_fields=["status", "atualizado_em"])
    return slides


def revisar(client, entregavel):
    return client.get(reverse("revisar", args=[entregavel.pk])).content.decode()


# --- o painel do que falta ----------------------------------------------------


@pytest.mark.django_db
def test_sem_pendencia_o_painel_nao_diz_que_falta_algo(client, plano_em_revisao, professor):
    client.force_login(professor)
    html = revisar(client, plano_em_revisao)
    assert "Ainda falta" not in html
    assert "Tudo certo" in html
    assert "cumpre o que o roteiro pede" in html


@pytest.mark.django_db
def test_com_pendencia_o_painel_continua_dizendo_o_que_falta(
    client, slides_em_revisao, professor
):
    """O outro lado: o titulo muda com o estado, e nao sumiu."""
    client.force_login(professor)
    html = revisar(client, slides_em_revisao)
    assert "Ainda falta" in html
    assert "Tudo certo" not in html
    assert "Anexe ao menos um arquivo de slides." in html


# --- a decisao ----------------------------------------------------------------


@pytest.mark.django_db
def test_a_decisao_fica_no_proprio_cartao(client, slides_em_revisao, professor):
    """Estava solta dentro da mesma moldura do painel de pendencias, separada só
    por uma linha. São dois assuntos: o que falta e o que você decide."""
    client.force_login(professor)
    html = revisar(client, slides_em_revisao)
    import re

    aside = re.search(r'<aside class="([^"]*)"', html).group(1).split()
    # Classe a classe: o aside leva tres (`coluna-pendencias` entre elas), e
    # comparar a string inteira quebraria a cada classe acrescentada.
    assert {"lateral", "lateral-pilha"} <= set(aside), aside
    inicio = html.index("Sua decisão")
    cartao = html[html.rindex('<div class="cartao-lateral', 0, inicio) : inicio]
    assert "cartao-lateral" in cartao


@pytest.mark.django_db
def test_o_comentario_tem_editor(client, slides_em_revisao, professor):
    """O mesmo editor das seções e das descrições: é texto que a equipe vai ler
    para saber o que corrigir, e uma lista de itens ajuda mais que um parágrafo."""
    client.force_login(professor)
    html = revisar(client, slides_em_revisao)
    inicio = html.index('name="comentario"')
    campo = html[html.rindex("<textarea", 0, inicio) : html.index(">", inicio)]
    assert "data-editor" in campo


# --- o comentario e HTML, entao precisa ser sanitizado ------------------------


@pytest.mark.django_db
def test_o_comentario_da_revisao_e_sanitizado(slides_em_revisao, professor):
    """Terceiro campo do sistema a ganhar editor, e o terceiro a precisar disto:
    é renderizado com |safe na devolutiva que a equipe lê."""
    services.devolver_entregavel(
        slides_em_revisao,
        por=professor,
        comentario='<p>Refaça o slide 3</p><script>alert(1)</script>',
    )
    revisao = slides_em_revisao.revisoes.last()
    assert "<p>Refaça o slide 3</p>" in revisao.comentario
    assert "script" not in revisao.comentario


@pytest.mark.django_db
def test_a_sanitizacao_do_comentario_vale_em_update_fields(slides_em_revisao, professor):
    from apps.cursos.models import Revisao

    revisao = Revisao.objects.create(
        entregavel=slides_em_revisao, revisor=professor, decisao=Revisao.DEVOLVIDO
    )
    revisao.comentario = "<p>Texto</p><script>alert(1)</script>"
    revisao.save(update_fields=["comentario"])
    revisao.refresh_from_db()
    assert "<p>Texto</p>" in revisao.comentario
    assert "script" not in revisao.comentario


@pytest.mark.django_db
def test_a_devolutiva_mostra_a_formatacao_do_comentario(
    client, slides_em_revisao, professor, aluno
):
    """Com escape, o editor seria armadilha: o professor formata e a equipe lê
    `<strong>` como texto."""
    services.devolver_entregavel(
        slides_em_revisao,
        por=professor,
        comentario="<p>Refaça o <strong>slide 3</strong>.</p>",
    )
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[slides_em_revisao.pk])).content.decode()
    assert "<strong>slide 3</strong>" in html
    assert "&lt;strong&gt;" not in html
