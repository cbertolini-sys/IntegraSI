"""Fixtures de usuário para os testes de `contas`.

Definidas aqui, e não reimportadas de `apps/cursos/tests/conftest.py` como faz o
catálogo: `contas` é o app base, e a dependência do projeto é de mão única --
`cursos` conhece `contas`, nunca o contrário (CLAUDE.md, Arquitetura). Fazer os
testes deste app importarem de `cursos` inverteria isso no lugar mais fácil de
não perceber.

Os CPFs são os mesmos das fixtures de `cursos`, de propósito: um cenário que
misture os dois conjuntos não colide.
"""

import pytest

from apps.contas.models import Usuario


@pytest.fixture
def coordenador(db):
    return Usuario.objects.create_user(
        email="coord@ufsm.br", nome_completo="Carla Costa",
        cpf="529.982.247-25", papel=Usuario.COORDENADOR, siape="7654321",
        password="senha-de-teste-123",
    )


@pytest.fixture
def outro_coordenador(db):
    return Usuario.objects.create_user(
        email="coord2@ufsm.br", nome_completo="Rita Rocha",
        cpf="071.620.218-24", papel=Usuario.COORDENADOR, siape="8888888",
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
def outro_professor(db):
    return Usuario.objects.create_user(
        email="outro.prof@ufsm.br", nome_completo="Elisa Esteves",
        cpf="111.444.777-35", papel=Usuario.PROFESSOR, siape="9999999",
        password="senha-de-teste-123",
    )


@pytest.fixture
def aluno(db):
    return Usuario.objects.create_user(
        email="aluno@ufsm.br", nome_completo="Ana Alves",
        cpf="987.654.321-00", papel=Usuario.ALUNO, matricula="201910101",
        password="senha-de-teste-123",
    )
