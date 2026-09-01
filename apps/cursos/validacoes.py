import re

from django.core.exceptions import ValidationError

from apps.cursos.choices import (
    PALAVRAS_CHAVE_EXIGIDAS,
    Rotulo,
    TipoEntregavel,
    TipoMidia,
    TipoPratica,
)

DURACAO_MINIMA = 5
DURACAO_MAXIMA = 10


def pendencias(entregavel):
    """Lista o que falta para o entregavel poder ir a revisao (spec 6).

    Devolve textos prontos para mostrar ao aluno. Lista vazia significa que pode
    enviar. E lista, e nao um sim/nao, porque a mensagem e o produto: e ela que
    evita a ida e volta com o professor.
    """
    regras = {
        TipoEntregavel.PLANO_ENSINO: _plano_de_ensino,
        TipoEntregavel.CARDS: _cards,
        TipoEntregavel.CADERNO: _caderno,
        TipoEntregavel.VIDEOS: _videos,
        TipoEntregavel.SLIDES: _slides,
        TipoEntregavel.AVALIACAO: _avaliacao,
    }
    # regras cobre todo TipoEntregavel; um tipo fora do enum e erro de dado, nao de
    # fluxo, entao o KeyError sobe cru para quem chama (Tasks 7, 9 e 10).
    return regras[entregavel.tipo](entregavel)


def _arquivos(entregavel):
    """Os anexos que nao sao link, filtrados em Python.

    `.exclude()` no banco seria o natural, e era o que estava aqui: o problema e
    que `prefetch_related` so guarda o resultado de `.all()`, entao qualquer
    `.filter()`/`.exclude()`/`.exists()` desce ao banco de novo e desfaz o
    prefetch. O painel do curso chama `pendencias` nos seis entregaveis, e eram
    seis consultas que o prefetch nao alcancava. `Curso.praticas` ja tinha
    aprendido isso e diz o mesmo no proprio docstring.

    Sao poucos anexos por entregavel; filtrar em memoria custa menos que a viagem.
    """
    return [a for a in entregavel.anexos.all() if a.tipo_midia != TipoMidia.LINK]


def _tem_texto(html):
    """Uma secao com `<p></p>` esta vazia para quem le, e o campo nao esta em branco.

    O editor grava marcacao mesmo quando ninguem escreveu nada, entao comparar com
    string vazia deixaria o plano passar em branco.
    """
    return bool(re.sub(r"<[^>]*>", "", html or "").replace("\xa0", " ").strip())


def _plano_de_ensino(entregavel):
    """TODAS as secoes precisam estar escritas.

    Antes bastava uma. O plano de ensino e o documento que descreve o curso
    inteiro: ementa sem metodologia, ou sem avaliacao, nao e plano, e era esse o
    caso que passava.

    Nao ha mais cobranca de anexo: o plano e escrito nas secoes, e a tela deixou de
    oferecer materiais. Cobrar PDF aqui travaria o envio para sempre.

    A mensagem nomeia as secoes que faltam, e nao diz apenas que falta alguma: e a
    mensagem que evita a ida e volta com o professor (spec 6).
    """
    faltas = []
    vazias = [s.titulo for s in entregavel.secoes.all() if not _tem_texto(s.conteudo)]
    if vazias:
        faltas.append("Preencha estas seções do plano de ensino: " + ", ".join(vazias) + ".")
    faltas.extend(dados_do_curso(entregavel.curso))
    return faltas


def dados_do_curso(curso):
    """Campos que sao do Curso, nao do Entregavel (spec 4.3): a validacao le
    entregavel.curso. Publica desde o inicio (sem underscore) porque a Task 7 tambem
    chama esta funcao na submissao ao coordenador: o curso pode ser editado depois do
    plano aprovado, entao a mesma checagem precisa rodar de novo la fora."""
    faltas = []
    if not (curso.resumo or "").strip():
        faltas.append("Escreva o resumo do curso.")
    if not curso.publico_alvo:
        faltas.append("Defina o público-alvo do curso.")
    if not curso.carga_horaria:
        faltas.append("Informe a carga horária do curso.")
    if not curso.formato:
        faltas.append("Informe o formato do curso.")
    # Cobrado aqui, e nao no formulario: a ficha salva pela metade de proposito, e
    # quem escreveu so o resumo nao pode perder o que digitou por ainda nao ter
    # pensado em cinco palavras.
    palavras = [p for p in (curso.palavras_chave or "").split(",") if p.strip()]
    if len(palavras) < PALAVRAS_CHAVE_EXIGIDAS:
        faltas.append(
            f"Informe as {PALAVRAS_CHAVE_EXIGIDAS} palavras-chave do curso; "
            f"há {len(palavras)}."
        )
    if curso.referencial_id:
        # A exigencia vem do DADO, e nao da sigla: nenhuma tela pode pressupor
        # BNCC (spec 4.2). Referencial sem competencias carregadas nao trava curso
        # nenhum, e um referencial futuro que nao separe por etapa tambem nao.
        if curso.referencial.organiza_por_etapa and not curso.etapa_ano:
            faltas.append(
                f"{curso.referencial.nome} organiza o que oferece por etapa escolar: "
                "defina o público escolar e a etapa, ou deixe o curso sem referencial."
            )
        try:
            curso.referencial.valida_quantidade(curso.competencias.count())
        except ValidationError as erro:
            faltas.append(erro.messages[0])
    return faltas


def _cards(entregavel):
    anexos = list(_arquivos(entregavel))
    if not anexos:
        return ["Anexe ao menos um card."]
    sem_referencia = [a.titulo for a in anexos if not a.referencia_bibliografica.strip()]
    if sem_referencia:
        return [
            "Informe a referência bibliográfica em: " + ", ".join(sem_referencia) + "."
        ]
    return []


def _caderno(entregavel):
    anexos = list(_arquivos(entregavel))
    faltas = []
    if not any(a.rotulo == Rotulo.SEM_GABARITO for a in anexos):
        faltas.append("Anexe a versão sem gabarito.")
    if not any(a.rotulo == Rotulo.COM_GABARITO for a in anexos):
        faltas.append("Anexe a versão com gabarito.")
    plugadas = {TipoPratica.PLUGADA, TipoPratica.AMBAS}
    desplugadas = {TipoPratica.DESPLUGADA, TipoPratica.AMBAS}
    if not any(a.tipo_pratica in plugadas for a in anexos):
        faltas.append("Inclua ao menos uma atividade plugada.")
    if not any(a.tipo_pratica in desplugadas for a in anexos):
        faltas.append("Inclua ao menos uma atividade desplugada.")
    return faltas


def _videos(entregavel):
    # `.all()` pelo mesmo motivo de `_arquivos`: e o unico que o prefetch guarda.
    videos = [a for a in entregavel.anexos.all() if a.tipo_midia == TipoMidia.VIDEO]
    faltas = []
    if not 2 <= len(videos) <= 3:
        faltas.append(f"Envie de 2 a 3 vídeos; há {len(videos)}.")
    fora_da_faixa = [
        v.titulo for v in videos
        if not (DURACAO_MINIMA <= (v.duracao_minutos or 0) <= DURACAO_MAXIMA)
    ]
    if fora_da_faixa:
        faltas.append(
            f"Cada vídeo deve ter de {DURACAO_MINIMA} a {DURACAO_MAXIMA} minutos; "
            f"fora da faixa: {', '.join(fora_da_faixa)}."
        )
    return faltas


def _slides(entregavel):
    if not _arquivos(entregavel):
        return ["Anexe ao menos um arquivo de slides."]
    return []


def _avaliacao(entregavel):
    """O material de avaliacao do curso: instrumento, roteiro de correcao, rubrica.

    Aceita link, e nao so arquivo (por isso `anexos`, e nao `_arquivos`): um
    instrumento de avaliacao pode ser um formulario online, e exigir upload
    obrigaria a equipe a imprimir para anexar. A REGRA continua aceitando; o
    formulario e que deixou de oferecer o campo de link, a pedido, entao a
    mensagem abaixo nao fala mais dele - mandar preencher um campo que a tela
    nao tem e pior que nao dizer nada.

    Nao e a nota de quem assiste ao curso, que pertence ao modulo de execucao
    (spec 1.1) junto com frequencia e certificado.
    """
    if not entregavel.anexos.all():
        return ["Anexe o material de avaliação."]
    return []
