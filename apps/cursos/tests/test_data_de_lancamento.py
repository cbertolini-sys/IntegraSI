"""De quando e o curso, na pagina publica.

Com a remocao do app `edicoes` o catalogo perdeu a unica marca de tempo que
tinha: a pagina do curso dizia "Versão 1 &middot; 2026/2". Depois disso, nada
dizia mais de quando o curso e.

O dado, porem, ja existia. `Curso.publicado_em` e gravado na transicao para
PUBLICADO desde o Plano 3, e nunca foi mostrado em tela nenhuma. Acrescentar um
campo novo de "data de lancamento" ao lado dele criaria segunda fonte de verdade
para a mesma pergunta, e sairia de sincronia na primeira vez que alguem editasse
um dos dois - e o mesmo argumento que este projeto usa contra flag paralela de
perfil completo.

O que faltava era o campo significar o que o nome promete. Ele era regravado a
cada transicao para PUBLICADO, entao um curso despublicado e republicado passava
a alegar ter sido lancado no dia da republicacao.
"""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

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


def com_data(curso, ano, mes, dia):
    """Fixa a data de lancamento: sem isto o teste afirmaria sobre `now()` e
    passaria a reprovar sozinho na virada de qualquer mes."""
    curso.publicado_em = timezone.make_aware(datetime.datetime(ano, mes, dia, 9, 0))
    curso.save(update_fields=["publicado_em", "atualizado_em"])
    return curso


# --- o campo significa o que o nome promete -----------------------------------


@pytest.mark.django_db
def test_a_primeira_publicacao_grava_a_data_de_lancamento(curso_publicado):
    assert curso_publicado.publicado_em is not None


@pytest.mark.django_db
def test_republicar_nao_reescreve_a_data_de_lancamento(curso_publicado, coordenador):
    """O curso foi lancado uma vez. Tirar do ar e repor nao o torna um curso novo,
    e a pagina publica passaria a alegar um lancamento que nao houve."""
    lancamento = com_data(curso_publicado, 2026, 3, 15).publicado_em

    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Ajuste no material.")
    services.publicar_curso(curso_publicado, por=coordenador)
    curso_publicado.refresh_from_db()

    assert curso_publicado.status == StatusCurso.PUBLICADO
    assert curso_publicado.publicado_em == lancamento


# --- a tela -------------------------------------------------------------------


@pytest.mark.django_db
def test_a_pagina_publica_diz_quando_o_curso_foi_lancado(client, curso_publicado):
    com_data(curso_publicado, 2026, 3, 15)

    html = client.get(reverse("catalogo_curso", args=[curso_publicado.pk])).content.decode()

    assert "Lançado em março de 2026" in html


@pytest.mark.django_db
def test_a_previa_de_curso_nao_publicado_nao_fala_em_lancamento(
    client, dados_curso, professor, aluno
):
    """A mesma tela serve a previa da equipe, onde `publicado_em` e nulo. Sem
    guarda ela imprimiria "Lançado em " seguido de nada, ou "None"."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)

    client.force_login(aluno)
    html = client.get(reverse("previa_do_curso", args=[curso.pk])).content.decode()

    assert curso.publicado_em is None
    assert "Lançado em" not in html
    assert "None" not in html
