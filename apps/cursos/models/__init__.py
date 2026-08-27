from apps.cursos.models.anexo import Anexo, Arquivo
from apps.cursos.models.curso import Curso
from apps.cursos.models.equipe import MembroEquipe
from apps.cursos.models.historico import LogTransicaoCurso
from apps.cursos.models.producao import Entregavel, Secao
from apps.cursos.models.revisao import Revisao
from apps.cursos.models.tema import Tema
from apps.cursos.models.upload import UploadEmAndamento

__all__ = [
    "Anexo",
    "Arquivo",
    "Curso",
    "Entregavel",
    "LogTransicaoCurso",
    "MembroEquipe",
    "Revisao",
    "Secao",
    "Tema",
    "UploadEmAndamento",
]
