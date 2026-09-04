# O catalogo monta cenarios de curso publicado nos seus testes, e cursos ja e uma
# dependencia de producao do catalogo (spec: dependencia de mao unica). As
# fixtures de usuario, edicao e dados de curso moram em apps/cursos/tests/conftest.py
# porque cursos foi o primeiro app a precisa-las; reimporta-las aqui evita
# duplicar as definicoes sem criar um conftest global (que colidiria com a
# descoberta automatica do conftest de cursos ao rodar a suite inteira).
from apps.cursos.tests.conftest import (  # noqa: F401
    aluno,
    coordenador,
    dados_curso,
    media_root_isolado,
    outro_aluno,
    professor,
)
