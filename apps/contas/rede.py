"""De onde vem a requisicao, para os limites por IP.

Mora em `contas`, e nao em `catalogo`, porque agora dois apps precisam dela: o
formulario publico de solicitacao e o login. `contas` e o app base, entao os dois
podem importar daqui sem inverter a dependencia de mao unica do projeto.
"""

from django.conf import settings
from django.core.validators import validate_ipv46_address
from django.core.exceptions import ValidationError


def ip_da_requisicao(request):
    """De quem é esta requisição, para efeito do limite por IP (spec 10).

    Atrás do nginx, `REMOTE_ADDR` é sempre 127.0.0.1 - olhar só para ele
    transformaria o limite por IP num limite global, e um único visitante
    fecharia o formulário para todo mundo. O IP real chega em `X-Forwarded-For`.

    Esse cabeçalho é uma lista onde cada proxy **acrescenta ao fim**: o último
    elemento é o que o nosso nginx escreveu; os anteriores são texto que o
    cliente mandou. Ler o *primeiro* (como este código fazia) entrega o limite
    ao atacante: `X-Forwarded-For: 9.9.9.9` diferente a cada requisição dá cota
    nova toda vez e o limite nunca dispara. Por isso lemos o último.

    O deploy ainda sobrescreve o cabeçalho no proxy (`$remote_addr`, ver
    `deploy/nginx.conf`), de modo que as duas camadas teriam que estar erradas ao
    mesmo tempo. E sem proxy nenhum na frente o cabeçalho é do cliente e não vale
    nada: `CONFIAR_NO_PROXY` é quem diz se há proxy.
    """
    if settings.CONFIAR_NO_PROXY:
        encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if encaminhado:
            candidato = encaminhado.split(",")[-1].strip()
            try:
                # ip_origem é um inet no PostgreSQL: lixo aqui derruba o POST com
                # DataError. O formulário público é a única porta anônima que
                # escreve no banco (spec 10) e não pode virar um 500 por causa de
                # um cabeçalho malformado.
                validate_ipv46_address(candidato)
            except ValidationError:
                return request.META.get("REMOTE_ADDR")
            return candidato
    return request.META.get("REMOTE_ADDR")


