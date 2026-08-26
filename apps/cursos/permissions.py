from django.core.exceptions import PermissionDenied


def garante(condicao, mensagem):
    """Levanta PermissionDenied quando a condicao e falsa. Usado pelos servicos para
    que a checagem fique junto da regra, e nao espalhada em if de template (spec 10)."""
    if not condicao:
        raise PermissionDenied(mensagem)


def e_responsavel(usuario, curso):
    return curso.professor_responsavel_id == usuario.id


def pode_ver_curso(usuario, curso):
    if usuario.e_coordenador:
        return True
    if usuario.e_professor:
        return e_responsavel(usuario, curso)
    return curso.tem_membro(usuario)


def pode_gerir_equipe(usuario, curso):
    return usuario.e_coordenador or (usuario.e_professor and e_responsavel(usuario, curso))


def pode_revisar(usuario, curso):
    return pode_gerir_equipe(usuario, curso)


def e_membro_da_equipe(usuario, curso):
    """Pertence a equipe do curso, independente do estado de nenhum entregavel.
    Distinto de pode_editar_producao: aqui e so vinculo, sem olhar editavel - e o
    que enviar_para_revisao usa para autorizar o pedido antes de checar o estado,
    senao um reenvio legitimo (ja em revisao/aprovado) vira PermissionDenied em vez
    do ValidationError que a regra de negocio espera."""
    return curso.tem_membro(usuario)


def pode_editar_producao(usuario, entregavel):
    """Aluno da equipe edita apenas enquanto o entregavel esta em rascunho ou
    devolvido; enviado para revisao, congela (spec 10)."""
    if not entregavel.editavel:
        return False
    return e_membro_da_equipe(usuario, entregavel.curso)
