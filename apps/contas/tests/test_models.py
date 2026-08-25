import pytest
from django.core.exceptions import ValidationError

from apps.contas.models import Usuario

CPF_A = "529.982.247-25"
CPF_B = "123.456.789-09"
CPF_C = "111.444.777-35"


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


@pytest.mark.django_db
def test_dois_usuarios_sem_matricula_coexistem():
    # matricula e siape sao unique=True, null=True: duas linhas com NULL convivem no
    # Postgres, mas duas com "" colidiriam (CharField default e "", nao None). Isto prova
    # que o "or None" da normalizacao em full_clean() esta de fato em vigor.
    criar_professor()
    criar_professor(
        email="coord@ufsm.br",
        nome_completo="Carla Costa",
        cpf=CPF_C,
        papel=Usuario.COORDENADOR,
        siape="7654321",
    )
    assert Usuario.objects.count() == 2


@pytest.mark.django_db
def test_create_superuser_com_siape_via_extra_cria_coordenador():
    # Task 4's criar_coordenador management command calls create_superuser exactly assim,
    # com siape chegando por **extra. Se o pass-through quebrar, e aqui que aparece.
    coordenador = Usuario.objects.create_superuser(
        email="raiz@ufsm.br",
        nome_completo="Root Reitor",
        cpf=CPF_C,
        siape="9876543",
        password="uma-senha-forte",
    )
    coordenador.refresh_from_db()
    assert coordenador.papel == Usuario.COORDENADOR
    assert coordenador.is_staff is True
    assert coordenador.is_superuser is True
    assert coordenador.siape == "9876543"
