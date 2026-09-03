import hashlib

from django.contrib.postgres.search import SearchVector
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import models, transaction
from django.utils import timezone

from apps.cursos import permissions, validacoes
from apps.cursos.arquivos import MEGA, valida_upload
from apps.cursos.busca import CONFIG_TEXTO
from apps.cursos.choices import (
    STATUS_EDITAVEIS,
    StatusCurso,
    StatusEntregavel,
    TipoEntregavel,
    TipoMidia,
)
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

# O que escrever em cada secao. Fica ao lado da lista que as cria, e nao no
# template, pelo mesmo motivo do `help_text` dos formularios: e aqui que alguem
# que acrescentar uma secao ve que falta explica-la.
#
# A busca e pelo TITULO, e nao por posicao: a spec 15 diz que as secoes sao livres
# ("entregaveis fixos, secoes livres"), entao o professor pode acrescentar uma que
# nao esta nesta lista, e ela simplesmente fica sem balao.
AJUDA_DAS_SECOES = {
    "Ementa": (
        "Um paragrafo dizendo do que o curso trata. E o resumo do conteudo, nao "
        "dos objetivos: o que sera visto, e nao o que a turma vai conseguir fazer."
    ),
    "Objetivos": (
        "O que a turma sera capaz de fazer ao terminar. Comece cada um com um "
        "verbo: reconhecer, criar, comparar, avaliar."
    ),
    "Conteúdo programático": (
        "Os assuntos, na ordem em que serao trabalhados. Uma lista costuma "
        "funcionar melhor que um paragrafo corrido."
    ),
    "Metodologia": (
        "Como as aulas acontecem: exposicao, pratica em duplas, atividade "
        "desplugada, uso de laboratorio. Diga tambem o que a escola precisa ter."
    ),
    "Cronograma": (
        "A divisao das horas por encontro ou por assunto. A soma precisa bater com "
        "a carga horaria informada no curso."
    ),
    "Avaliação": (
        "Como se percebe que a turma aprendeu: observacao, producao, exercicio, "
        "apresentacao. E o criterio, nao a nota."
    ),
    "Referências": (
        "De onde veio o conteudo: livros, artigos, sites, materiais de terceiros. "
        "Serve tambem para a escola aprofundar depois."
    ),
}


@transaction.atomic
def criar_curso(**dados):
    """Cria o curso, seus seis entregaveis e as secoes iniciais do Plano de Ensino.

    Feito aqui, e nao por sinal post_save: sinal e invisivel no fluxo, dificil de
    testar e nao dispara de forma confiavel em fixtures e criacoes em lote (spec 4.6).
    """
    permissions.garante(
        permissions.pode_criar_curso(dados.get("professor_responsavel")),
        "Somente professor cria curso.",
    )
    if "edicao" not in dados:
        # Import adiado, como abrir_nova_versao ja faz neste arquivo.
        from apps.edicoes.models import Edicao

        corrente = Edicao.objects.corrente()
        if corrente is None:
            raise ValidationError(
                "Nenhuma edição da disciplina está aberta. Peça à coordenação para "
                "abrir a edição corrente antes de propor um curso."
            )
        dados["edicao"] = corrente
    curso = Curso.objects.create(**dados)
    for tipo in TipoEntregavel:
        entregavel = Entregavel.objects.create(curso=curso, tipo=tipo)
        if tipo == TipoEntregavel.PLANO_ENSINO:
            for ordem, titulo in enumerate(SECOES_PLANO_ENSINO, start=1):
                Secao.objects.create(entregavel=entregavel, titulo=titulo, ordem=ordem)
    # MembroEquipe direto, e nao adicionar_membro: aquele servico tira o curso de
    # RASCUNHO no primeiro membro, e o responsavel entrando na criacao faria todo
    # curso nascer EM_PRODUCAO, matando um estado que a spec 5 usa. Proposta com
    # uma pessoa so ainda e proposta.
    MembroEquipe.objects.create(curso=curso, pessoa=curso.professor_responsavel)
    return curso


@transaction.atomic
def adicionar_membro(curso, pessoa, por):
    """Vincula alguem a equipe. O primeiro membro tira o curso do rascunho."""
    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    membro = MembroEquipe.objects.create(curso=curso, pessoa=pessoa)
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
    _exige_comentario(comentario, "Escreva um comentário antes de aprovar.")
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
    _exige_comentario(comentario, "Escreva o que precisa ser corrigido antes de devolver.")
    entregavel.status = StatusEntregavel.RASCUNHO
    entregavel.save(update_fields=["status", "atualizado_em"])
    Revisao.objects.create(
        entregavel=entregavel, revisor=por, decisao=Revisao.DEVOLVIDO, comentario=comentario
    )
    return entregavel


@transaction.atomic
def reabrir_entregavel(entregavel, por, comentario):
    """Desfaz uma aprovacao enquanto o curso ainda esta em producao.

    Aprovar cedo demais era definitivo: `_exige_em_revisao` recusa qualquer
    decisao fora de EM_REVISAO, e nao havia caminho de volta. O entregavel volta
    para DEVOLVIDO, que e o estado em que a equipe pode editar de novo.

    So enquanto o curso nao subiu: depois de submetido, mexer num entregavel
    mudaria por baixo o material que a coordenacao esta analisando.
    """
    permissions.garante(
        permissions.pode_revisar(por, entregavel.curso),
        "Somente o professor responsável revisa.",
    )
    if entregavel.status != StatusEntregavel.APROVADO:
        raise ValidationError("Só é possível reabrir um entregável aprovado.")
    if entregavel.curso.status not in STATUS_EDITAVEIS:
        raise ValidationError(
            "O curso já foi enviado para a coordenação; não dá para reabrir um "
            "entregável agora."
        )
    _exige_comentario(comentario, "Escreva por que está reabrindo o entregável.")
    entregavel.status = StatusEntregavel.RASCUNHO
    entregavel.save(update_fields=["status", "atualizado_em"])
    Revisao.objects.create(
        entregavel=entregavel, revisor=por, decisao=Revisao.REABERTO, comentario=comentario
    )
    return entregavel


def _exige_comentario(comentario, mensagem):
    """Toda decisao registra um porque.

    O historico so vale se cada linha dele disser alguma coisa: aprovar aceitava
    comentario vazio, e o registro nascia mudo.
    """
    if not (comentario or "").strip():
        raise ValidationError(mensagem)


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
    return [m.pessoa.email for m in curso.membros.select_related("pessoa")]


def _emails_dos_coordenadores():
    from apps.contas.models import Usuario

    return list(
        Usuario.objects.filter(papel=Usuario.COORDENADOR, is_active=True).values_list("email", flat=True)
    )


@transaction.atomic
def submeter_ao_coordenador(curso, por):
    """Professor manda o curso para a coordenacao (spec 5). So sai de EM_PRODUCAO
    ou DEVOLVIDO, com todos os entregaveis aprovados e os dados do curso em dia -
    o curso pode ser editado depois do Plano de Ensino aprovado, entao a mesma
    checagem de validacoes.dados_do_curso roda de novo aqui."""
    permissions.garante(
        permissions.pode_gerir_equipe(por, curso), "Somente o professor responsável submete."
    )
    if curso.status not in (StatusCurso.EM_PRODUCAO, StatusCurso.DEVOLVIDO):
        raise ValidationError("Este curso não está em produção.")
    if not curso.pronto_para_o_coordenador:
        # Do modelo, e nao escrito a mao: a migracao 0016 acrescentou o sexto
        # entregavel e a frase ficou dizendo "cinco" por uma sessao inteira,
        # contradizendo a pagina Sobre na mesma tela. Um setimo entregavel nao
        # pode reabrir o mesmo defeito.
        total = len(TipoEntregavel.choices)
        raise ValidationError(f"Todos os {total} entregáveis precisam estar aprovados.")
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
#   3. Despublicar nao reabre os seis entregaveis (ao contrario de
#      devolver_curso, R54): o material continua APROVADO e intocado, entao a
#      fila seria cerimonia sobre um curso que ninguem editou.
ORIGENS_DA_PUBLICACAO = (StatusCurso.AGUARDANDO_COORDENADOR, StatusCurso.DESPUBLICADO)


def _substituir_versoes_anteriores(curso, por):
    """Move para SUBSTITUIDO as outras versoes da linhagem que ja estiveram no
    catalogo, mantendo a invariante "no maximo uma versao publicada por linhagem"
    (spec 4.5) - e ela que deixa o catalogo ser um filter(status=PUBLICADO) sem
    DISTINCT ON.

    Alcanca PUBLICADO e tambem DESPUBLICADO. A spec 5 diz "publicar uma versao
    move automaticamente a anterior para SUBSTITUIDO", e ser superada e fato da
    linhagem, nao do estado do catalogo no instante da publicacao: se a versao
    velha estivesse apenas despublicada e assim continuasse, ela seguiria
    republicavel para sempre (spec 5: DESPUBLICADO "pode ser republicado") e
    voltaria ao catalogo ao lado da nova. Pior: a republicacao da velha e que
    substituiria a nova, invertendo a unica seta que a spec 5 desenha
    ("nova v PUBLICADO ==> versao anterior vira SUBSTITUIDO") e matando de forma
    terminal a versao mais recente. Fechar isso aqui, na publicacao da nova, e o
    que torna a inversao inalcancavel - a velha ja e terminal quando alguem
    pensar em republica-la.

    Nao alcanca versao em producao (RASCUNHO, EM_PRODUCAO, AGUARDANDO_COORDENADOR,
    DEVOLVIDO): republicar um curso despublicado nao pode jogar fora o trabalho da
    equipe que esta montando a proxima versao dele.
    """
    anteriores = Curso.objects.filter(
        models.Q(pk=curso.linhagem_id) | models.Q(raiz_id=curso.linhagem_id),
        status__in=(StatusCurso.PUBLICADO, StatusCurso.DESPUBLICADO),
    ).exclude(pk=curso.pk)
    for anterior in anteriores:
        _transicionar(
            anterior,
            StatusCurso.SUBSTITUIDO,
            por,
            observacao=f"Substituído pela versão {curso.versao}.",
        )


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
    # Substitui ANTES de publicar, e nao depois: entre as duas escritas a
    # linhagem teria duas linhas PUBLICADO, e o indice unico parcial
    # (uma_versao_publicada_por_linhagem) e conferido a cada comando, nao no
    # commit - indice parcial nao pode ser DEFERRABLE no Postgres. Nesta ordem a
    # invariante nunca chega a ser violada, nem por um instante dentro da
    # transacao.
    _substituir_versoes_anteriores(curso, por)
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

    R54: devolver o curso tambem reabre os seis entregaveis para DEVOLVIDO, na
    mesma transacao. Sem isso o curso volta para DEVOLVIDO com os seis
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
        entregavel.status = StatusEntregavel.RASCUNHO
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
def atualizar_ficha(curso, dados, por):
    """Grava a ficha preenchida pela equipe (spec 4.3 e 10).

    `temas` sai por definir_temas, e nao por curso.temas.set(): coluna gerada nao
    alcanca M2M, e e aquele servico que reindexa vetor_temas. Foi uma tela
    escrevendo `temas` direto que sumiu com cursos da busca no Plano 2.
    """
    permissions.garante(
        permissions.pode_editar_ficha(por, curso),
        "Somente a equipe do curso o edita, e apenas enquanto ele está em produção.",
    )
    dados = dict(dados)
    temas = dados.pop("temas", None)
    competencias = dados.pop("competencias", None)
    for campo, valor in dados.items():
        setattr(curso, campo, valor)
    curso.save()
    if competencias is not None:
        curso.competencias.set(competencias)
    if temas is not None:
        definir_temas(curso, temas, por=por)
    return curso


def definir_temas(curso, temas, por):
    """Troca os temas do curso e reindexa. A reindexacao e explicita porque coluna
    gerada nao alcanca M2M (spec 4.4).

    A autoridade e pode_editar_ficha, e nao pode_gerir_equipe: tema e campo da
    ficha (spec 4.3), e a ficha e de qualquer membro da equipe. Com a guarda
    antiga, um aluno salvando a ficha levava PermissionDenied vindo daqui de
    dentro, com a mensagem errada, ainda que a tela ja o tivesse autorizado.
    Continua recusando quem esta fora da equipe e curso fora de producao.
    """
    permissions.garante(permissions.pode_editar_ficha(por, curso), "Curso de outro professor.")
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


def _prevalida_anexo_de_video(upload, titulo, duracao_minutos, descricao=""):
    """Roda `Anexo.full_clean()` num espelho desligado, ANTES de a copia comecar.

    E a regra geral da qual a checagem de titulo em branco (em `concluir_upload`) e
    apenas um caso particular: *nenhuma recusa do Anexo pode acontecer depois da
    copia dos bytes*. `titulo` e `CharField(max_length=200)` e `duracao_minutos` e
    `PositiveSmallIntegerField`; violar qualquer um dos dois so estourava no
    `Anexo.objects.create()` da ultima linha, com o arquivo ja escrito em
    MEDIA_ROOT. A transacao desfaz as linhas, nao os bytes - e `limpar_arquivos_orfaos`
    parte de `Arquivo.objects`, que nesse ponto ja nao tem linha nenhuma apontando
    para eles: ninguem mais os encontraria, e nenhum alerta de cron dispararia,
    porque do lado do cron nada falhou.

    Conferir campo a campo aqui seria repetir `Anexo` numa segunda lista que
    divergiria dele na primeira mudanca; quem sabe o que o Anexo recusa e o
    proprio Anexo.
    """
    espelho = Anexo(
        entregavel=upload.entregavel,
        tipo_midia=TipoMidia.VIDEO,
        titulo=titulo,
        descricao=descricao,
        duracao_minutos=duracao_minutos,
        enviado_por=upload.usuario,
    )
    try:
        # `arquivo` fica de fora porque o Arquivo so nasce depois da copia - e a
        # copia e exatamente o que esta funcao existe para nao desperdicar.
        # `validate_unique`/`validate_constraints` desligados porque `Anexo` nao tem
        # nem unique nem constraint: ligados, custariam uma ida ao banco por upload
        # sem recusar nada. Se algum dia houver uma, ela precisa voltar para ca.
        espelho.full_clean(
            exclude=["arquivo"], validate_unique=False, validate_constraints=False
        )
    except ValidationError as erro:
        # `exclude` do `full_clean` nao alcanca o que `clean()` levanta (ele so filtra
        # `clean_fields`): a ausencia do arquivo chega aqui como erro do campo
        # `arquivo`, e e a unica que esperamos - as proximas linhas a resolvem.
        erros = {
            campo: mensagens
            for campo, mensagens in erro.message_dict.items()
            if campo != "arquivo"
        }
        if erros:
            raise ValidationError(erros)


@transaction.atomic
def concluir_upload(upload, titulo, duracao_minutos, descricao=""):
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
    # Este servico cria um Anexo de tipo VIDEO, e so o entregavel D o comporta. Sem
    # esta linha um .mp4 pousa em SLIDES e `validacoes.pendencias` da o entregavel
    # por satisfeito - `_slides` conta arquivos, e video e arquivo. A restricao
    # existia so no `{% if %}` do template, ou seja, so na tela.
    if upload.entregavel.tipo != TipoEntregavel.VIDEOS:
        raise ValidationError("Vídeo-aula só entra no entregável de vídeo-aulas.")
    # Titulo e duracao sao exigidos por Anexo.clean(), mas conferidos AQUI, antes de
    # qualquer byte ir para o disco: descobrir no `Anexo.objects.create()` da ultima
    # linha significaria o arquivo ja copiado para MEDIA_ROOT: a transacao desfaz a
    # linha, nao o arquivo em disco. E o orfao que `anexar` teve que consertar.
    if not (titulo or "").strip():
        # `"   "` nao esta em `empty_values`, entao o `full_clean` do espelho abaixo
        # ACEITA um titulo so de espacos. Esta linha e a unica que o recusa.
        raise ValidationError("Informe o título do vídeo.")
    # A duracao ausente ou zerada nao tem mais linha propria: quem a recusa e o
    # `Anexo.clean()` rodado no espelho, junto com tudo o mais que o Anexo recusa.
    _prevalida_anexo_de_video(upload, titulo, duracao_minutos, descricao)

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
    # Daqui para baixo os bytes JA estao em MEDIA_ROOT, e a transacao nao os alcanca.
    # A pre-validacao acima cobre o que da para prever; este `except` e a rede para o
    # que nao da - um IntegrityError, um PROTECT, um `clean()` novo que ninguem
    # lembrou de espelhar. Sem ele o arquivo fica em disco sem nenhuma linha de
    # Arquivo apontando para ele, e `limpar_arquivos_orfaos`, que varre
    # `Arquivo.objects`, nunca o veria. E o mesmo `arquivo.arquivo.delete(save=False)`
    # que `views/aluno.anexar` faz no seu ramo de erro; a licao nao tinha atravessado
    # a costura para o caminho do upload em blocos.
    try:
        arquivo.save()

        anexo = Anexo.objects.create(
            entregavel=upload.entregavel,
            tipo_midia=TipoMidia.VIDEO,
            titulo=titulo,
            descricao=descricao,
            arquivo=arquivo,
            duracao_minutos=duracao_minutos,
            enviado_por=upload.usuario,
        )
        # Fora da transacao de proposito. Um `unlink()` aqui dentro e a inversao
        # classica: se a transacao volta atras depois dele, a linha de
        # UploadEmAndamento ressuscita apontando para um arquivo que ja nao existe,
        # e o dono nao consegue nem retomar nem concluir. O disco so pode ser mexido
        # depois que o banco confirmou.
        #
        # Dentro do `try` porque `upload.delete()` tambem pode falhar: ali o Anexo ja
        # existe, mas a transacao volta atras e leva o Arquivo junto -- os bytes
        # ficariam em materiais/ sem linha nenhuma apontando para eles, que e
        # exatamente o vazamento que este bloco existe para impedir.
        transaction.on_commit(lambda: caminho.unlink(missing_ok=True))
        upload.delete()
    except Exception:
        try:
            arquivo.arquivo.delete(save=False)
        except Exception:
            # Limpar e melhor-esforco. Uma falha aqui (permissao, disco cheio) nao
            # pode substituir a excecao original: o aluno receberia 500 no lugar do
            # 400 que explica que o titulo passou de 200 caracteres.
            pass
        raise
    return anexo


@transaction.atomic
def abrir_nova_versao(curso, por, motivo):
    """Clona um curso publicado numa nova versao, na edicao corrente (spec 4.5).

    A versao anterior continua publicada e solicitavel durante todo o trabalho;
    ela so vira SUBSTITUIDO quando a nova for publicada.

    O que NAO vem junto, de proposito:
      - a equipe. "O professor monta a nova equipe. Pode ser outra turma inteira"
        (spec 4.5, passo 3): copiar os membros daria acesso de edicao a alunos de
        outro semestre e faria a versao nova nascer sem que ninguem a assumisse.
      - o historico de Revisao. Pertence a versao que o produziu; um parecer do
        professor sobre um material que ja mudou seria historico falso.
      - os bytes. Os anexos clonados apontam para o MESMO Arquivo (spec 4.6).
    """
    permissions.garante(
        permissions.pode_abrir_versao(por, curso),
        "Somente o professor responsável ou a coordenação abre nova versão.",
    )
    if curso.status != StatusCurso.PUBLICADO:
        raise ValidationError("Só se abre nova versão de curso publicado.")
    if not (motivo or "").strip():
        raise ValidationError("Informe o motivo da nova versão.")

    linhagem = curso.linhagem_id
    versoes = Curso.objects.filter(models.Q(pk=linhagem) | models.Q(raiz_id=linhagem))
    em_producao = versoes.exclude(
        status__in=(StatusCurso.PUBLICADO, StatusCurso.SUBSTITUIDO, StatusCurso.DESPUBLICADO)
    )
    if em_producao.exists():
        raise ValidationError("Já existe uma versão deste curso em produção.")

    from apps.edicoes.models import Edicao

    ultima = versoes.order_by("-versao").first()
    nova = Curso.objects.create(
        titulo=curso.titulo,
        resumo=curso.resumo,
        # Outro semestre, outra equipe (spec 4.5). Sem edicao corrente aberta,
        # herda a do curso de origem: `edicao` e obrigatorio no Curso, e abrir
        # versao nao pode depender de o coordenador ter lembrado da proxima edicao.
        edicao=Edicao.objects.corrente() or curso.edicao,
        professor_responsavel=curso.professor_responsavel,
        tipo_publico=curso.tipo_publico,
        etapa_ano=curso.etapa_ano,
        publico_descricao=curso.publico_descricao,
        referencial=curso.referencial,
        carga_horaria=curso.carga_horaria,
        formato=curso.formato,
        pre_requisitos=curso.pre_requisitos,
        palavras_chave=curso.palavras_chave,
        raiz_id=linhagem,
        versao=ultima.versao + 1,
        motivo_versao=motivo,
    )
    nova.competencias.set(curso.competencias.all())
    # definir_temas, e nao um temas.set() aqui: coluna gerada nao alcanca M2M
    # (spec 4.4), e e esse service que mantem juntos o vinculo e a reindexacao.
    # Foi uma tela escrevendo `temas` direto, sem reindexar, que sumiu com cursos
    # da busca no Plano 2.
    # `temas.set()` mais a reindexacao, e nao `definir_temas`: aquele e a operacao
    # da FICHA e por isso confere `pode_editar_ficha` de quem chama. Clonar um
    # curso nao e editar a ficha dele, e desde que o coordenador deixou de editar
    # ficha alheia (regra A) a copia levava PermissionDenied vindo de dentro, na
    # acao que a linha acima ja autorizou por `pode_abrir_versao`.
    #
    # A reindexacao continua explicita pelo motivo de sempre: coluna gerada nao
    # alcanca M2M (spec 4.4).
    nova.temas.set(curso.temas.all())
    atualizar_vetor_temas(nova)
    # A equipe de alunos nao vem (spec 4.5), mas o responsavel vem: ele e membro
    # de todo curso que responde (spec 4.1), e a v2 nasceria sem ninguem.
    MembroEquipe.objects.create(curso=nova, pessoa=nova.professor_responsavel)

    for entregavel in curso.entregaveis.prefetch_related("secoes", "anexos"):
        copia = Entregavel.objects.create(curso=nova, tipo=entregavel.tipo)
        secoes_clonadas = {}
        for secao in entregavel.secoes.all():
            secoes_clonadas[secao.pk] = Secao.objects.create(
                entregavel=copia, titulo=secao.titulo, ordem=secao.ordem, conteudo=secao.conteudo
            )
        for anexo in entregavel.anexos.all():
            Anexo.objects.create(
                entregavel=copia,
                # A secao CLONADA. Repetir anexo.secao apontaria o material da
                # versao nova para dentro da versao velha: editar uma mexeria na
                # outra, e apagar a nova arrastaria o anexo por CASCADE.
                secao=secoes_clonadas.get(anexo.secao_id),
                tipo_midia=anexo.tipo_midia,
                # Mesmo Arquivo: clonar um curso nao pode clonar gigabytes de
                # video (spec 4.6).
                arquivo=anexo.arquivo,
                url=anexo.url,
                titulo=anexo.titulo,
                descricao=anexo.descricao,
                referencia_bibliografica=anexo.referencia_bibliografica,
                rotulo=anexo.rotulo,
                tipo_pratica=anexo.tipo_pratica,
                duracao_minutos=anexo.duracao_minutos,
                enviado_por=anexo.enviado_por,
            )

    LogTransicaoCurso.objects.create(
        curso=nova,
        de_status=StatusCurso.RASCUNHO,
        para_status=StatusCurso.RASCUNHO,
        usuario=por,
        observacao=f"Versão {nova.versao} aberta a partir da versão {curso.versao}: {motivo}",
    )
    return nova


def remover_membro(curso, membro, por):
    """Tira alguem da equipe. Tira o acesso, nao apaga o trabalho (spec 4.1).

    Anexo, Secao e Revisao guardam quem fez cada coisa por FK propria, e
    MembroEquipe nao e pai de nada: apagar o vinculo nao toca nessas linhas, e o
    material continua com o nome de quem o produziu.
    """
    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    # A url traz os dois ids. Sem esta conferencia, quem tem permissao neste curso
    # apagaria o vinculo de alguem num curso alheio so trocando o membro_pk.
    if membro.curso_id != curso.pk:
        raise ValidationError("Este membro não é da equipe deste curso.")
    if membro.pessoa_id == curso.professor_responsavel_id:
        raise ValidationError(
            "O professor responsável não sai da equipe: o curso ficaria sem quem revisa."
        )
    if curso.status not in STATUS_EDITAVEIS:
        raise ValidationError("A equipe só muda enquanto o curso está em produção.")
    membro.delete()


def alocar_professor(curso, professor, por):
    """Poe um professor que ja tem conta na equipe de producao (spec 4.1).

    Sem convite, ao contrario de alocar_aluno: quem cria conta de professor e a
    coordenacao, e mandar primeiro acesso para quem ja entra no sistema seria
    convite que nao serve para nada.

    A recusa de None e explicita: o select pode chegar vazio, e sem ela o None
    seguiria para adicionar_membro e viraria 500 em vez de mensagem.
    """
    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    if professor is None or not professor.e_professor:
        raise ValidationError("Escolha um professor ou coordenador para a equipe.")
    return adicionar_membro(curso, professor, por=por)


def alocar_aluno_existente(curso, aluno, por):
    """Poe na equipe um aluno que ja tem conta (um curso nao e o primeiro dele).

    Sem convite, pelo mesmo motivo de `alocar_professor`: a conta ja foi aberta
    uma vez, e mandar primeiro acesso de novo seria convite que nao serve para
    nada. Quem nunca ativou continua com o convite que recebeu.

    Existe porque `alocar_aluno` recusa e-mail ja cadastrado, e recusa de
    proposito: um endereco digitado errado poria a pessoa errada numa equipe. A
    mensagem de la mandava pedir a coordenacao, e nao havia por onde. Escolher de
    uma lista fecha o buraco pelo outro lado - nao ha o que digitar errado.

    A recusa de None e explicita, como em `alocar_professor`: o select pode chegar
    vazio, e sem ela o None seguiria para adicionar_membro e viraria 500.
    """
    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    if aluno is None or not aluno.e_aluno:
        raise ValidationError("Escolha um aluno para a equipe.")
    return adicionar_membro(curso, aluno, por=por)


@transaction.atomic
def alocar_aluno(curso, email, por, base_url=""):
    """Cria a conta do aluno com o e-mail e mais nada, vincula a equipe e envia o
    convite (regras 2 e 3 do Plano 5).

    So o e-mail, como em `contas.services.criar_professor`: nome, CPF, matricula e
    telefone vem no primeiro acesso, escritos pela propria pessoa. O professor
    digitava o nome do aluno aqui, e digitar o nome de outra pessoa e onde nasce
    erro de grafia que ninguem corrige depois - o nome aparece no credito publico
    do curso.

    Os tres passos acontecem juntos: uma conta criada sem convite fica
    inalcancavel -- ninguem consegue ativa-la, e o e-mail fica queimado, porque a
    segunda tentativa bate na recusa de e-mail ja cadastrado.

    A recusa e por e-mail existente, e nao vinculo da conta que ja existe: um
    endereco digitado errado poria a pessoa errada numa equipe, e o professor nao
    teria como perceber.
    """
    # Importes adiados, e nao no topo: `contas.services` nao pode ser importado na
    # carga deste modulo sem fechar um ciclo (`contas` nao conhece `cursos`, e este
    # arquivo ja usa o mesmo padrao para `Usuario` em `definir_temas`).
    from apps.contas.models import Usuario
    from apps.contas.services import convidar

    permissions.garante(
        permissions.pode_gerir_equipe(por, curso),
        "Somente o professor responsável monta a equipe.",
    )
    email = (email or "").strip().lower()
    # Recusa explicita antes do create_user: ele levanta ValueError para e-mail
    # vazio, e a view so captura ValidationError -- um POST sem e-mail virava 500.
    # Era o que `test_equipe_sem_aluno_selecionado_nao_quebra` prendia no contrato
    # antigo, e a regra 2 do Plano 5 quase a perdeu junto com o contrato.
    if not email:
        raise ValidationError({"email": "Informe o e-mail do aluno."})

    if Usuario.objects.filter(email__iexact=email).exists():
        raise ValidationError(
            "Já existe conta com este e-mail. Confira o endereço ou peça à "
            "coordenação para vincular a conta existente."
        )

    # `password=None` e o que deixa a senha inutilizavel: `set_password(None)`
    # grava um hash prefixado com "!" que nenhuma entrada satisfaz. So o convite
    # abre a conta.
    #
    # Uma guarda so, de proposito. Havia aqui uma chamada extra que zerava a senha
    # depois do create_user, e as duas se mascaravam: apagar qualquer uma deixava
    # a outra garantindo o mesmo resultado, e nenhum teste distinguia qual estava
    # valendo. Nao acrescente a segunda de volta -- prefira confiar nesta linha,
    # que o teste consegue derrubar sozinha.
    aluno = Usuario.objects.create_user(
        email=email, nome_completo="", papel=Usuario.ALUNO, password=None
    )

    membro = adicionar_membro(curso, aluno, por=por)
    convidar(aluno, por=por, base_url=base_url)
    return membro
