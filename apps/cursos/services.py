from django.db import transaction

from apps.cursos.choices import StatusCurso, TipoEntregavel
from apps.cursos.models import Curso, Entregavel, MembroEquipe, Secao

SECOES_PLANO_ENSINO = [
    "Ementa",
    "Objetivos",
    "Conteúdo programático",
    "Metodologia",
    "Cronograma",
    "Avaliação",
    "Referências",
]


@transaction.atomic
def criar_curso(**dados):
    """Cria o curso, seus cinco entregaveis e as secoes iniciais do Plano de Ensino.

    Feito aqui, e nao por sinal post_save: sinal e invisivel no fluxo, dificil de
    testar e nao dispara de forma confiavel em fixtures e criacoes em lote (spec 4.6).
    """
    curso = Curso.objects.create(**dados)
    for tipo in TipoEntregavel:
        entregavel = Entregavel.objects.create(curso=curso, tipo=tipo)
        if tipo == TipoEntregavel.PLANO_ENSINO:
            for ordem, titulo in enumerate(SECOES_PLANO_ENSINO, start=1):
                Secao.objects.create(entregavel=entregavel, titulo=titulo, ordem=ordem)
    return curso


@transaction.atomic
def adicionar_membro(curso, aluno, por):
    """Vincula um aluno a equipe. O primeiro membro tira o curso do rascunho."""
    membro = MembroEquipe.objects.create(curso=curso, aluno=aluno)
    if curso.status == StatusCurso.RASCUNHO:
        curso.status = StatusCurso.EM_PRODUCAO
        curso.save()
    return membro
