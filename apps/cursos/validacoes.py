from django.core.exceptions import ValidationError

from apps.cursos.choices import Rotulo, TipoEntregavel, TipoMidia, TipoPratica

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
    }
    # regras cobre todo TipoEntregavel; um tipo fora do enum e erro de dado, nao de
    # fluxo, entao o KeyError sobe cru para quem chama (Tasks 7, 9 e 10).
    return regras[entregavel.tipo](entregavel)


def _arquivos(entregavel):
    return entregavel.anexos.exclude(tipo_midia=TipoMidia.LINK)


def _plano_de_ensino(entregavel):
    faltas = []
    if not _arquivos(entregavel).filter(arquivo__mime="application/pdf").exists():
        faltas.append("Anexe o plano de ensino em PDF.")
    if not entregavel.secoes.exclude(conteudo="").exists():
        faltas.append("Preencha ao menos uma seção do plano de ensino.")
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
    if curso.referencial_id:
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
    videos = list(entregavel.anexos.filter(tipo_midia=TipoMidia.VIDEO))
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
    if not _arquivos(entregavel).exists():
        return ["Anexe ao menos um arquivo de slides."]
    return []
