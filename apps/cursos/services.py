from django.core.exceptions import ValidationError
from django.db import transaction

from apps.cursos import validacoes
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel
from apps.cursos.models import Curso, Entregavel, MembroEquipe, Revisao, Secao

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


@transaction.atomic
def enviar_para_revisao(entregavel, por):
    """Manda o entregavel para o professor revisar. So sai de RASCUNHO ou DEVOLVIDO,
    e so quando nao ha pendencia nenhuma: a lista de pendencias e o que a Task 9
    mostra ao aluno (spec 6)."""
    if not entregavel.editavel:
        raise ValidationError(
            f"Este entregável está {entregavel.get_status_display().lower()} e não pode ser reenviado."
        )
    faltas = validacoes.pendencias(entregavel)
    if faltas:
        raise ValidationError(faltas)
    entregavel.status = StatusEntregavel.EM_REVISAO
    entregavel.save()
    return entregavel


@transaction.atomic
def aprovar_entregavel(entregavel, por, comentario=""):
    """Aprova um entregavel EM_REVISAO e acrescenta o registro imutavel da decisao."""
    _exige_em_revisao(entregavel)
    entregavel.status = StatusEntregavel.APROVADO
    entregavel.save()
    Revisao.objects.create(
        entregavel=entregavel, revisor=por, decisao=Revisao.APROVADO, comentario=comentario
    )
    return entregavel


@transaction.atomic
def devolver_entregavel(entregavel, por, comentario):
    """Devolve um entregavel EM_REVISAO para edicao. Exige comentario: mandar de
    volta sem dizer o que corrigir e o jeito mais caro de desperdicar uma revisao."""
    _exige_em_revisao(entregavel)
    if not (comentario or "").strip():
        raise ValidationError("Escreva o que precisa ser corrigido antes de devolver.")
    entregavel.status = StatusEntregavel.DEVOLVIDO
    entregavel.save()
    Revisao.objects.create(
        entregavel=entregavel, revisor=por, decisao=Revisao.DEVOLVIDO, comentario=comentario
    )
    return entregavel


def _exige_em_revisao(entregavel):
    if entregavel.status != StatusEntregavel.EM_REVISAO:
        raise ValidationError("Só é possível revisar um entregável que foi enviado para revisão.")
