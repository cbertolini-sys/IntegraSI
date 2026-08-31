import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.contas.models import ConviteAluno, Usuario
from apps.cursos import services
from apps.cursos.choices import StatusCurso
from apps.notificacoes.models import Notificacao


@pytest.mark.django_db
def test_alocar_cria_a_conta_com_nome_e_email(curso, professor):
    """Regra 2: a alocação informa só nome e e-mail."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor
    )
    assert membro.pessoa.nome_completo == "Joana Silva"
    assert membro.pessoa.papel == Usuario.ALUNO
    assert membro.pessoa.cpf is None
    assert membro.pessoa.perfil_completo is False


@pytest.mark.django_db
def test_alocar_convida_o_aluno(curso, professor):
    services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor)
    assert ConviteAluno.objects.filter(usuario__email="joana@acad.ufsm.br").count() == 1
    assert (
        Notificacao.objects.filter(
            evento="CONVITE_ALUNO", destinatario="joana@acad.ufsm.br"
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_a_conta_nasce_sem_senha_utilizavel(curso, professor):
    """Só o convite dá acesso: uma senha vazia que autenticasse seria uma porta
    aberta em toda conta ainda não usada."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor
    )
    assert membro.pessoa.has_usable_password() is False


@pytest.mark.django_db
def test_email_ja_cadastrado_e_recusado(curso, professor, aluno):
    """Decisão do coordenador: recusa em vez de vincular a conta existente.
    Vincular em silêncio poria alguém numa equipe por um e-mail digitado errado."""
    with pytest.raises(ValidationError) as erro:
        services.alocar_aluno(curso, nome="Outro Nome", email=aluno.email, por=professor)
    # Afirma a MENSAGEM, e nao so o tipo: o indice unico do modelo recusaria este
    # mesmo caso sozinho, e um `pytest.raises(ValidationError)` pelado passaria com
    # a checagem do servico apagada (conferido por mutacao). O que o servico
    # acrescenta e dizer ao professor o que fazer a seguir.
    assert "Confira o endereço" in " ".join(erro.value.messages)


@pytest.mark.django_db
def test_email_ja_cadastrado_e_recusado_ignorando_maiusculas(curso, professor, aluno):
    """A recusa não pode depender de como a pessoa digitou: `Aluno@UFSM.br` é a
    mesma conta."""
    with pytest.raises(ValidationError):
        services.alocar_aluno(
            curso, nome="Outro Nome", email=aluno.email.upper(), por=professor
        )


@pytest.mark.django_db
def test_email_recusado_nao_deixa_conta_nem_convite(curso, professor, aluno):
    antes = Usuario.objects.count()
    with pytest.raises(ValidationError):
        services.alocar_aluno(curso, nome="Outro Nome", email=aluno.email, por=professor)
    assert Usuario.objects.count() == antes
    assert ConviteAluno.objects.count() == 0


@pytest.mark.django_db
def test_qualquer_dominio_de_email_e_aceito(curso, professor):
    """Decisão do coordenador: sem lista branca de domínio -- há aluno de
    intercâmbio e conta pessoal, e restringir travaria o professor."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@gmail.com", por=professor
    )
    assert membro.pessoa.email == "joana@gmail.com"


@pytest.mark.django_db
def test_alocar_tira_o_curso_do_rascunho(curso, professor):
    assert curso.status == StatusCurso.RASCUNHO
    services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO


@pytest.mark.django_db
def test_aluno_nao_aloca(curso, aluno):
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=aluno)


@pytest.mark.django_db
def test_professor_de_outro_curso_nao_aloca(curso, outro_professor):
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(
            curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=outro_professor
        )


@pytest.mark.django_db
def test_permissao_recusada_nao_deixa_conta(curso, outro_professor):
    """A guarda vem antes de qualquer escrita: sem isso, um professor de fora
    criaria a conta e só depois seria barrado."""
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(
            curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=outro_professor
        )
    assert Usuario.objects.filter(email="joana@acad.ufsm.br").exists() is False


@pytest.mark.django_db
def test_alocacao_e_atomica_quando_o_convite_falha(curso, professor, monkeypatch):
    """A conta, o vínculo e o convite nascem juntos ou não nascem.

    Sem a transação, um erro no envio deixaria uma conta órfã que ninguém ativa e
    que queima o e-mail para sempre: a segunda tentativa bateria na recusa de
    e-mail já cadastrado, e só a coordenação destravaria pelo Admin.

    O patch é na origem (`apps.contas.services.convidar`), e não no nome
    importado: `alocar_aluno` importa a função dentro do corpo, para não fechar
    ciclo entre `cursos` e `contas`.
    """

    def explode(*args, **kwargs):
        raise RuntimeError("fila fora do ar")

    monkeypatch.setattr("apps.contas.services.convidar", explode)
    with pytest.raises(RuntimeError):
        services.alocar_aluno(
            curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor
        )
    monkeypatch.undo()
    assert Usuario.objects.filter(email="joana@acad.ufsm.br").exists() is False
    assert curso.membros.count() == 0


@pytest.mark.django_db
def test_coordenador_tambem_aloca(curso, coordenador):
    """Regra 1 encontra a regra 2: o coordenador é professor e gere qualquer
    equipe."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=coordenador
    )
    assert membro.pessoa.email == "joana@acad.ufsm.br"


@pytest.mark.django_db
@pytest.mark.parametrize("faltando", ["nome", "email"])
def test_nome_ou_email_em_branco_e_recusado(curso, professor, faltando):
    """Recusa explicita, e nao `ValueError` vindo do `create_user`: a view so
    captura `ValidationError`, e um POST incompleto viraria 500. Dois casos, para
    que apagar uma das duas checagens derrube exatamente a sua parametrizacao."""
    dados = {"nome": "Joana Silva", "email": "joana@acad.ufsm.br"}
    dados[faltando] = "   "
    with pytest.raises(ValidationError):
        services.alocar_aluno(curso, por=professor, **dados)
    assert Usuario.objects.filter(email="joana@acad.ufsm.br").exists() is False
