from apps.cursos.views.aluno import (
    anexar,
    curso,
    entregavel,
    enviar_entregavel,
    meus_cursos,
    salvar_secao,
)
from apps.cursos.views.coordenador import (
    analisar_curso,
    cursos_no_catalogo,
    decidir_curso,
    fila_coordenacao,
)
from apps.cursos.views.professor import decidir, equipe, fila_revisao, nova_proposta, revisar, submeter_curso

__all__ = [
    "analisar_curso", "anexar", "curso", "cursos_no_catalogo", "decidir", "decidir_curso",
    "entregavel",
    "enviar_entregavel", "equipe", "fila_coordenacao", "fila_revisao", "meus_cursos",
    "nova_proposta", "revisar", "salvar_secao", "submeter_curso",
]
