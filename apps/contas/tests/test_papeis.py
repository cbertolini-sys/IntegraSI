import pytest

from apps.contas.models import Usuario


@pytest.mark.django_db
def test_coordenador_tambem_e_professor(coordenador):
    """Regra 1: todo coordenador é, inerentemente, um professor -- com nível de
    acesso Admin por cima. É o que permite a ele criar curso e conduzir turma sem
    uma segunda conta."""
    assert coordenador.e_coordenador is True
    assert coordenador.e_professor is True
    assert coordenador.e_aluno is False


@pytest.mark.django_db
def test_professor_nao_e_coordenador(professor):
    assert professor.e_professor is True
    assert professor.e_coordenador is False


@pytest.mark.django_db
def test_aluno_nao_herda_nada(aluno):
    assert aluno.e_aluno is True
    assert aluno.e_professor is False
    assert aluno.e_coordenador is False


@pytest.mark.django_db
def test_somente_professor_distingue_quem_nao_e_coordenador(professor, coordenador):
    """A herança apaga a distinção em `e_professor`. Onde a regra for mesmo "é
    professor e NÃO é coordenador", existe esta propriedade -- para que ninguém
    reescreva `papel == PROFESSOR` espalhado pelo código."""
    assert professor.e_somente_professor is True
    assert coordenador.e_somente_professor is False


@pytest.mark.django_db
def test_papel_continua_sendo_um_so_valor(coordenador):
    """A herança é de comportamento, não de armazenamento: `papel` segue com um
    valor por pessoa, e o coordenador é COORDENADOR no banco."""
    assert coordenador.papel == Usuario.COORDENADOR
