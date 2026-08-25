import pytest
from django.core.exceptions import ValidationError

from apps.contas.models import Usuario

CPF_A = "529.982.247-25"
CPF_B = "123.456.789-09"


def criar_aluno(**kwargs):
    dados = {
        "email": "aluno@ufsm.br",
        "nome_completo": "Ana Alves",
        "cpf": CPF_A,
        "papel": Usuario.ALUNO,
        "matricula": "201910101",
    }
    dados.update(kwargs)
    return Usuario.objects.create_user(**dados)


def criar_professor(**kwargs):
    dados = {
        "email": "prof@ufsm.br",
        "nome_completo": "Bruno Barros",
        "cpf": CPF_B,
        "papel": Usuario.PROFESSOR,
        "siape": "1234567",
    }
    dados.update(kwargs)
    return Usuario.objects.create_user(**dados)


@pytest.mark.django_db
def test_documentos_sao_gravados_somente_com_digitos():
    aluno = criar_aluno(matricula="2019.10101")
    aluno.refresh_from_db()
    assert aluno.cpf == "52998224725"
    assert aluno.matricula == "201910101"


@pytest.mark.django_db
def test_cpf_invalido_e_recusado():
    with pytest.raises(ValidationError):
        criar_aluno(cpf="529.982.247-24")


@pytest.mark.django_db
def test_aluno_sem_matricula_e_recusado():
    with pytest.raises(ValidationError):
        criar_aluno(matricula="")


@pytest.mark.django_db
def test_professor_sem_siape_e_recusado():
    with pytest.raises(ValidationError):
        criar_professor(siape="")


@pytest.mark.django_db
def test_aluno_nao_pode_ter_siape():
    with pytest.raises(ValidationError):
        criar_aluno(siape="1234567")


@pytest.mark.django_db
def test_professor_nao_pode_ter_matricula():
    with pytest.raises(ValidationError):
        criar_professor(matricula="201910101")


@pytest.mark.django_db
def test_mesmo_cpf_escrito_de_duas_formas_colide():
    criar_aluno()
    with pytest.raises(ValidationError):
        criar_professor(cpf="52998224725")


@pytest.mark.django_db
def test_email_duplicado_e_recusado():
    criar_aluno()
    with pytest.raises(ValidationError):
        criar_professor(email="aluno@ufsm.br")


@pytest.mark.django_db
def test_propriedades_de_papel():
    aluno = criar_aluno()
    professor = criar_professor()
    assert aluno.e_aluno and not aluno.e_professor and not aluno.e_coordenador
    assert professor.e_professor and not professor.e_aluno


@pytest.mark.django_db
def test_str_mostra_nome_e_nunca_o_cpf():
    aluno = criar_aluno()
    assert str(aluno) == "Ana Alves"
    assert "529" not in str(aluno)
