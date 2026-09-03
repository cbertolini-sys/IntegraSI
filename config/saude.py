"""Verificação de saúde para monitoração externa.

Mora em `config`, e não num app: não é funcionalidade de domínio nenhum, e um app
novo entraria na tabela de camadas de `tests/test_arquitetura.py` para hospedar
uma view de três linhas.

O `Restart=always` do systemd reergue o processo que morre. O que ele não vê é o
processo VIVO e inútil: banco fora do ar, pool esgotado, migração pela metade. É
esse o caso que esta rota cobre, e por isso ela toca o banco em vez de responder
"ok" de graça - um 200 que não prova nada é pior que rota nenhuma, porque a
monitoração passa a dizer que está tudo bem.
"""

from django.db import connection
from django.http import HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def saude(request):
    """200 se o processo alcança o banco, 503 se não alcança.

    Pública de propósito: não diz nada que já não se saiba de fora, e monitoração
    não faz login. Se o campus quiser restringir, o lugar é o nginx (um
    `allow`/`deny` no `location = /saude/`), e não uma senha aqui dentro.

    A resposta é texto curto e sem detalhe do erro: quem monitora precisa do
    código de status, e a mensagem do banco é informação de dentro do servidor.
    """
    try:
        connection.ensure_connection()
    except Exception:
        # Sem `raise`: o objetivo é responder 503, e não estourar. O traceback
        # sai pelo log da aplicação, que é onde ele serve para alguém.
        return HttpResponse("sem banco", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
