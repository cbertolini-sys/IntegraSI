from apps.cursos.views.aluno import (
    anexar,
    curso,
    entregavel,
    enviar_entregavel,
    meus_cursos,
    salvar_secao,
)
from apps.cursos.views.professor import decidir, equipe, fila_revisao, nova_proposta, revisar

__all__ = [
    "anexar", "curso", "decidir", "entregavel", "enviar_entregavel", "equipe",
    "fila_revisao", "meus_cursos", "nova_proposta", "revisar", "salvar_secao",
]
