# turmas consome cursos (dependência de mão única: turmas lê cursos, cursos não
# conhece turmas). As fixtures de usuário, edição e dados de curso moram em
# apps/cursos/tests/conftest.py porque cursos foi o primeiro app a precisá-las;
# reimportá-las aqui evita duplicar as definições, do mesmo jeito que
# apps/catalogo/tests/conftest.py já faz.
from apps.cursos.tests.conftest import (  # noqa: F401
    aluno,
    coordenador,
    dados_curso,
    edicao,
    media_root_isolado,
    outro_aluno,
    outro_professor,
    professor,
)
