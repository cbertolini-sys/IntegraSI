import pytest
from django.core.exceptions import ValidationError

from apps.contas.models import Usuario


@pytest.mark.django_db
def test_aluno_nasce_sem_documento_e_com_perfil_incompleto():
    """Regra 2: o professor aloca informando só nome e e-mail. CPF, matrícula e
    telefone chegam no primeiro acesso."""
    aluno = Usuario.objects.create_user(
        email="novo@acad.ufsm.br", nome_completo="Novo Aluno",
        cpf=None, papel=Usuario.ALUNO, password=None,
    )
    assert aluno.cpf is None
    assert aluno.matricula is None
    assert aluno.perfil_completo is False


@pytest.mark.django_db
def test_perfil_fica_completo_com_os_tres_campos(aluno):
    aluno.cpf = None
    aluno.matricula = None
    aluno.save()
    assert aluno.perfil_completo is False
    aluno.cpf = "987.654.321-00"
    aluno.matricula = "201910101"
    aluno.telefone = "(55) 99999-1234"
    aluno.save()
    assert aluno.perfil_completo is True


@pytest.mark.django_db
@pytest.mark.parametrize("faltando", ["cpf", "matricula", "telefone"])
def test_falta_de_qualquer_um_deixa_o_perfil_incompleto(aluno, faltando):
    """Três testes, não um: apagar a checagem de um campo sozinho tem de derrubar
    exatamente a sua parametrização."""
    dados = {"cpf": "987.654.321-00", "matricula": "201910101", "telefone": "(55) 99999-1234"}
    dados[faltando] = "" if faltando == "telefone" else None
    for campo, valor in dados.items():
        setattr(aluno, campo, valor)
    assert aluno.perfil_completo is False


@pytest.mark.django_db
def test_professor_nasce_com_perfil_completo(professor):
    """Professor e coordenador são criados pela coordenação com documento na mão.
    O telefone não entra na conta deles: quem passa pelo primeiro acesso é o
    aluno, e é lá que o telefone é pedido."""
    assert professor.perfil_completo is True


@pytest.mark.django_db
def test_identificacao_e_o_nome_quando_ha_nome(professor):
    assert professor.identificacao == "Bruno Barros"


@pytest.mark.django_db
def test_identificacao_cai_no_email_sem_nome():
    """A coordenação cadastra professor só com o e-mail; `nome_completo` fica
    vazio até o primeiro acesso. Uma mensagem ou um <option> que interpola
    `nome_completo` direto, sem isto, imprime uma string vazia - sem sujeito na
    frase, ou uma opção de select selecionável e invisível."""
    sem_nome = Usuario.objects.create_user(
        email="semnome@ufsm.br", nome_completo="", papel=Usuario.PROFESSOR, password=None
    )
    assert sem_nome.identificacao == "semnome@ufsm.br"


@pytest.mark.django_db
def test_dois_alunos_sem_cpf_convivem():
    """`cpf` continua único. Nulo não colide com nulo no Postgres, e é o que
    permite alocar dois alunos antes de qualquer um deles completar o perfil."""
    for i in (1, 2):
        Usuario.objects.create_user(
            email=f"aluno{i}@acad.ufsm.br", nome_completo=f"Aluno {i}",
            cpf=None, papel=Usuario.ALUNO, password=None,
        )
    assert Usuario.objects.filter(cpf__isnull=True).count() == 2


@pytest.mark.django_db
def test_cpf_repetido_continua_recusado(aluno):
    with pytest.raises(ValidationError):
        Usuario.objects.create_user(
            email="clone@acad.ufsm.br", nome_completo="Clone",
            cpf="987.654.321-00", papel=Usuario.ALUNO,
            matricula="202020202", password=None,
        )


@pytest.mark.django_db
def test_professor_nasce_sem_documento_e_sem_nome():
    """A coordenação cadastra professor só com o e-mail, e ele completa o resto no
    primeiro acesso. Antes o modelo exigia CPF e SIAPE já no cadastro, o que
    tornava esse fluxo impossível.

    Quem exige os três campos é a tela do convite, e não o modelo. O que o modelo
    guarda é o perfil ficar marcado como incompleto enquanto faltar."""
    professor = Usuario.objects.create_user(
        email="soemail@ufsm.br", nome_completo="", cpf=None,
        papel=Usuario.PROFESSOR, password=None,
    )
    assert professor.perfil_completo is False


@pytest.mark.django_db
def test_professor_com_cpf_precisa_de_siape():
    """Coerência, e não obrigatoriedade: metade da identificação funcional gravada
    é pior que nenhuma, porque a tela de cadastro pendente não a distingue de uma
    ficha pronta."""
    with pytest.raises(ValidationError):
        Usuario.objects.create_user(
            email="semsiape@ufsm.br", nome_completo="Sem Siape",
            cpf="071.620.218-24", papel=Usuario.PROFESSOR, password=None,
        )


@pytest.mark.django_db
def test_professor_com_nome_e_cpf_ainda_e_incompleto_sem_nome():
    """`perfil_completo` passou a cobrar o nome dos dois papéis, porque agora ele
    pode nascer vazio. Sem isso o professor cadastrado por e-mail entraria no
    sistema sem nome e o middleware o deixaria passar."""
    professor = Usuario.objects.create_user(
        email="anonimo@ufsm.br", nome_completo="", cpf="071.620.218-24",
        papel=Usuario.PROFESSOR, siape="5555555", password=None,
    )
    assert professor.perfil_completo is False


@pytest.mark.django_db
def test_aluno_com_cpf_precisa_de_matricula():
    """Coerência: meio-preenchido não passa. Quem exige os três campos é a tela de
    primeiro acesso; o modelo garante que CPF e matrícula andem juntos."""
    with pytest.raises(ValidationError):
        Usuario.objects.create_user(
            email="meio@acad.ufsm.br", nome_completo="Meio Preenchido",
            cpf="071.620.218-24", papel=Usuario.ALUNO, password=None,
        )
