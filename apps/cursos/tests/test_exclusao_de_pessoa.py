"""A coordenacao exclui pessoas, e o sistema decide se da para apagar de verdade.

Mora em `apps/cursos/tests/` porque os cenarios precisam de curso, e as fixtures
de curso vivem aqui. O SERVICO mora em `contas.services`, que e onde a
administracao de pessoas ja acontece.

A regra pedida foi "se aparece em algum curso como equipe ou responsavel,
desativa". Ao implementar apareceu que isso e mais estreito do que precisa ser:
OITO relacoes apontam para `Usuario` com PROTECT, e duas delas sao equipe e
responsavel. Alguem que nunca entrou numa equipe pode ter revisado um entregavel
ou movido um curso no fluxo, e apagar essa pessoa estouraria `ProtectedError` -
um 500 na cara do coordenador.

Por isso a regra le as relacoes DO PROPRIO MODELO, em vez de conferir uma lista
de nomes. Um modelo novo que aponte para `Usuario` com PROTECT entra na conta
sozinho, e ninguem precisa lembrar de vir aqui.
"""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.contas import services as contas
from apps.contas.models import Usuario
from apps.cursos import services
from apps.cursos.models import MembroEquipe


@pytest.fixture
def sem_rastro(db):
    """Uma conta que nunca produziu nada: nasce e some sem deixar buraco."""
    return Usuario.objects.create_user(
        email="passou.por.aqui@ufsm.br", nome_completo="Rita Nunes",
        cpf="168.995.350-09", papel=Usuario.PROFESSOR, siape="3000001",
        password="senha-de-teste-123",
    )


@pytest.fixture
def segundo_coordenador(db):
    """Existe aqui, e nao no conftest: so estes testes precisam de DOIS
    coordenadores, e a fixture de `contas` nao alcanca este pacote."""
    return Usuario.objects.create_user(
        email="segunda.coordenacao@ufsm.br", nome_completo="Beto Assis",
        cpf="264.502.270-79", papel=Usuario.COORDENADOR, siape="3000002",
        password="senha-de-teste-123",
    )


# --- apagar de verdade --------------------------------------------------------


@pytest.mark.django_db
def test_pessoa_sem_rastro_e_apagada(sem_rastro, coordenador):
    resultado = contas.excluir_pessoa(sem_rastro, por=coordenador)

    assert resultado.apagada is True
    assert not Usuario.objects.filter(email="passou.por.aqui@ufsm.br").exists()


# --- desativar, e dizer por que -----------------------------------------------


@pytest.mark.django_db
def test_quem_esta_numa_equipe_e_desativado(dados_curso, professor, aluno, coordenador):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)

    resultado = contas.excluir_pessoa(aluno, por=coordenador)
    aluno.refresh_from_db()

    assert resultado.apagada is False
    assert aluno.is_active is False
    assert Usuario.objects.filter(pk=aluno.pk).exists(), "a conta sumiu em vez de ser desativada"


@pytest.mark.django_db
def test_quem_so_revisou_tambem_e_desativado(dados_curso, professor, aluno, coordenador):
    """O caso que a regra literal ("equipe ou responsável") deixaria passar.

    O `outro_professor` nao entra em equipe nenhuma: ele so revisa. Sem ler as
    relacoes do modelo, o sistema tentaria apagar e estouraria ProtectedError por
    causa de `Revisao.revisor`.
    """
    from apps.cursos.choices import StatusEntregavel
    from apps.cursos.models import Entregavel, Revisao

    curso = services.criar_curso(**dados_curso)
    entregavel = curso.entregaveis.first()
    revisor = Usuario.objects.create_user(
        email="so.revisa@ufsm.br", nome_completo="Ana Só Revisa",
        cpf="285.842.760-76", papel=Usuario.PROFESSOR, siape="3000003",
        password="senha-de-teste-123",
    )
    Revisao.objects.create(entregavel=entregavel, revisor=revisor, decisao=Revisao.APROVADO)
    assert not MembroEquipe.objects.filter(pessoa=revisor).exists()

    resultado = contas.excluir_pessoa(revisor, por=coordenador)
    revisor.refresh_from_db()

    assert resultado.apagada is False
    assert revisor.is_active is False


@pytest.mark.django_db
def test_a_recusa_diz_o_que_prende_a_pessoa(dados_curso, professor, aluno, coordenador):
    """"Não é possível excluir" não ajuda ninguém. Quem lê precisa saber o que
    aquela conta produziu, para decidir se desativar basta."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)

    resultado = contas.excluir_pessoa(aluno, por=coordenador)

    assert resultado.motivos, "desativou sem dizer por quê"
    texto = " ".join(resultado.motivos).lower()
    assert "equipe" in texto, texto


# --- as duas recusas ----------------------------------------------------------


@pytest.mark.django_db
def test_ninguem_se_exclui(coordenador):
    """Mesma razão do rebaixamento: o Admin não tem como recusar, e uma
    coordenação que se apaga deixa o sistema sem quem publique curso."""
    with pytest.raises(ValidationError):
        contas.excluir_pessoa(coordenador, por=coordenador)


@pytest.mark.django_db
def test_o_ultimo_coordenador_nao_sai(coordenador, segundo_coordenador):
    """Com dois, um sai. Com um, ninguém sai: sem coordenação não há quem publique
    curso, aceite solicitação ou promova alguém de volta."""
    contas.excluir_pessoa(segundo_coordenador, por=coordenador)

    sozinho = Usuario.objects.filter(papel=Usuario.COORDENADOR, is_active=True)
    assert sozinho.count() == 1

    with pytest.raises(ValidationError) as erro:
        contas.excluir_pessoa(coordenador, por=segundo_coordenador)
    assert "última coordenação ativa" in str(erro.value)


@pytest.mark.django_db
def test_professor_nao_exclui_ninguem(sem_rastro, professor):
    with pytest.raises(PermissionDenied):
        contas.excluir_pessoa(sem_rastro, por=professor)


# --- a volta ------------------------------------------------------------------


@pytest.mark.django_db
def test_reativar_devolve_o_acesso(dados_curso, professor, aluno, coordenador):
    """Sem volta, um clique errado é permanente."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    contas.excluir_pessoa(aluno, por=coordenador)

    contas.reativar_pessoa(aluno, por=coordenador)
    aluno.refresh_from_db()

    assert aluno.is_active is True


@pytest.mark.django_db
def test_professor_nao_reativa(aluno, professor, coordenador):
    contas.excluir_pessoa(aluno, por=coordenador)
    with pytest.raises(PermissionDenied):
        contas.reativar_pessoa(aluno, por=professor)


# --- o que a desativacao NAO faz ----------------------------------------------


@pytest.mark.django_db
def test_o_aluno_desativado_continua_na_equipe(dados_curso, professor, aluno, coordenador):
    """Decisão sua, e é a certa: a equipe é o registro de quem produziu o curso.
    Tirar o nome de lá reescreveria a autoria."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)

    contas.excluir_pessoa(aluno, por=coordenador)

    assert MembroEquipe.objects.filter(curso=curso, pessoa=aluno).exists()


@pytest.mark.django_db
def test_o_desativado_some_das_listas_de_alocacao(dados_curso, professor, aluno, coordenador):
    """Continuar na equipe do curso em que produziu é uma coisa; continuar
    disponível para entrar em cursos novos é outra."""
    from apps.cursos.views.professor import _alunos_disponiveis

    outro = services.criar_curso(**dict(dados_curso, titulo="Outro curso"))
    assert aluno in _alunos_disponiveis(outro)

    contas.excluir_pessoa(aluno, por=coordenador)

    assert aluno not in _alunos_disponiveis(outro)
