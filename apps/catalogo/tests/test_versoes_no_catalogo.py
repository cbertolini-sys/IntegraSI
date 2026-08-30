"""A linhagem de versoes vista de fora, pelo visitante (Plano 4, Task 6).

As regras que este arquivo prende:

 1. O catalogo mostra UMA entrada por linhagem: a versao publicada. Nao ha
    DISTINCT ON nem agrupamento na consulta - quem garante isso e a invariante da
    Task 5 (no maximo uma versao PUBLICADO por linhagem, com constraint no banco).
    Este arquivo e o teste dessa invariante pelo lado de fora.
 2. Enquanto a nova versao esta em producao, a anterior continua no catalogo e
    continua solicitavel (spec 4.5).
 3. Publicada a nova, a anterior vira SUBSTITUIDO: sai da listagem e a pagina
    publica dela responde 404 - a URL antiga nao pode continuar servindo material
    superado.
 4. A pagina publica diz qual versao e de que edicao ela e.

O teste do plano contava ocorrencias do titulo no HTML (`count(...) == 1`). Trocado
por assercao sobre a linhagem em si - a lista de cursos que a view entrega e as
URLs presentes - porque a contagem quebraria a toa no dia em que o titulo
aparecesse tambem num `alt`, num `title` ou numa migalha de navegacao, sem que
nada de errado tivesse acontecido.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel


@pytest.fixture
def curso_publicado(dados_curso, aluno, professor, coordenador):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    curso.refresh_from_db()
    return curso


def publica_nova_versao(curso, professor, coordenador, aluno):
    nova = services.abrir_nova_versao(curso, por=coordenador, motivo="Melhorias.")
    services.adicionar_membro(nova, aluno, por=professor)
    nova.entregaveis.update(status=StatusEntregavel.APROVADO)
    nova.refresh_from_db()
    services.submeter_ao_coordenador(nova, por=professor)
    services.publicar_curso(nova, por=coordenador)
    nova.refresh_from_db()
    return nova


@pytest.mark.django_db
def test_catalogo_mostra_a_linhagem_uma_vez_so(client, curso_publicado, professor, coordenador, aluno):
    nova = publica_nova_versao(curso_publicado, professor, coordenador, aluno)

    resposta = client.get(reverse("catalogo"))

    assert [curso.pk for curso in resposta.context["cursos"]] == [nova.pk]
    assert reverse("catalogo_curso", args=[curso_publicado.pk]) not in resposta.content.decode()


@pytest.mark.django_db
def test_durante_a_producao_da_nova_a_antiga_continua_no_catalogo(client, curso_publicado, coordenador):
    services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Melhorias.")

    resposta = client.get(reverse("catalogo"))

    assert [curso.pk for curso in resposta.context["cursos"]] == [curso_publicado.pk]
    assert client.get(reverse("solicitar", args=[curso_publicado.pk])).status_code == 200


@pytest.mark.django_db
def test_versao_substituida_sai_do_catalogo_e_a_pagina_dela_some(
    client, curso_publicado, professor, coordenador, aluno
):
    publica_nova_versao(curso_publicado, professor, coordenador, aluno)
    curso_publicado.refresh_from_db()

    assert curso_publicado.status == StatusCurso.SUBSTITUIDO
    assert client.get(reverse("catalogo_curso", args=[curso_publicado.pk])).status_code == 404


@pytest.mark.django_db
def test_pagina_publica_mostra_a_versao_e_a_edicao(client, curso_publicado, professor, coordenador, aluno):
    nova = publica_nova_versao(curso_publicado, professor, coordenador, aluno)

    conteudo = client.get(reverse("catalogo_curso", args=[nova.pk])).content.decode()

    assert "Versão 2" in conteudo
    assert str(nova.edicao) in conteudo
