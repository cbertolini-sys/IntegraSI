"""A tela de Pessoas: quem ela lista e o que ela oferece.

Listava so professores e coordenacao, e o aluno nao aparecia em lugar nenhum
fora da equipe de um curso. Como a coordenacao passou a poder excluir pessoas, e
a regra vale igual para aluno, ele precisa ter porta.
"""

import pytest
from django.urls import reverse

from apps.contas import services
from apps.contas.models import Usuario


def corpo(client):
    return client.get(reverse("pessoas")).content.decode()


@pytest.mark.django_db
def test_a_tela_lista_alunos_tambem(client, coordenador, professor, aluno):
    client.force_login(coordenador)
    html = corpo(client)

    assert aluno.nome_completo in html
    assert professor.nome_completo in html


@pytest.mark.django_db
def test_cada_pessoa_tem_o_botao_de_excluir(client, coordenador, aluno):
    client.force_login(coordenador)

    assert 'value="EXCLUIR"' in corpo(client)


@pytest.mark.django_db
def test_o_coordenador_nao_ve_o_botao_de_excluir_para_si(client, coordenador):
    """A guarda do servico ja recusa, mas oferecer o botao seria oferecer um erro:
    a pessoa clica, leva a recusa e nao entende por que o botao existia."""
    client.force_login(coordenador)
    html = corpo(client)
    inicio = html.index(coordenador.nome_completo)
    linha = html[inicio : html.index("</li>", inicio)]

    assert 'value="EXCLUIR"' not in linha, linha


@pytest.mark.django_db
def test_excluir_pela_tela_apaga_quem_nao_tem_rastro(client, coordenador, aluno):
    client.force_login(coordenador)

    client.post(reverse("pessoas"), {"usuario": aluno.pk, "acao": "EXCLUIR"}, follow=True)

    assert not Usuario.objects.filter(pk=aluno.pk).exists()


@pytest.mark.django_db
def test_a_tela_diz_quando_desativou_em_vez_de_apagar(client, coordenador, professor, aluno):
    """A mensagem e o produto: sem ela a pessoa clica em "Excluir", a conta
    continua na lista, e ela conclui que o botao nao funcionou."""
    from apps.cursos import services as cursos

    curso = cursos.criar_curso(titulo="Curso qualquer", professor_responsavel=professor)
    cursos.adicionar_membro(curso, aluno, por=professor)
    client.force_login(coordenador)

    resposta = client.post(
        reverse("pessoas"), {"usuario": aluno.pk, "acao": "EXCLUIR"}, follow=True
    )
    aviso = " ".join(str(m) for m in resposta.context["messages"])

    assert aluno.nome_completo in aviso
    assert "desativ" in aviso.lower(), aviso
    assert "equipe" in aviso.lower(), aviso


@pytest.mark.django_db
def test_o_desativado_mostra_o_botao_de_reativar(client, coordenador, aluno, professor):
    from apps.cursos import services as cursos

    curso = cursos.criar_curso(titulo="Curso qualquer", professor_responsavel=professor)
    cursos.adicionar_membro(curso, aluno, por=professor)
    services.excluir_pessoa(aluno, por=coordenador)

    client.force_login(coordenador)
    html = corpo(client)
    inicio = html.index(aluno.nome_completo)
    linha = html[inicio : html.index("</li>", inicio)]

    assert 'value="REATIVAR"' in linha, linha
    assert "Desativado" in linha


@pytest.mark.django_db
def test_reativar_pela_tela(client, coordenador, aluno, professor):
    from apps.cursos import services as cursos

    curso = cursos.criar_curso(titulo="Curso qualquer", professor_responsavel=professor)
    cursos.adicionar_membro(curso, aluno, por=professor)
    services.excluir_pessoa(aluno, por=coordenador)

    client.force_login(coordenador)
    client.post(reverse("pessoas"), {"usuario": aluno.pk, "acao": "REATIVAR"}, follow=True)
    aluno.refresh_from_db()

    assert aluno.is_active is True
