# As fixtures de usuario moram em `apps/contas/tests/conftest.py`, o app base.
# Reimportar aqui evita duplicar as definicoes sem criar um conftest global, que
# colidiria com a descoberta automatica dos conftests de cada app - o mesmo
# arranjo que `apps/catalogo/tests/conftest.py` usa.
from apps.contas.tests.conftest import (  # noqa: F401
    aluno,
    coordenador,
    professor,
)
