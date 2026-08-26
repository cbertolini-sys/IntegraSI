from django.db import models


class StatusCurso(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    EM_PRODUCAO = "EM_PRODUCAO", "Em producao"
    AGUARDANDO_COORDENADOR = "AGUARDANDO_COORDENADOR", "Aguardando coordenador"
    DEVOLVIDO = "DEVOLVIDO", "Devolvido pelo coordenador"
    PUBLICADO = "PUBLICADO", "Publicado"
    DESPUBLICADO = "DESPUBLICADO", "Despublicado"
    SUBSTITUIDO = "SUBSTITUIDO", "Substituido por nova versao"


class StatusEntregavel(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    EM_REVISAO = "EM_REVISAO", "Em revisao"
    APROVADO = "APROVADO", "Aprovado"
    DEVOLVIDO = "DEVOLVIDO", "Devolvido"


class TipoEntregavel(models.TextChoices):
    PLANO_ENSINO = "PLANO_ENSINO", "A - Plano de Ensino e Mapeamento Pedagogico"
    CARDS = "CARDS", "B - Infograficos e Cards Educativos"
    CADERNO = "CADERNO", "C - Caderno de Exercicios e Atividades Praticas"
    VIDEOS = "VIDEOS", "D - Video-Aulas"
    SLIDES = "SLIDES", "E - Slides e Apresentacoes"


class TipoPublico(models.TextChoices):
    ESCOLAR = "ESCOLAR", "Etapa escolar"
    COMUNITARIO = "COMUNITARIO", "Publico da comunidade"


class Formato(models.TextChoices):
    PRESENCIAL = "PRESENCIAL", "Presencial"
    HIBRIDO = "HIBRIDO", "Hibrido"
    ONLINE = "ONLINE", "Online"


class TipoMidia(models.TextChoices):
    ARQUIVO = "ARQUIVO", "Arquivo"
    VIDEO = "VIDEO", "Video"
    LINK = "LINK", "Link externo"


class Rotulo(models.TextChoices):
    NENHUM = "NENHUM", "Sem rotulo"
    SEM_GABARITO = "SEM_GABARITO", "Versao sem gabarito"
    COM_GABARITO = "COM_GABARITO", "Versao com gabarito"


class TipoPratica(models.TextChoices):
    NENHUM = "NENHUM", "Nao se aplica"
    PLUGADA = "PLUGADA", "Atividade plugada"
    DESPLUGADA = "DESPLUGADA", "Atividade desplugada"
    AMBAS = "AMBAS", "Plugada e desplugada"
