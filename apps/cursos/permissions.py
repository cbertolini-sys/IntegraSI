from django.core.exceptions import PermissionDenied


def garante(condicao, mensagem):
    """Levanta PermissionDenied quando a condicao e falsa. Usado pelos servicos para
    que a checagem fique junto da regra, e nao espalhada em if de template (spec 10)."""
    if not condicao:
        raise PermissionDenied(mensagem)


def e_responsavel(usuario, curso):
    return curso.professor_responsavel_id == usuario.id


def pode_criar_curso(usuario):
    """Professor propõe curso (spec 3). Curso.clean() já barra um
    professor_responsavel que não seja professor, mas essa checagem só dispara
    dentro de Curso.save() e vira ValidationError - o portão de serviço aqui é quem
    devolve PermissionDenied antes disso, para quem chamar services.criar_curso
    direto (sem passar pelo gate da view, que hoje já restringe a professor)."""
    return usuario is not None and usuario.e_professor


def pode_ver_curso(usuario, curso):
    """Coordenacao ve tudo; os demais veem o curso que respondem ou que produzem.

    O ramo do professor nao pode ser so `e_responsavel`: a partir do Plano 6 um
    professor pode estar na equipe de um curso de outro (spec 10, professor
    colaborador), e produzir sem enxergar nao existe.
    """
    if usuario.e_coordenador:
        return True
    if e_responsavel(usuario, curso):
        return True
    return curso.tem_membro(usuario)


def pode_gerir_equipe(usuario, curso):
    return usuario.e_coordenador or (usuario.e_professor and e_responsavel(usuario, curso))


def pode_revisar(usuario, curso):
    """Quem aprova ou devolve um entregavel (spec 6): coordenador, ou o professor
    responsavel. Coincide hoje com pode_gerir_equipe, mas as duas sao regras
    independentes da spec - quem monta a equipe e quem revisa o trabalho. Escrita
    por extenso, e nao como alias de pode_gerir_equipe, para que o Plano 3 possa
    mudar uma sem arrastar a outra por acidente (item 7 da revisao de branco)."""
    return usuario.e_coordenador or (usuario.e_professor and e_responsavel(usuario, curso))


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


def pode_publicar(usuario):
    """Quem publica, devolve ou despublica um curso (spec 5, 11): so o
    coordenador. Distinta de pode_revisar, que e do professor - o portao entre
    producao e catalogo publico e uma decisao institucional, nao pedagogica."""
    return usuario.e_coordenador


def pode_abrir_versao(usuario, curso):
    """Quem abre nova versao de um curso publicado (spec 4.5, passo 1): o
    coordenador ou o professor responsavel pela versao atual. Coincide hoje com
    pode_gerir_equipe, e esta escrita por extenso pelo mesmo motivo de
    pode_revisar: sao regras diferentes da spec (montar equipe x decidir que o
    curso precisa de outra versao) e uma pode mudar sem a outra."""
    return usuario.e_coordenador or (usuario.e_professor and e_responsavel(usuario, curso))


def pode_baixar_arquivo(usuario, arquivo):
    """Pode baixar quem enxerga ALGUM curso que anexa este arquivo.

    A pergunta e "existe algum anexo cujo curso esta pessoa pode ver?", e nao "o
    que diz o primeiro anexo": `Arquivo.anexos` e FK reversa, e a partir do Plano
    4 (versoes de curso) o mesmo Arquivo e compartilhado por varias versoes em vez
    de ter os bytes clonados (spec 4.6). Olhar so o primeiro recusaria quem tem
    acesso por outra versao - e liberaria por uma versao que a pessoa nao deveria
    ver, dependendo so da ordenacao do Anexo.

    Arquivo sem anexo nenhum nao tem curso por onde autorizar: ninguem baixa.

    Consequencia deliberada a partir do Plano 4 (versoes), respondendo a pergunta
    que a Task 4 deixou em aberto: quando a v2 publica e a v1 vira SUBSTITUIDO,
    a equipe da v1 continua baixando o material da v1 - "permanece consultavel
    como historico" (spec 4.5), e substituicao e fato do catalogo, nao revogacao
    de acesso de quem produziu o trabalho. A equipe NOVA alcanca os mesmos bytes
    pelo anexo clonado na v2, nunca pela v1 (ela nao e membro de la): se ela
    apagar o anexo da v2, perde o arquivo junto, como qualquer outra equipe. A
    coordenacao enxerga as duas. Testes em test_versoes.py, regra 23.
    """
    return any(
        pode_ver_curso(usuario, anexo.entregavel.curso)
        for anexo in arquivo.anexos.select_related("entregavel__curso")
    )


def pode_editar_ficha(usuario, curso):
    """Quem preenche a ficha do curso (spec 10): qualquer membro da equipe, o
    professor responsavel e o coordenador, enquanto o curso esta em producao.

    Escrita por extenso, e nao como alias de pode_ver_curso, porque as duas regras
    sao diferentes: ver um curso e ler; a ficha e o que vai ao catalogo publico, e
    ela congela quando o curso sai de producao.
    """
    from apps.cursos.choices import STATUS_EDITAVEIS

    if curso.status not in STATUS_EDITAVEIS:
        return False
    if usuario.e_coordenador:
        return True
    return e_responsavel(usuario, curso) or curso.tem_membro(usuario)
