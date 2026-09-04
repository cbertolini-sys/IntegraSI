from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalogo.models import Solicitacao, SugestaoDeCurso
from apps.cursos import permissions
from apps.notificacoes.services import enfileirar
from apps.turmas.models import Turma


@transaction.atomic
def aceitar_solicitacao(solicitacao, professor, dados_turma, por):
    """Aceita a solicitação e cria a turma na mesma transação.

    O professor é obrigatório: é desta designação que decorre o acesso dele aos
    participantes (spec 7.2). Solicitação aceita sem turma e sem professor não é
    um estado alcançável.
    """
    permissions.garante(permissions.pode_publicar(por), "Somente a coordenação aceita solicitações.")
    if solicitacao.status in (Solicitacao.ACEITA, Solicitacao.RECUSADA):
        raise ValidationError("Esta solicitação já foi respondida.")

    turma = Turma.objects.create(
        curso=solicitacao.curso, solicitacao=solicitacao, professor=professor, **dados_turma
    )
    solicitacao.status = Solicitacao.ACEITA
    solicitacao.resposta = (
        f"Curso agendado para {turma.data_inicio:%d/%m/%Y} em {turma.local}. "
        f"Professor responsável: {professor.nome_completo}."
    )
    solicitacao.save(update_fields=["status", "resposta"])

    enfileirar(
        evento="SOLICITACAO_ACEITA",
        destinatarios=[solicitacao.email],
        assunto=f"Curso agendado: {solicitacao.curso.titulo}",
        corpo=solicitacao.resposta,
    )
    return turma


@transaction.atomic
def recusar_solicitacao(solicitacao, por, resposta):
    permissions.garante(
        permissions.pode_publicar(por), "Somente a coordenação responde solicitações."
    )
    if solicitacao.status in (Solicitacao.ACEITA, Solicitacao.RECUSADA):
        raise ValidationError("Esta solicitação já foi respondida.")
    if not (resposta or "").strip():
        raise ValidationError("Escreva a resposta ao solicitante.")
    solicitacao.status = Solicitacao.RECUSADA
    solicitacao.resposta = resposta
    solicitacao.save(update_fields=["status", "resposta"])
    enfileirar(
        evento="SOLICITACAO_RECUSADA",
        destinatarios=[solicitacao.email],
        assunto=f"Sobre sua solicitação: {solicitacao.curso.titulo}",
        corpo=resposta,
    )
    return solicitacao


def _responder_sugestao(sugestao, por, resposta, status, evento, assunto):
    """O tronco comum das duas decisoes sobre uma sugestao.

    Nao ha turma a criar, ao contrario de `aceitar_solicitacao`: aceitar uma
    sugestao diz "vamos produzir isto", e a producao comeca depois, quando um
    professor abre a proposta. Por isso os dois desfechos sao a mesma operacao
    com outro rotulo, e por isso a resposta escrita e obrigatoria nos DOIS: sem
    turma e sem curso, ela e a unica coisa que a pessoa recebe.
    """
    permissions.garante(
        permissions.pode_publicar(por), "Somente a coordenação responde sugestões."
    )
    if sugestao.status in (SugestaoDeCurso.ACEITA, SugestaoDeCurso.RECUSADA):
        raise ValidationError("Esta sugestão já foi respondida.")
    if not (resposta or "").strip():
        raise ValidationError("Escreva a resposta a quem sugeriu.")

    sugestao.status = status
    sugestao.resposta = resposta
    sugestao.save(update_fields=["status", "resposta"])
    enfileirar(
        evento=evento,
        destinatarios=[sugestao.email],
        assunto=assunto,
        corpo=resposta,
    )
    return sugestao


@transaction.atomic
def aceitar_sugestao(sugestao, por, resposta):
    return _responder_sugestao(
        sugestao,
        por,
        resposta,
        status=SugestaoDeCurso.ACEITA,
        evento="SUGESTAO_ACEITA",
        assunto="Sua sugestão de curso foi aceita",
    )


@transaction.atomic
def recusar_sugestao(sugestao, por, resposta):
    return _responder_sugestao(
        sugestao,
        por,
        resposta,
        status=SugestaoDeCurso.RECUSADA,
        evento="SUGESTAO_RECUSADA",
        assunto="Sobre a sua sugestão de curso",
    )
