from django.db import models


class StatusCurso(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    EM_PRODUCAO = "EM_PRODUCAO", "Em produção"
    AGUARDANDO_COORDENADOR = "AGUARDANDO_COORDENADOR", "Aguardando coordenador"
    DEVOLVIDO = "DEVOLVIDO", "Devolvido pelo coordenador"
    PUBLICADO = "PUBLICADO", "Publicado"
    DESPUBLICADO = "DESPUBLICADO", "Despublicado"
    SUBSTITUIDO = "SUBSTITUIDO", "Substituído por nova versão"


class StatusEntregavel(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    EM_REVISAO = "EM_REVISAO", "Em revisão"
    APROVADO = "APROVADO", "Aprovado"
    DEVOLVIDO = "DEVOLVIDO", "Devolvido"


class TipoEntregavel(models.TextChoices):
    """Os seis pacotes do roteiro, na ordem em que ele os pede.

    A numeracao vive no ROTULO, e nunca no valor gravado. Rotulo e texto e pode ser
    renumerado; valor gravado nunca muda, senao toda linha ja no banco vira lixo.
    Foi por isso que a passagem de letras para numeros nao precisou de migracao de
    dados: PLANO_ENSINO continua PLANO_ENSINO.

    A ORDEM DE DECLARACAO importa: `ORDEM_DO_ROTEIRO`, em models/producao.py,
    monta a ordenacao das telas a partir dela. Reordenar aqui reordena a tela.
    """

    PLANO_ENSINO = "PLANO_ENSINO", "1 - Plano de Ensino e Mapeamento Pedagógico"
    SLIDES = "SLIDES", "2 - Slides e Apresentações"
    VIDEOS = "VIDEOS", "3 - Vídeo-Aulas"
    CARDS = "CARDS", "4 - Infográficos e Cards Educativos"
    CADERNO = "CADERNO", "5 - Caderno de Exercícios e Atividades Práticas"
    AVALIACAO = "AVALIACAO", "6 - Avaliação"


class TipoPublico(models.TextChoices):
    ESCOLAR = "ESCOLAR", "Etapa escolar"
    COMUNITARIO = "COMUNITARIO", "Público da comunidade"


class Formato(models.TextChoices):
    PRESENCIAL = "PRESENCIAL", "Presencial"
    HIBRIDO = "HIBRIDO", "Híbrido"
    ONLINE = "ONLINE", "Online"


class TipoMidia(models.TextChoices):
    ARQUIVO = "ARQUIVO", "Arquivo"
    VIDEO = "VIDEO", "Vídeo"
    LINK = "LINK", "Link externo"


class Rotulo(models.TextChoices):
    NENHUM = "NENHUM", "Sem rótulo"
    SEM_GABARITO = "SEM_GABARITO", "Versão sem gabarito"
    COM_GABARITO = "COM_GABARITO", "Versão com gabarito"


class TipoPratica(models.TextChoices):
    NENHUM = "NENHUM", "Não se aplica"
    PLUGADA = "PLUGADA", "Atividade plugada"
    DESPLUGADA = "DESPLUGADA", "Atividade desplugada"
    AMBAS = "AMBAS", "Plugada e desplugada"


# Onde a ficha do curso ainda pode mudar. PUBLICADO nao entra: curso no catalogo
# muda por nova versao (spec 4.5), nunca por edicao no lugar. Vive aqui, e nao em
# services.py, porque permissions.py precisa dele e nao pode importar services
# (services importa permissions, e o ciclo fecharia).
STATUS_EDITAVEIS = (StatusCurso.RASCUNHO, StatusCurso.EM_PRODUCAO, StatusCurso.DEVOLVIDO)


# Curso que ainda esta sendo feito. Nao e o complemento de PUBLICADO: DESPUBLICADO
# ja foi ao catalogo e voltou, e SUBSTITUIDO e a versao anterior de um curso que
# seguiu adiante. Nenhum dos dois e trabalho por fazer, e contar os dois aqui
# encheria o painel do professor de curso que ele nao vai abrir.
#
# AGUARDANDO_COORDENADOR entra, ao contrario de STATUS_EDITAVEIS: o curso nao pode
# mais ser editado, mas continua sendo trabalho aberto do professor ate a
# coordenacao decidir.
STATUS_EM_DESENVOLVIMENTO = (
    StatusCurso.RASCUNHO,
    StatusCurso.EM_PRODUCAO,
    StatusCurso.AGUARDANDO_COORDENADOR,
    StatusCurso.DEVOLVIDO,
)


# Quantas palavras-chave o curso precisa ter para ir ao catalogo. Vive aqui, e nao
# em validacoes.py, porque o formulario tambem precisa dela para desenhar as
# caixas, e choices.py nao importa nada do app.
PALAVRAS_CHAVE_EXIGIDAS = 5
