from pathlib import Path

from django.core.exceptions import ValidationError

MEGA = 1024 * 1024

# Assinatura no inicio do arquivo -> mime. Conferir o conteudo, e nao a extensao,
# e o que impede um executavel renomeado para .pdf de entrar no sistema (spec 8).
ASSINATURAS = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"PK\x03\x04", "application/zip"),  # pptx, odp e docx sao zip
]

LIMITES = {
    "application/pdf": 20 * MEGA,
    "image/png": 10 * MEGA,
    "image/jpeg": 10 * MEGA,
    "application/zip": 50 * MEGA,
}

EXTENSOES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".pptx": "application/zip",
    ".odp": "application/zip",
    ".docx": "application/zip",
}


def detecta_mime(cabecalho):
    """Devolve o mime pela assinatura do arquivo, ou None se nao reconhecer."""
    for assinatura, mime in ASSINATURAS:
        if cabecalho.startswith(assinatura):
            return mime
    return None


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
    limite = LIMITES[mime]
    if tamanho > limite:
        raise ValidationError(f"Arquivo acima do limite de {limite // MEGA} MB para este tipo.")
    return mime
