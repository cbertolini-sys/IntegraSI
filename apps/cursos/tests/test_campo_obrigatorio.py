"""O asterisco de campo obrigatorio.

A marca so vale se disser a verdade, e tres campos mentiriam: `upload` era
`required=False` nos dois formularios (mas nao da para anexar sem arquivo, e o
video sem arquivo nao sobe), e a referencia bibliografica dos cards e cobrada por
`validacoes._cards` sem o formulario pedir. Marcar o que ja estava certo e
esconder esses tres seria trocar uma falta de informacao por uma informacao
errada.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import TipoEntregavel


@pytest.fixture
def curso_com_equipe(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso


def campo(html, nome):
    """O `.campo` inteiro do campo `nome`, do <div> ate o fim do bloco."""
    marca = f'name="{nome}"'
    assert marca in html, nome
    inicio = html.rindex('<div class="campo', 0, html.index(marca))
    return html[inicio : html.index("</div>", html.index(marca))]


def tela(client, curso, tipo):
    entregavel = curso.entregaveis.get(tipo=tipo)
    return client.get(reverse("entregavel", args=[entregavel.pk])).content.decode()


@pytest.mark.django_db
def test_o_obrigatorio_ganha_asterisco_e_o_opcional_nao(client, curso_com_equipe, aluno):
    client.force_login(aluno)
    html = tela(client, curso_com_equipe, TipoEntregavel.SLIDES)
    assert 'class="obrigatorio"' in campo(html, "titulo")
    assert 'class="obrigatorio"' not in campo(html, "descricao")


@pytest.mark.django_db
def test_o_arquivo_e_obrigatorio_e_diz_isso(client, curso_com_equipe, aluno):
    """Nao existe mais anexo sem arquivo: o campo de link saiu de todos os
    entregaveis. Era `required=False` com o `clean()` recusando depois - a pessoa
    so descobria ao enviar."""
    client.force_login(aluno)
    html = tela(client, curso_com_equipe, TipoEntregavel.SLIDES)
    assert 'class="obrigatorio"' in campo(html, "upload")
    assert "required" in campo(html, "upload")


@pytest.mark.django_db
def test_a_referencia_e_obrigatoria_so_nos_cards(client, curso_com_equipe, aluno):
    """`_cards` cobra a referencia de CADA card, e nenhuma outra regra a pede. O
    formulario dizia opcional nos dois casos."""
    client.force_login(aluno)
    html = tela(client, curso_com_equipe, TipoEntregavel.CARDS)
    assert 'class="obrigatorio"' in campo(html, "referencia_bibliografica")


@pytest.mark.django_db
def test_anexar_card_sem_referencia_e_recusado_no_proprio_campo(
    client, curso_com_equipe, aluno
):
    """O asterisco precisa ter consequencia: marcar sem recusar seria enfeite."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    cards = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.CARDS)
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[cards.pk]),
        {
            "titulo": "Card 1",
            "upload": SimpleUploadedFile("c.pdf", b"%PDF-1.7\n%x\n", content_type="application/pdf"),
        },
        follow=True,
    )
    assert not cards.anexos.exists()
    assert "obrigat" in resposta.content.decode().lower()


@pytest.mark.django_db
def test_o_video_marca_arquivo_titulo_e_duracao(client, curso_com_equipe, aluno):
    client.force_login(aluno)
    html = tela(client, curso_com_equipe, TipoEntregavel.VIDEOS)
    for nome in ("upload", "titulo", "duracao_minutos"):
        assert 'class="obrigatorio"' in campo(html, nome), nome
    assert 'class="obrigatorio"' not in campo(html, "descricao")


@pytest.mark.django_db
def test_as_secoes_do_plano_de_ensino_tambem_sao_marcadas(client, curso_com_equipe, aluno):
    """`_plano_de_ensino` reprova qualquer secao vazia, entao as sete sao
    obrigatorias para enviar."""
    client.force_login(aluno)
    html = tela(client, curso_com_equipe, TipoEntregavel.PLANO_ENSINO)
    assert html.count('class="obrigatorio"') == 7


@pytest.mark.django_db
def test_o_asterisco_nao_e_lido_em_voz_alta(client, curso_com_equipe, aluno):
    """Quem usa leitor de tela ouve o `required` do proprio campo; o asterisco
    seria "asterisco" no meio do rotulo, duas vezes a mesma informacao e uma
    delas sem sentido."""
    import re

    client.force_login(aluno)
    html = tela(client, curso_com_equipe, TipoEntregavel.SLIDES)
    for marca in re.findall(r'<span class="obrigatorio"[^>]*>', html):
        assert 'aria-hidden="true"' in marca, marca
