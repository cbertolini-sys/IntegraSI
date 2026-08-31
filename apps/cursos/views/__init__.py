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
    nova_versao,
)
from apps.cursos.views.midia import baixar
from apps.cursos.views.professor import (
    decidir,
    equipe,
    ficha,
    fila_revisao,
    nova_proposta,
    remover_da_equipe,
    revisar,
    submeter_curso,
)
from apps.cursos.views.upload import (
    upload_bloco,
    upload_concluir,
    upload_estado,
    upload_iniciar,
)

__all__ = [
    "analisar_curso", "anexar", "baixar", "curso", "cursos_no_catalogo", "decidir", "decidir_curso",
    "entregavel",
    "ficha",
    "enviar_entregavel", "equipe", "fila_coordenacao", "fila_revisao", "meus_cursos",
    "nova_proposta", "nova_versao", "remover_da_equipe", "revisar", "salvar_secao", "submeter_curso",
    "upload_bloco", "upload_concluir", "upload_estado", "upload_iniciar",
]
