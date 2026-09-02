"""A tela onde a coordenacao decide sobre um curso.

Tres coisas pedidas, e uma descoberta no caminho: os dois textos da tela (o
comentario da devolucao e o motivo da despublicacao) gravam no MESMO campo,
`LogTransicaoCurso.observacao`, que nao aparece em tela nenhuma. Era o "campo que
so entra" de novo - o mesmo padrao ja corrigido em `Anexo.descricao`.
"""

import pytest
from django.urls import reverse

from apps.catalogo.tests.test_catalogo import publica
from apps.cursos import services
from apps.cursos.choices import StatusCurso
from apps.cursos.models import LogTransicaoCurso


@pytest.fixture
def publicado(dados_curso, aluno, professor, coordenador):
    curso = services.criar_curso(**dados_curso)
    publica(curso, aluno, professor, coordenador)
    return curso


def tela(client, curso, **params):
    url = reverse("analisar_curso", args=[curso.pk])
    if params:
        url += "?" + "&".join(f"{c}={v}" for c, v in params.items())
    return client.get(url).content.decode()


# --- o motivo e obrigatorio, e a tela diz isso -------------------------------


@pytest.mark.django_db
def test_o_motivo_da_despublicacao_e_marcado_como_obrigatorio(client, publicado, coordenador):
    """O servico ja recusava vazio; a tela nao avisava, e a pessoa escrevia a
    decisao inteira para descobrir depois."""
    client.force_login(coordenador)
    html = tela(client, publicado)
    campo = html[html.index("Motivo da despublicação") - 200 : html.index("DESPUBLICAR")]
    assert 'class="obrigatorio"' in campo
    assert "required" in campo


@pytest.mark.django_db
def test_despublicar_sem_motivo_continua_recusado(client, publicado, coordenador):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("decidir_curso", args=[publicado.pk]),
        {"decisao": "DESPUBLICAR", "comentario": "   "},
        follow=True,
    )
    publicado.refresh_from_db()
    assert publicado.status == StatusCurso.PUBLICADO
    assert "motivo" in resposta.content.decode().lower()


# --- editor nos dois textos da tela ------------------------------------------


@pytest.mark.django_db
def test_os_textos_da_decisao_tem_editor(
    client, publicado, dados_curso, aluno, professor, coordenador
):
    """Os dois gravam no mesmo campo; um com editor e outro sem seria a mesma
    coisa com duas caras.

    Um de cada vez, e nao os dois na mesma tela: os formularios sao mutuamente
    exclusivos (`if pode_decidir` / `elif pode_despublicar`), entao cada estado do
    curso mostra so o seu. A primeira versao deste teste contava dois na mesma
    pagina e nunca poderia passar.
    """
    from apps.cursos.choices import StatusEntregavel

    client.force_login(coordenador)
    # Publicado: aparece o motivo da despublicacao.
    assert "data-editor" in tela(client, publicado)

    # Aguardando a coordenacao: aparece o comentario da decisao.
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.all().update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    html = tela(client, curso)
    assert "Decisão da coordenação" in html
    assert "data-editor" in html


@pytest.mark.django_db
def test_a_observacao_do_log_e_sanitizada(publicado, coordenador):
    """O editor grava HTML, e HTML sem sanitizacao e o quarto caminho para script
    no navegador de quem ler o historico um dia."""
    services.despublicar_curso(
        publicado, por=coordenador,
        motivo="<p>Material desatualizado</p><script>alert(1)</script>",
    )
    log = LogTransicaoCurso.objects.filter(curso=publicado).last()
    assert "<p>Material desatualizado</p>" in log.observacao
    assert "script" not in log.observacao


@pytest.mark.django_db
def test_a_sanitizacao_do_log_vale_em_update_fields(publicado, coordenador):
    log = LogTransicaoCurso.objects.filter(curso=publicado).last()
    log.observacao = "<p>Texto</p><script>alert(1)</script>"
    log.save(update_fields=["observacao"])
    log.refresh_from_db()
    assert "<p>Texto</p>" in log.observacao
    assert "script" not in log.observacao


# --- a volta leva de onde a pessoa veio --------------------------------------


@pytest.mark.django_db
def test_a_volta_leva_a_lista_de_cursos_quando_veio_de_la(client, publicado, coordenador):
    client.force_login(coordenador)
    html = tela(client, publicado, voltar="catalogo")
    assert reverse("cursos_no_catalogo") in html
    assert "Voltar aos cursos" in html


@pytest.mark.django_db
def test_sem_parametro_a_volta_leva_a_fila(client, publicado, coordenador):
    client.force_login(coordenador)
    html = tela(client, publicado)
    assert reverse("fila_coordenacao") in html


@pytest.mark.django_db
def test_a_lista_de_cursos_manda_a_volta_no_link(client, publicado, coordenador):
    """Prende as duas pontas: nao adianta a tela saber voltar se o caminho de ida
    nao diz de onde veio."""
    client.force_login(coordenador)
    html = client.get(reverse("cursos_no_catalogo")).content.decode()
    assert reverse("analisar_curso", args=[publicado.pk]) + "?voltar=catalogo" in html


# --- turmas sai do painel -----------------------------------------------------


@pytest.mark.django_db
def test_o_painel_da_coordenacao_nao_fala_mais_em_turmas(client, coordenador):
    """Turmas viraram modulo de outra etapa, a desenvolver."""
    client.force_login(coordenador)
    html = client.get(reverse("painel")).content.decode()
    assert "Turmas agendadas" not in html
    assert reverse("minhas_turmas") not in html


@pytest.mark.django_db
def test_a_pagina_sobre_nao_promete_turmas_no_painel_da_coordenacao(client):
    """A pagina listava as quatro frentes do painel, e uma delas era turmas."""
    conteudo = client.get(reverse("sobre")).content.decode()
    inicio = conteudo.index('<ol class="fluxograma coordenacao">')
    fluxo = conteudo[inicio : conteudo.index("</ol>", inicio)]
    painel = fluxo[fluxo.index("<h4>Painel</h4>") : fluxo.index("</li>", fluxo.index("<h4>Painel</h4>"))]
    assert "turmas" not in painel.lower()
