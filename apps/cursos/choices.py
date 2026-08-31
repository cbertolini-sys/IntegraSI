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
    PLANO_ENSINO = "PLANO_ENSINO", "A - Plano de Ensino e Mapeamento Pedagógico"
    CARDS = "CARDS", "B - Infográficos e Cards Educativos"
    CADERNO = "CADERNO", "C - Caderno de Exercícios e Atividades Práticas"
    VIDEOS = "VIDEOS", "D - Vídeo-Aulas"
    SLIDES = "SLIDES", "E - Slides e Apresentações"


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


# Quantas palavras-chave o curso precisa ter para ir ao catalogo. Vive aqui, e nao
# em validacoes.py, porque o formulario tambem precisa dela para desenhar as
# caixas, e choices.py nao importa nada do app.
PALAVRAS_CHAVE_EXIGIDAS = 5
