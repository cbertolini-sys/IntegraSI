"""A proposta nao depende da edicao corrente, e as telas aguentam a ausencia dela.

Na instalacao nova de 200.132.38.187 nao havia edicao nenhuma cadastrada, e o
primeiro professor a tentar propor um curso levou "Nenhuma edição da disciplina
está aberta". O sistema inteiro ficava fechado para producao ate alguem abrir uma
edicao pelo Django Admin, e nada na tela dizia isso a quem podia resolver.

A edicao e rotulo de catalogo (spec 4.1): diz em que semestre o curso foi
produzido. Rotulo nao tranca porta. `abrir_nova_versao` ja se recusava a depender
dela, com o motivo escrito no proprio comentario; a criacao dependia.

Com o campo opcional aparece o outro risco, o que a suite verde nao mostra: o
Django renderiza `None` como o texto "None", entao qualquer template que
interpolasse `{{ curso.edicao }}` direto passaria a imprimir "None" na tela. E a
mesma armadilha dos campos da ficha, que ja custou uma vez neste projeto.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel
from apps.edicoes.models import Edicao


@pytest.fixture
def sem_edicao(db):
    """Nenhuma edicao aberta: o estado de uma instalacao recem-inaugurada."""
    Edicao.objects.filter(ativa=True).update(ativa=False)


@pytest.fixture
def curso_completo_sem_edicao(dados_curso):
    """Um curso com a ficha inteira preenchida e SEM edicao.

    `dados_curso` traz a ficha completa (e o portao de completude exige tudo para
    submeter), mas tambem traz a edicao pronta. Aqui ela sai do dicionario e a
    fixture desativa a que a `dados_curso` criou, para que `criar_curso` procure a
    corrente e nao ache nenhuma - que e o estado da instalacao nova.
    """
    dados = {campo: valor for campo, valor in dados_curso.items() if campo != "edicao"}
    Edicao.objects.filter(ativa=True).update(ativa=False)
    curso = services.criar_curso(**dados)
    assert curso.edicao is None, "a fixture nao montou o cenario que ela promete"
    return curso


def ate_a_coordenacao(curso, professor, aluno):
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)


def so_o_trecho(html, abertura, fechamento):
    """Recorta o elemento que guarda a edicao.

    Afirmar sobre a pagina inteira encontraria "None" em qualquer classe de CSS ou
    trecho de script que viesse a conter a palavra, e o teste passaria a reprovar
    por motivo nenhum. O recorte tambem e o que faz a assercao ser sobre ESTE
    lugar, e nao sobre o acaso de a palavra nao existir na pagina.
    """
    inicio = html.index(abertura)
    return html[inicio : html.index(fechamento, inicio)]


# --- a criacao ----------------------------------------------------------------


@pytest.mark.django_db
def test_o_professor_cria_proposta_pela_tela_sem_edicao_aberta(client, sem_edicao, professor):
    """Pelo POST da tela, e nao so pelo servico: era a tela que devolvia a
    mensagem de recusa ao professor."""
    client.force_login(professor)
    resposta = client.post(reverse("nova_proposta"), {"titulo": "Robótica com sucata"})

    assert resposta.status_code == 302
    curso = professor.cursos_como_responsavel.get()
    assert resposta.url == reverse("equipe", args=[curso.pk])


@pytest.mark.django_db
def test_a_tela_de_proposta_nao_fala_mais_em_edicao_fechada(client, sem_edicao, professor):
    client.force_login(professor)
    html = client.post(
        reverse("nova_proposta"), {"titulo": "Robótica com sucata"}, follow=True
    ).content.decode()

    assert "edição da disciplina" not in html


# --- o "None" nas telas -------------------------------------------------------


@pytest.mark.django_db
def test_a_fila_da_coordenacao_nao_imprime_none_no_lugar_da_edicao(
    client, curso_completo_sem_edicao, professor, coordenador, aluno
):
    """`_curso_na_lista.html` interpolava `{{ curso.edicao }}` direto, e o Django
    renderiza `None` como o texto "None"."""
    ate_a_coordenacao(curso_completo_sem_edicao, professor, aluno)

    client.force_login(coordenador)
    html = client.get(reverse("fila_coordenacao")).content.decode()

    assert curso_completo_sem_edicao.titulo in html, "o curso nem apareceu na fila"
    detalhe = so_o_trecho(html, '<p class="detalhe">', "</p>")
    assert "None" not in detalhe, detalhe
    # O que TEM que continuar na linha: sem isto, apagar o bloco inteiro passaria.
    assert professor.nome_completo in detalhe


@pytest.mark.django_db
def test_a_pagina_publica_nao_imprime_none_no_lugar_da_edicao(
    client, curso_completo_sem_edicao, professor, coordenador, aluno
):
    """A pagina publica dizia "Versão 1 &middot; {{ curso.edicao }}", e o visitante
    leria "Versão 1 · None"."""
    ate_a_coordenacao(curso_completo_sem_edicao, professor, aluno)
    services.publicar_curso(curso_completo_sem_edicao, por=coordenador)

    html = client.get(
        reverse("catalogo_curso", args=[curso_completo_sem_edicao.pk])
    ).content.decode()

    fatos = so_o_trecho(html, '<div class="fatos">', "</div>")
    assert "None" not in fatos, fatos
    # A versao nao pode ter ido embora junto com a edicao.
    assert "Versão 1" in fatos


# --- o outro lado: havendo edicao, o rotulo continua aparecendo ---------------


@pytest.mark.django_db
def test_havendo_edicao_corrente_a_proposta_nasce_com_ela(edicao, professor):
    """A metade que nao pode ter sido perdida no caminho: o rotulo continua sendo
    gravado quando existe o que gravar."""
    curso = services.criar_curso(titulo="Robótica com sucata", professor_responsavel=professor)

    assert curso.edicao == edicao
