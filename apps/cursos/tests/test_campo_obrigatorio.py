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
@pytest.mark.parametrize(
    "tipo,campos",
    [
        (TipoEntregavel.SLIDES, ["titulo", "descricao", "upload"]),
        (
            TipoEntregavel.CARDS,
            ["titulo", "descricao", "referencia_bibliografica", "tipo_pratica", "upload"],
        ),
        (TipoEntregavel.CADERNO, ["titulo", "descricao", "rotulo", "tipo_pratica", "upload"]),
        (TipoEntregavel.AVALIACAO, ["titulo", "descricao", "upload"]),
    ],
)
def test_todo_campo_de_entregavel_e_obrigatorio(client, curso_com_equipe, aluno, tipo, campos):
    """Nos entregaveis nao ha campo opcional: o que esta na tela e porque a regra
    daquele entregavel usa. O que sobrava por preencher voltava como pendencia na
    hora de enviar, longe do campo que resolve."""
    client.force_login(aluno)
    html = tela(client, curso_com_equipe, tipo)
    for nome in campos:
        assert 'class="obrigatorio"' in campo(html, nome), f"{tipo}.{nome}"


@pytest.mark.django_db
def test_na_ficha_o_opcional_continua_sem_asterisco(client, curso_com_equipe, professor):
    """O outro lado: a marca sai de `field.required`, e nao de um asterisco solto
    no template. Na ficha so o titulo e obrigatorio - a proposta nasce so com ele
    de proposito, e quem cobra o resto e `validacoes.dados_do_curso`."""
    client.force_login(professor)
    html = client.get(reverse("ficha", args=[curso_com_equipe.pk])).content.decode()
    assert 'class="obrigatorio"' in campo(html, "titulo")
    assert 'class="obrigatorio"' not in campo(html, "resumo")


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
def test_o_video_marca_os_quatro_campos(client, curso_com_equipe, aluno):
    client.force_login(aluno)
    html = tela(client, curso_com_equipe, TipoEntregavel.VIDEOS)
    for nome in ("upload", "titulo", "descricao", "duracao_minutos"):
        assert 'class="obrigatorio"' in campo(html, nome), nome


@pytest.mark.django_db
def test_as_secoes_do_plano_de_ensino_tambem_sao_marcadas(client, curso_com_equipe, aluno):
    """`_plano_de_ensino` reprova qualquer secao vazia, entao as sete sao
    obrigatorias para enviar."""
    import re

    client.force_login(aluno)
    html = tela(client, curso_com_equipe, TipoEntregavel.PLANO_ENSINO)
    # So os titulos de secao: contar a pagina inteira somaria a legenda "* Campo
    # obrigatório." e o numero deixaria de dizer o que o nome do teste promete.
    titulos = re.findall(r"<h3>.*?</h3>", html, re.S)
    assert len(titulos) == 7, f"esperava sete seções, vi {len(titulos)}"
    for titulo in titulos:
        assert 'class="obrigatorio"' in titulo, titulo[:60]


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


@pytest.mark.django_db
def test_a_palavra_obrigatorio_aparece_na_tela(client, curso_com_equipe, aluno):
    """Asterisco sem legenda e simbolo que a pessoa tem que adivinhar."""
    client.force_login(aluno)
    for tipo in TipoEntregavel:
        html = tela(client, curso_com_equipe, tipo)
        assert "obrigatório" in html.lower(), tipo


@pytest.mark.django_db
def test_a_legenda_some_para_quem_nao_pode_editar(client, curso_com_equipe, aluno):
    """Entregavel congelado nao tem campo nenhum: explicar o asterisco ali seria
    legenda de um simbolo que a tela nao mostra."""
    from apps.cursos.choices import StatusEntregavel

    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    slides.status = StatusEntregavel.EM_REVISAO
    slides.save(update_fields=["status", "atualizado_em"])
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[slides.pk])).content.decode()
    assert "legenda-obrigatorio" not in html


@pytest.mark.django_db
def test_marcar_nenhuma_pratica_deixa_de_ser_aceito(client, curso_com_equipe, aluno):
    """`tipo_pratica` tambem entrou no "todos obrigatorios": marcar nada era uma
    resposta valida e virava NENHUM, que e o que o catalogo le como "nao se
    aplica"."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    cards = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.CARDS)
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[cards.pk]),
        {
            "titulo": "Card 1",
            "descricao": "Um card sobre senhas.",
            "referencia_bibliografica": "BNCC, 2018.",
            "upload": SimpleUploadedFile("c.pdf", b"%PDF-1.7\n%x\n", content_type="application/pdf"),
        },
        follow=True,
    )
    assert not cards.anexos.exists()
    assert "obrigat" in resposta.content.decode().lower()


@pytest.mark.django_db
def test_nenhuma_ajuda_de_entregavel_diz_opcional():
    """O gêmeo de `test_nenhum_campo_obrigatorio_se_diz_opcional`, que varre os
    formulários instanciados sem argumento.

    `AnexoForm()` sem `tipo` nasce com tudo opcional, então a descrição escapava
    daquela varredura justamente na tela onde ela é obrigatória. Aqui o formulário
    é montado como a tela o monta, um por entregável.
    """
    from apps.cursos.forms import AnexoForm

    mentirosos = []
    for tipo in TipoEntregavel:
        for nome, definicao in AnexoForm(tipo=tipo).fields.items():
            if "opcional" in str(definicao.help_text).lower():
                mentirosos.append(f"{tipo.value}.{nome}")
    assert mentirosos == [], (
        "nos entregáveis todo campo é obrigatório, e estes dizem o contrário:\n"
        + "\n".join(mentirosos)
    )
