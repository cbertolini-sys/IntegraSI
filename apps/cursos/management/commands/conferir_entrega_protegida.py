"""Confere, contra um servidor de verdade, se a entrega de material esta fechada.

Esta e a unica conferencia do sistema que nenhum teste da suite consegue fazer, e
a mais perigosa de esquecer.

O Django nunca transmite material: ele confere a permissao e responde com o
cabecalho `X-Accel-Redirect`, e quem envia os bytes e o nginx (spec 8, 10). Isso
so e seguro porque o `location /protegido/` do nginx e marcado `internal;` --
sem essa diretiva, qualquer pessoa busca a URL direto e contorna a checagem de
permissao inteira, enquanto a view do Django segue perfeitamente correta e todos
os testes seguem verdes.

Roda depois de instalar, depois de mexer no nginx, e por cron se quiser dormir
tranquilo. Codigo de saida diferente de zero quando reprova, para o cron avisar.
"""

import urllib.error
import urllib.request

from django.core.management.base import BaseCommand, CommandError

from apps.cursos.views.midia import PREFIXO_INTERNO

# Recusas aceitaveis: as duas significam "o navegador nao alcanca esta rota".
FECHADO = {401, 403, 404}


class Command(BaseCommand):
    help = "Confere se /protegido/ do nginx esta marcado internal; num servidor no ar."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            required=True,
            help="Endereco do servidor, ex.: https://integrasi.ufsm.br",
        )
        parser.add_argument("--timeout", type=int, default=10)

    def handle(self, *args, **opcoes):
        base = opcoes["base_url"].rstrip("/")
        # O caminho sai do proprio codigo: trocar PREFIXO_INTERNO sem trocar o
        # nginx e um dos jeitos de abrir a porta, e a conferencia tem de seguir o
        # codigo, nao uma string repetida aqui.
        alvo = f"{base}{PREFIXO_INTERNO}conferencia-de-seguranca.pdf"

        # Sem cookie e sem sessao de proposito: a pergunta e "um estranho
        # consegue?". Mandar credencial junto responderia outra pergunta.
        requisicao = urllib.request.Request(alvo, method="GET")

        try:
            with urllib.request.urlopen(requisicao, timeout=opcoes["timeout"]) as resposta:
                status = resposta.status
        except urllib.error.HTTPError as erro:
            status = erro.code
        except urllib.error.URLError as erro:
            raise CommandError(
                f"Não foi possível falar com {alvo}: {erro.reason}. "
                "Sem resposta não há conclusão -- a conferência não foi feita."
            )

        if status in FECHADO:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Porta fechada: {alvo} respondeu {status}. "
                    "O nginx está recusando a rota vinda do navegador, como deve."
                )
            )
            return

        raise CommandError(
            f"PORTA ABERTA: {alvo} respondeu {status}, e deveria recusar.\n"
            "Qualquer pessoa com a URL baixa material sem passar pela checagem de "
            "permissão do Django.\n"
            "Confira se o bloco `location /protegido/` do nginx tem a diretiva "
            "`internal;` e recarregue o servidor (`nginx -s reload`)."
        )
