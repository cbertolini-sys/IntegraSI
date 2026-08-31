"""A conferencia que so o servidor no ar da.

Se o `location /protegido/` do nginx nao estiver marcado `internal;`, qualquer
pessoa busca a URL direto e contorna a checagem de permissao INTEIRA -- e a view
do Django continua perfeitamente correta, com todos os testes verdes. Nenhum
teste desta suite alcanca isso, porque nao ha nginx aqui.

O que estes testes prendem e o COMANDO que faz a conferencia contra um servidor
de verdade: que ele reprove quando a porta esta aberta, aprove quando esta
fechada, e nao minta quando nao conseguiu falar com o servidor.
"""

import urllib.error

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

COMANDO = "conferir_entrega_protegida"


class RespostaFalsa:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def responde(status):
    def _abrir(requisicao, timeout=None):
        if status >= 400:
            raise urllib.error.HTTPError(
                requisicao.full_url, status, "erro", {}, None
            )
        return RespostaFalsa(status)

    return _abrir


def test_porta_fechada_passa(monkeypatch, capsys):
    """404 e o que o `internal;` produz: o nginx recusa a rota vinda do
    navegador."""
    monkeypatch.setattr("urllib.request.urlopen", responde(404))
    call_command(COMANDO, "--base-url", "https://exemplo.br")
    assert "fechada" in capsys.readouterr().out.lower()


def test_403_tambem_passa(monkeypatch):
    """Alguns arranjos devolvem 403 em vez de 404. As duas respostas significam
    a mesma coisa: o navegador nao alcanca a rota."""
    monkeypatch.setattr("urllib.request.urlopen", responde(403))
    call_command(COMANDO, "--base-url", "https://exemplo.br")


def test_porta_aberta_reprova(monkeypatch):
    """200 significa que o nginx entregou o arquivo direto ao navegador, sem
    passar pelo Django. E a falha que este comando existe para achar."""
    monkeypatch.setattr("urllib.request.urlopen", responde(200))
    with pytest.raises(CommandError) as erro:
        call_command(COMANDO, "--base-url", "https://exemplo.br")
    assert "internal" in str(erro.value).lower()


def test_redirecionamento_tambem_reprova(monkeypatch):
    """302 nao e recusa: quem responde e alguma outra coisa, e a conferencia nao
    provou nada. Melhor reprovar do que dar por seguro."""
    monkeypatch.setattr("urllib.request.urlopen", responde(302))
    with pytest.raises(CommandError):
        call_command(COMANDO, "--base-url", "https://exemplo.br")


def test_servidor_inalcancavel_nao_finge_sucesso(monkeypatch):
    """Sem resposta nao ha conclusao. Um comando que passasse aqui viraria um
    carimbo de aprovacao para um servidor que ninguem checou."""

    def cai(requisicao, timeout=None):
        raise urllib.error.URLError("conexao recusada")

    monkeypatch.setattr("urllib.request.urlopen", cai)
    with pytest.raises(CommandError) as erro:
        call_command(COMANDO, "--base-url", "https://exemplo.br")
    assert "não foi possível" in str(erro.value).lower()


def test_a_url_conferida_usa_o_prefixo_do_codigo(monkeypatch):
    """O caminho sai de `views.midia.PREFIXO_INTERNO`, e nao de uma string
    repetida aqui: trocar o prefixo no codigo sem trocar no nginx e justamente
    um dos jeitos de abrir a porta, e a conferencia tem de seguir o codigo."""
    from apps.cursos.views.midia import PREFIXO_INTERNO

    vistas = []

    def espia(requisicao, timeout=None):
        vistas.append(requisicao.full_url)
        raise urllib.error.HTTPError(requisicao.full_url, 404, "nf", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", espia)
    call_command(COMANDO, "--base-url", "https://exemplo.br/")
    assert vistas and PREFIXO_INTERNO in vistas[0]
    assert vistas[0].startswith("https://exemplo.br" + PREFIXO_INTERNO)


def test_nao_manda_cookie(monkeypatch):
    """A pergunta e "um estranho consegue?". Mandar sessao junto responderia
    outra coisa."""
    cabecalhos = []

    def espia(requisicao, timeout=None):
        cabecalhos.append({k.lower(): v for k, v in requisicao.header_items()})
        raise urllib.error.HTTPError(requisicao.full_url, 404, "nf", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", espia)
    call_command(COMANDO, "--base-url", "https://exemplo.br")
    assert "cookie" not in cabecalhos[0]
