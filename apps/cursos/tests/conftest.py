import datetime

import pytest

from apps.contas.models import Usuario
from apps.cursos.choices import Formato, TipoPublico
from apps.cursos.models import Curso
from apps.edicoes.models import Edicao


@pytest.fixture
def coordenador(db):
    return Usuario.objects.create_user(
        email="coord@ufsm.br", nome_completo="Carla Costa",
        cpf="529.982.247-25", papel=Usuario.COORDENADOR, siape="7654321",
        password="senha-de-teste-123",
    )


@pytest.fixture
def professor(db):
    return Usuario.objects.create_user(
        email="prof@ufsm.br", nome_completo="Bruno Barros",
        cpf="123.456.789-09", papel=Usuario.PROFESSOR, siape="1234567",
        password="senha-de-teste-123",
    )


@pytest.fixture
def aluno(db):
    return Usuario.objects.create_user(
        email="aluno@ufsm.br", nome_completo="Ana Alves",
        cpf="987.654.321-00", papel=Usuario.ALUNO, matricula="201910101",
        password="senha-de-teste-123",
    )


@pytest.fixture
def outro_aluno(db):
    return Usuario.objects.create_user(
        email="outro@ufsm.br", nome_completo="Davi Dias",
        cpf="111.444.777-35", papel=Usuario.ALUNO, matricula="201910202",
        password="senha-de-teste-123",
    )


@pytest.fixture
def edicao(db):
    return Edicao.objects.create(
        codigo="2026/2", descricao="TICs para Inclusao Digital",
        data_inicio=datetime.date(2026, 8, 1), data_fim=datetime.date(2026, 12, 20),
        ativa=True,
    )


@pytest.fixture
def dados_curso(edicao, professor):
    return {
        "titulo": "Pensamento Computacional Desplugado",
        "resumo": "Oficina de logica sem telas para o 5o ano.",
        "edicao": edicao,
        "professor_responsavel": professor,
        "tipo_publico": TipoPublico.ESCOLAR,
        "etapa_ano": "EF05",
        "carga_horaria": 12,
        "formato": Formato.PRESENCIAL,
    }


@pytest.fixture
def curso(dados_curso):
    return Curso.objects.create(**dados_curso)
