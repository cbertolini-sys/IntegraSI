import hashlib
from pathlib import Path

from django.core.exceptions import ValidationError

MEGA = 1024 * 1024
GIGA = 1024 * MEGA

# Teto do video (spec 8). Vive aqui, e nao no model, porque quem valida o nome e o
# tamanho declarados antes de abrir o upload e `valida_upload`.
LIMITE_VIDEO = 1 * GIGA

# Tamanho do bloco que o navegador manda por requisicao no upload fatiado. Vive
# aqui, no Python, e chega ao `static/js/upload.js` pelo `data-tamanho-bloco` do
# formulario: uma segunda copia dentro do JS divergiria em silencio da primeira,
# e um comentario dizendo "precisa ser o mesmo valor" nao e mecanismo nenhum.
#
# Precisa caber em DATA_UPLOAD_MAX_MEMORY_SIZE — acima do teto o Django recusa o
# corpo antes de a view rodar (test_upload_integracao prende a relacao).
TAMANHO_BLOCO = 5 * MEGA

# Assinatura no inicio do arquivo -> mime. Conferir o conteudo, e nao a extensao,
# e o que impede um executavel renomeado para .pdf de entrar no sistema (spec 8).
ASSINATURAS = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"PK\x03\x04", "application/zip"),  # pptx, odp e docx sao zip
]
# MP4 nao entra na tabela acima: nao tem assinatura no inicio. O primeiro campo e
# o tamanho da caixa, e o tipo ('ftyp') vem nos bytes 4 a 8 — ver `detecta_mime`.
CAIXA_FTYP = slice(4, 8)

LIMITES = {
    "application/pdf": 20 * MEGA,
    "image/png": 10 * MEGA,
    "image/jpeg": 10 * MEGA,
    "application/zip": 50 * MEGA,
    "video/mp4": LIMITE_VIDEO,
}

# DIVERGENCIA REGISTRADA da spec 8, decidida na revisao de branch do Plano 4. A
# spec diz "outros formatos [de video] sao aceitos mas apenas baixados"; aqui so
# `.mp4` entra, e `.mov`/`.webm`/`.avi` sao recusados no sistema inteiro (o upload
# em blocos e o unico caminho que cria `TipoMidia.VIDEO`). A metade "download-only"
# da frase continua valendo — `views/midia.INLINE` tem so PDF e MP4, e todo o resto
# ja sai como `attachment`. O que foi decidido nao implementar e a aceitacao dos
# outros conteineres. A justificativa esta na spec, anotada na propria frase; em
# resumo: a validacao e por assinatura, e conteiner que nao sabemos reconhecer e
# conteiner dentro do qual nao sabemos recusar um executavel; a recusa por extensao
# acontece antes do primeiro byte, o que so uma lista fechada permite; e sem
# transcodificacao um `.mov` chega como um video que o professor nao consegue
# assistir na revisao. Reabrir a decisao e acrescentar assinatura, teto e extensao
# do conteiner nos tres dicionarios deste modulo, e nada mais.
EXTENSOES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pptx": "application/zip",
    ".odp": "application/zip",
    ".docx": "application/zip",
    ".mp4": "video/mp4",
}


def detecta_mime(cabecalho):
    """Devolve o mime pela assinatura do arquivo, ou None se nao reconhecer."""
    for assinatura, mime in ASSINATURAS:
        if cabecalho.startswith(assinatura):
            return mime
    if cabecalho[CAIXA_FTYP] == b"ftyp":
        return "video/mp4"
    return None


def _confere_limite(mime, tamanho):
    """Teto por tipo (spec 8). Vive numa funcao so porque os dois lados do upload em
    blocos precisam dele: o declarado, na abertura, e o real, na conclusao."""
    limite = LIMITES[mime]
    if tamanho > limite:
        raise ValidationError(f"Arquivo acima do limite de {limite // MEGA} MB para este tipo.")


def valida_declaracao(nome, tamanho):
    """Confere o que da para conferir antes do primeiro byte: a extensao e o tamanho
    que o cliente declara. Devolve o mime que a extensao promete.

    Existe porque `valida_upload` precisa do cabecalho e so pode rodar no fim. Sem
    ela o teto por tipo ficava sem dono no caminho da abertura: um `.pdf` declarado
    com 900 MB nascia (900 MB cabem no unico teto que o modelo conhece, o do video),
    passava meia hora enchendo o disco e so entao ouvia que PDF para em 20 MB.

    O que ela NAO faz e conferir conteudo: nome declarado nao prova nada sobre os
    bytes que vao chegar. Essa parte continua obrigatoria em `valida_upload`.
    """
    mime = EXTENSOES.get(Path(nome).suffix.lower())
    if mime is None:
        raise ValidationError("Tipo de arquivo não reconhecido ou não permitido.")
    if tamanho <= 0:
        # Um upload de 0 byte nasceria `completo` sem nunca tocar o disco, e a
        # conclusao iria stat() um arquivo parcial que nao existe.
        raise ValidationError("Arquivo vazio.")
    _confere_limite(mime, tamanho)
    return mime


def valida_upload(nome, tamanho, cabecalho):
    """Confere tipo e tamanho e devolve o mime. Levanta ValidationError se recusar."""
    mime = detecta_mime(cabecalho)
    if mime is None:
        raise ValidationError("Tipo de arquivo não reconhecido ou não permitido.")
    esperado = EXTENSOES.get(Path(nome).suffix.lower())
    if esperado != mime:
        raise ValidationError(
            f"O conteúdo do arquivo não corresponde à extensão {Path(nome).suffix}."
        )
    _confere_limite(mime, tamanho)
    return mime


def calcula_hash(upload):
    """SHA-256 do conteudo, lido em pedacos (upload.chunks()) em vez de inteiro na
    memoria de uma vez: bastava para os 50 MB de hoje, mas e o mesmo caminho que o
    upload de 1 GB do Plano 4 vai herdar, e a spec exige que 1 GB nunca sente
    inteiro num worker Python (spec 8; item 8 da revisao de branco). Devolve o
    ponteiro do upload ao inicio no final, para quem for salvar o conteudo em
    seguida (ex.: FileField.save())."""
    hasher = hashlib.sha256()
    for pedaco in upload.chunks():
        hasher.update(pedaco)
    upload.seek(0)
    return hasher.hexdigest()
