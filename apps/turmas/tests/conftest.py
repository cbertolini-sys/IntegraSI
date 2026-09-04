# turmas consome cursos (dependência de mão única: turmas lê cursos, cursos não
# conhece turmas). As fixtures de usuário, edição e dados de curso moram em
# apps/cursos/tests/conftest.py porque cursos foi o primeiro app a precisá-las;
# reimportá-las aqui evita duplicar as definições, do mesmo jeito que
# apps/catalogo/tests/conftest.py já faz.
import pytest

from apps.catalogo.models import Solicitacao
from apps.cursos import services as servicos_curso
from apps.cursos.choices import StatusEntregavel
from apps.cursos.tests.conftest import (  # noqa: F401
    aluno,
    coordenador,
    dados_curso,
    media_root_isolado,
    outro_aluno,
    outro_professor,
    professor,
)


@pytest.fixture
def curso_publicado(dados_curso, outro_aluno, professor, coordenador):
    # adicionar_membro tira o curso de RASCUNHO para EM_PRODUCAO; sem isso
    # submeter_ao_coordenador recusa por status, não pelos entregáveis (mesma
    # lacuna já documentada nos conftests de catalogo).
    curso = servicos_curso.criar_curso(**dados_curso)
    servicos_curso.adicionar_membro(curso, outro_aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    servicos_curso.submeter_ao_coordenador(curso, por=professor)
    servicos_curso.publicar_curso(curso, por=coordenador)
    return curso


@pytest.fixture
def solicitacao(curso_publicado):
    return Solicitacao.objects.create(
        curso=curso_publicado, nome="Escola São José", email="direcao@escola.exemplo.br",
        num_participantes=25, instituicao="EMEF São José",
    )
