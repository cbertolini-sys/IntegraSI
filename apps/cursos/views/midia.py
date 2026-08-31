"""Entrega protegida de arquivo (spec 8, 10).

Material de curso nunca fica exposto em MEDIA_URL: quem pede um arquivo passa por
aqui, e so entao o nginx transmite os bytes por `X-Accel-Redirect` - um caminho
que o navegador nao consegue pedir sozinho, porque o `location /protegido/` do
nginx e marcado `internal;` (obrigacao da Task 8, sem a qual esta view inteira
vira enfeite).
"""

from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from apps.cursos import permissions
from apps.cursos.models import Arquivo

# Abrir no navegador so o que e seguro renderizar. HTML ou SVG servido inline a
# partir do nosso dominio e vetor de XSS (spec 8). PNG e JPEG ficam de fora de
# proposito: a lista e dos tipos que a spec manda abrir, nao de tudo o que o
# navegador saberia exibir.
INLINE = {"application/pdf", "video/mp4"}

# Prefixo do `location internal;` do nginx. O caminho e sempre montado a partir do
# nome que o FileField gravou (`materiais/<hex>/<hex>`, vindo do UUID), nunca do
# `nome_original`, que e texto escolhido por quem enviou.
PREFIXO_INTERNO = "/protegido/"


@login_required
@require_GET
def baixar(request, identificador):
    arquivo = get_object_or_404(Arquivo, identificador=identificador)
    permissions.garante(
        permissions.pode_baixar_arquivo(request.user, arquivo),
        "Material de curso de outra equipe.",
    )

    disposicao = "inline" if arquivo.mime in INLINE else "attachment"
    # safe="": nem barra nem quebra de linha do nome escolhido pelo usuario podem
    # chegar cruas a um cabecalho de resposta.
    cabecalho = f"{disposicao}; filename*=UTF-8''{quote(arquivo.nome_original, safe='')}"

    if not settings.USAR_X_ACCEL:
        # Desenvolvimento: sem nginx na frente, o Django entrega mesmo.
        resposta = FileResponse(arquivo.arquivo.open("rb"), content_type=arquivo.mime)
        resposta["Content-Disposition"] = cabecalho
        return resposta

    # Producao: quem transmite e o nginx. Um GB pelo processo Python prende um
    # worker por dez minutos e tres downloads simultaneos derrubam o servidor.
    resposta = HttpResponse(content_type=arquivo.mime)
    resposta["X-Accel-Redirect"] = PREFIXO_INTERNO + quote(arquivo.arquivo.name)
    resposta["Content-Disposition"] = cabecalho
    return resposta
