import hashlib

from django.contrib.postgres.search import SearchVector
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import models, transaction
from django.utils import timezone

from apps.cursos import permissions, validacoes
from apps.cursos.arquivos import MEGA, valida_upload
from apps.cursos.busca import CONFIG_TEXTO
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import (
    Anexo,
    Arquivo,
    Curso,
    Entregavel,
    LogTransicaoCurso,
    MembroEquipe,
    Revisao,
    Secao,
)
from apps.notificacoes.services import enfileirar

# Cabecalho suficiente para todas as assinaturas de `arquivos.ASSINATURAS` e para a
# caixa `ftyp` do MP4 (bytes 4:8).
TAMANHO_CABECALHO = 16
# Pedaco de leitura da conclusao. O arquivo pode ter 1 GB e nunca pode sentar
# inteiro na memoria de um worker (spec 8).
BLOCO_LEITURA = MEGA

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
    permissions.garante(
        permissions.pode_criar_curso(dados.get("professor_responsavel")),
        "Somente professor cria curso.",
    )
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
    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    membro = MembroEquipe.objects.create(curso=curso, aluno=aluno)
    if curso.status == StatusCurso.RASCUNHO:
        curso.status = StatusCurso.EM_PRODUCAO
        # atualizado_em precisa estar na lista pelo mesmo motivo de
        # enviar_para_revisao acima: e auto_now=True, e update_fields so o persiste
        # se ele estiver nomeado.
        curso.save(update_fields=["status", "atualizado_em"])
    return membro


@transaction.atomic
def enviar_para_revisao(entregavel, por):
    """Manda o entregavel para o professor revisar. So sai de RASCUNHO ou DEVOLVIDO,
    e so quando nao ha pendencia nenhuma: a lista de pendencias e o que a Task 9
    mostra ao aluno (spec 6)."""
    # A checagem de permissao vem antes da checagem de editavel de proposito: um
    # aluno de fora que chuta um id de entregavel nao pode descobrir, pelo tipo do
    # erro, que o entregavel esta em revisao - isso vazaria o estado de um curso
    # que ele nao deveria nem enxergar. Usa e_membro_da_equipe, nao
    # pode_editar_producao: este ultimo ja embute o estado editavel, e um reenvio
    # de algo ja em revisao/aprovado precisa continuar autorizado para o membro,
    # so barrado depois pela checagem de editavel abaixo (com ValidationError).
    permissions.garante(
        permissions.e_membro_da_equipe(por, entregavel.curso) or permissions.pode_revisar(por, entregavel.curso),
        "Você não participa da equipe deste curso.",
    )
    if not entregavel.editavel:
        raise ValidationError(
            f"Este entregável está {entregavel.get_status_display().lower()} e não pode ser reenviado."
        )
    faltas = validacoes.pendencias(entregavel)
    if faltas:
        raise ValidationError(faltas)
    entregavel.status = StatusEntregavel.EM_REVISAO
    # atualizado_em e auto_now=True: um save(update_fields=[...]) so o atualiza no
    # banco se ele estiver na lista (pre_save so roda para quem esta em
    # update_fields). fila_revisao.html mostra este campo como "enviado em" -
    # esquece-lo aqui congelaria o rotulo na data de criacao do entregavel.
    entregavel.save(update_fields=["status", "atualizado_em"])
    return entregavel


@transaction.atomic
def aprovar_entregavel(entregavel, por, comentario=""):
    """Aprova um entregavel EM_REVISAO e acrescenta o registro imutavel da decisao."""
    permissions.garante(
        permissions.pode_revisar(por, entregavel.curso),
        "Somente o professor responsável revisa.",
    )
    _exige_em_revisao(entregavel)
    entregavel.status = StatusEntregavel.APROVADO
    entregavel.save(update_fields=["status", "atualizado_em"])
    Revisao.objects.create(
        entregavel=entregavel, revisor=por, decisao=Revisao.APROVADO, comentario=comentario
    )
    return entregavel


@transaction.atomic
def devolver_entregavel(entregavel, por, comentario):
    """Devolve um entregavel EM_REVISAO para edicao. Exige comentario: mandar de
    volta sem dizer o que corrigir e o jeito mais caro de desperdicar uma revisao."""
    permissions.garante(
        permissions.pode_revisar(por, entregavel.curso),
        "Somente o professor responsável revisa.",
    )
    _exige_em_revisao(entregavel)
    if not (comentario or "").strip():
        raise ValidationError("Escreva o que precisa ser corrigido antes de devolver.")
    entregavel.status = StatusEntregavel.DEVOLVIDO
    entregavel.save(update_fields=["status", "atualizado_em"])
    Revisao.objects.create(
        entregavel=entregavel, revisor=por, decisao=Revisao.DEVOLVIDO, comentario=comentario
    )
    return entregavel


def _exige_em_revisao(entregavel):
    if entregavel.status != StatusEntregavel.EM_REVISAO:
        raise ValidationError("Só é possível revisar um entregável que foi enviado para revisão.")


def _transicionar(curso, para, por, observacao=""):
    """Muda o status do curso e grava o LogTransicaoCurso na mesma transacao. Ponto
    unico por onde toda mudanca de situacao do curso passa, para que o historico
    administrativo (spec 11) nunca fique incompleto."""
    de = curso.status
    curso.status = para
    campos = ["status", "atualizado_em"]
    if para == StatusCurso.PUBLICADO:
        curso.publicado_em = timezone.now()
        campos.append("publicado_em")
    curso.save(update_fields=campos)
    LogTransicaoCurso.objects.create(
        curso=curso, de_status=de, para_status=para, usuario=por, observacao=observacao
    )


def _emails_da_equipe(curso):
    return [m.aluno.email for m in curso.membros.select_related("aluno")]


def _emails_dos_coordenadores():
    from apps.contas.models import Usuario

    return list(
        Usuario.objects.filter(papel=Usuario.COORDENADOR, is_active=True).values_list("email", flat=True)
    )


@transaction.atomic
def submeter_ao_coordenador(curso, por):
    """Professor manda o curso para a coordenacao (spec 5). So sai de EM_PRODUCAO
    ou DEVOLVIDO, com os cinco entregaveis aprovados e os dados do curso em dia -
    o curso pode ser editado depois do Plano de Ensino aprovado, entao a mesma
    checagem de validacoes.dados_do_curso roda de novo aqui."""
    permissions.garante(
        permissions.pode_gerir_equipe(por, curso), "Somente o professor responsável submete."
    )
    if curso.status not in (StatusCurso.EM_PRODUCAO, StatusCurso.DEVOLVIDO):
        raise ValidationError("Este curso não está em produção.")
    if not curso.pronto_para_o_coordenador:
        raise ValidationError("Todos os cinco entregáveis precisam estar aprovados.")
    faltas = validacoes.dados_do_curso(curso)
    if faltas:
        raise ValidationError(faltas)
    _transicionar(curso, StatusCurso.AGUARDANDO_COORDENADOR, por)
    enfileirar(
        evento="CURSO_SUBMETIDO",
        destinatarios=_emails_dos_coordenadores(),
        assunto=f"Curso aguardando aprovação: {curso.titulo}",
        corpo=f"O professor {por.nome_completo} submeteu o curso {curso.titulo} para aprovação.",
    )
    return curso


# De onde um curso pode entrar (ou voltar) para o catalogo publico (spec 5).
# DESPUBLICADO esta aqui porque a spec diz, textualmente, que um curso
# despublicado "pode ser republicado" - e diz, no mesmo paragrafo, que
# SUBSTITUIDO e terminal e "nao republicavel". O contraste entre as duas frases
# nomeia a publicacao como o ato que desfaz a despublicacao.
#
# Republicar volta direto a PUBLICADO, sem passar pela fila da coordenacao, por
# tres razoes lidas da spec 5:
#   1. O diagrama de estados nao tem seta de DESPUBLICADO para dentro do ciclo de
#      producao; as unicas setas que chegam em AGUARDANDO_COORDENADOR saem de
#      EM_PRODUCAO e DEVOLVIDO.
#   2. "Somente o coordenador publica, devolve ao professor ou despublica", ao
#      passo que submeter e ato do professor. Mandar a republicacao pela fila
#      faria a decisao do coordenador so poder ser desfeita pelo professor - um
#      beco sem saida novo no lugar do antigo, pior ainda se o professor
#      responsavel tiver deixado a instituicao.
#   3. Despublicar nao reabre os cinco entregaveis (ao contrario de
#      devolver_curso, R54): o material continua APROVADO e intocado, entao a
#      fila seria cerimonia sobre um curso que ninguem editou.
ORIGENS_DA_PUBLICACAO = (StatusCurso.AGUARDANDO_COORDENADOR, StatusCurso.DESPUBLICADO)


@transaction.atomic
def publicar_curso(curso, por):
    """Coordenador publica o curso submetido, ou republica um despublicado
    (spec 5, 11); avisa a equipe e o professor, sem enviar e-mail dentro da
    transacao - enfileirar so grava.

    A republicacao passa por aqui, e nao por um .update() no shell, justamente
    para que _transicionar grave o LogTransicaoCurso: o historico administrativo
    da spec 11 nao pode ter buraco em nenhuma das duas voltas.
    """
    permissions.garante(permissions.pode_publicar(por), "Somente o coordenador publica.")
    if curso.status not in ORIGENS_DA_PUBLICACAO:
        raise ValidationError(
            "Só se publica curso submetido pelo professor, ou se republica curso despublicado."
        )
    republicacao = curso.status == StatusCurso.DESPUBLICADO
    _transicionar(curso, StatusCurso.PUBLICADO, por)
    if republicacao:
        enfileirar(
            evento="CURSO_REPUBLICADO",
            destinatarios=_emails_da_equipe(curso) + [curso.professor_responsavel.email],
            assunto=f"Curso republicado: {curso.titulo}",
            corpo=f"O curso {curso.titulo} voltou ao catálogo público.",
        )
    else:
        enfileirar(
            evento="CURSO_PUBLICADO",
            destinatarios=_emails_da_equipe(curso) + [curso.professor_responsavel.email],
            assunto=f"Curso publicado: {curso.titulo}",
            corpo=f"O curso {curso.titulo} foi aprovado pela coordenação e está no catálogo público.",
        )
    return curso


@transaction.atomic
def devolver_curso(curso, por, comentario):
    """Coordenador devolve o curso submetido, com comentario obrigatorio (spec 5,
    11).

    R54: devolver o curso tambem reabre os cinco entregaveis para DEVOLVIDO, na
    mesma transacao. Sem isso o curso volta para DEVOLVIDO com os cinco
    entregaveis ainda APROVADO (portanto congelados, ver Entregavel.editavel), e a
    equipe fica sem como agir sobre o retorno do coordenador - um beco sem saida
    que a revisao do Plano 2 encontrou. Nao cria Revisao para os entregaveis: quem
    decidiu foi o coordenador sobre o curso, nao o professor sobre cada entrega, e
    um registro de Revisao com o coordenador como revisor falsificaria o historico
    pedagogico que essa tabela existe para preservar. O fato mora so no
    LogTransicaoCurso."""
    permissions.garante(permissions.pode_publicar(por), "Somente o coordenador devolve o curso.")
    if curso.status != StatusCurso.AGUARDANDO_COORDENADOR:
        raise ValidationError("Só se devolve curso que está aguardando aprovação.")
    if not (comentario or "").strip():
        raise ValidationError("Escreva o que precisa ser corrigido antes de devolver.")
    _transicionar(curso, StatusCurso.DEVOLVIDO, por, observacao=comentario)
    for entregavel in curso.entregaveis.all():
        entregavel.status = StatusEntregavel.DEVOLVIDO
        entregavel.save(update_fields=["status", "atualizado_em"])
    enfileirar(
        evento="CURSO_DEVOLVIDO",
        destinatarios=[curso.professor_responsavel.email],
        assunto=f"Curso devolvido: {curso.titulo}",
        corpo=comentario,
    )
    return curso


@transaction.atomic
def despublicar_curso(curso, por, motivo):
    """Coordenador tira o curso do catalogo publico, com motivo obrigatorio para
    o historico administrativo (spec 11)."""
    permissions.garante(permissions.pode_publicar(por), "Somente o coordenador despublica.")
    if curso.status != StatusCurso.PUBLICADO:
        raise ValidationError("Este curso não está publicado.")
    if not (motivo or "").strip():
        raise ValidationError("Informe o motivo da despublicação.")
    _transicionar(curso, StatusCurso.DESPUBLICADO, por, observacao=motivo)
    return curso


@transaction.atomic
def definir_temas(curso, temas, por):
    """Troca os temas do curso e reindexa. A reindexacao e explicita porque coluna
    gerada nao alcanca M2M (spec 4.4)."""
    permissions.garante(permissions.pode_gerir_equipe(por, curso), "Curso de outro professor.")
    curso.temas.set(temas)
    atualizar_vetor_temas(curso)
    return curso


def atualizar_vetor_temas(curso):
    """Recalcula vetor_temas a partir dos nomes dos temas ligados hoje ao curso.
    Chamada tanto por definir_temas quanto por TemaAdmin.save_model quando um
    Tema e renomeado - nos dois casos o vetor antigo ficaria com um nome que o
    tema nao tem mais."""
    nomes = " ".join(curso.temas.values_list("nome", flat=True))
    Curso.objects.filter(pk=curso.pk).update(
        vetor_temas=SearchVector(models.Value(nomes), config=CONFIG_TEXTO)
    )


@transaction.atomic
def concluir_upload(upload, titulo, duracao_minutos):
    """Transforma o arquivo parcial de um upload em blocos em Arquivo + Anexo de video.

    Le o parcial sempre em pedacos de `BLOCO_LEITURA` pelo `open` do modulo: um
    `parcial.read()` sem argumento carregaria 1 GB na memoria do worker (spec 8).
    """
    permissions.garante(
        permissions.pode_editar_producao(upload.usuario, upload.entregavel),
        "Este entregável não está aberto para edição.",
    )
    # Reconferido aqui, e nao so na abertura: 1 GB no upstream domestico leva perto
    # de meia hora, e a janela em que o professor aprova o entregavel cabe inteira
    # dentro dela. O portao da abertura ja tinha expirado quando os bytes chegaram.
    if not upload.completo:
        raise ValidationError("O upload ainda não terminou.")
    # Titulo e duracao sao exigidos por Anexo.clean(), mas conferidos AQUI, antes de
    # qualquer byte ir para o disco: descobrir no `Anexo.objects.create()` da ultima
    # linha significaria o arquivo ja copiado para MEDIA_ROOT: a transacao desfaz a
    # linha, nao o arquivo em disco. E o orfao que `anexar` teve que consertar.
    if not (titulo or "").strip():
        raise ValidationError("Informe o título do vídeo.")
    if not duracao_minutos:
        raise ValidationError("Informe a duração do vídeo em minutos.")

    caminho = upload.caminho()
    tamanho = caminho.stat().st_size
    digest = hashlib.sha256()
    with open(caminho, "rb") as parcial:
        cabecalho = parcial.read(TAMANHO_CABECALHO)
        # O nome declarado na abertura nao prova nada sobre os bytes que chegaram:
        # a conferencia de conteudo e obrigatoria aqui, com o cabecalho real.
        mime = valida_upload(upload.nome_original, tamanho, cabecalho)
        if mime != "video/mp4":
            raise ValidationError("Este entregável aceita apenas vídeo MP4.")
        parcial.seek(0)
        for pedaco in iter(lambda: parcial.read(BLOCO_LEITURA), b""):
            digest.update(pedaco)

        arquivo = Arquivo(
            nome_original=upload.nome_original,
            tamanho=tamanho,
            mime=mime,
            hash_conteudo=digest.hexdigest(),
            enviado_por=upload.usuario,
        )
        # File.chunks() volta ao inicio sozinho e copia de 64 KB em 64 KB.
        arquivo.arquivo.save(upload.nome_original, File(parcial), save=False)
    arquivo.save()

    anexo = Anexo.objects.create(
        entregavel=upload.entregavel,
        tipo_midia=TipoMidia.VIDEO,
        titulo=titulo,
        arquivo=arquivo,
        duracao_minutos=duracao_minutos,
        enviado_por=upload.usuario,
    )
    # Fora da transacao de proposito. Um `unlink()` aqui dentro e a inversao classica:
    # se a transacao volta atras depois dele, a linha de UploadEmAndamento ressuscita
    # apontando para um arquivo que ja nao existe, e o dono nao consegue nem retomar
    # nem concluir. O disco so pode ser mexido depois que o banco confirmou.
    transaction.on_commit(lambda: caminho.unlink(missing_ok=True))
    upload.delete()
    return anexo
