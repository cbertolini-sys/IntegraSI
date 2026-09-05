"""A sessao nao volta ao banco a cada requisicao.

Medido antes desta mudanca: uma requisicao autenticada ao painel gastava 6
consultas, e UMA delas era so para ler `django_session`. Para o volume de hoje e
irrelevante; registro e corrijo porque custa pouco e porque a conta piora
exatamente quando o sistema comeca a ser usado.

O que este arquivo NAO promete: que o ganho seja total em producao. O cache e
`locmem`, que vive dentro de CADA processo do gunicorn, e sao nove. Uma sessao
aquecida no operario 3 nao existe no 7, e la a requisicao volta ao banco - o
`cached_db` cai para o banco quando o cache nao tem, que e justamente por que ele
se chama assim. O ganho e parcial e proporcional a quantas requisicoes seguidas
caem no mesmo operario.

Um cache compartilhado (Redis, Memcached) tornaria o ganho completo, e traria um
servico a mais para instalar, monitorar e reiniciar. Para este tamanho, nao paga.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse


@pytest.fixture
def alguem(db):
    """Conta propria: as fixtures de pessoa moram nos conftests dos apps, e este
    arquivo esta em `tests/`, que nao os alcanca."""
    return get_user_model().objects.create_user(
        email="sessao@ufsm.br", nome_completo="Teste de Sessão",
        cpf="168.995.350-09", papel=get_user_model().PROFESSOR, siape="3100001",
        password="senha-de-teste-123",
    )


def consultas_de_sessao(client, url):
    """So as consultas que tocam `django_session`."""
    client.get(url)  # aquecimento: a primeira grava a sessao no cache
    with CaptureQueriesContext(connection) as capturadas:
        client.get(url)
    return [q for q in capturadas.captured_queries if "django_session" in q["sql"]]


@pytest.mark.django_db
def test_a_sessao_aquecida_nao_volta_ao_banco(client, alguem):
    """A afirmacao e sobre a CONSULTA, e nao sobre o nome do backend em settings.

    Afirmar `SESSION_ENGINE == "...cached_db"` passaria verde com o cache
    quebrado, mal configurado ou desligado por um `CACHES` invalido. O que
    interessa e o efeito, e o efeito e mensuravel.
    """
    client.force_login(alguem)

    assert consultas_de_sessao(client, reverse("painel")) == []


@pytest.mark.django_db
def test_a_sessao_continua_valendo_quando_o_cache_esvazia(client, alguem):
    """`cached_db`, e nao `cache` puro.

    O backend `cache` guarda a sessao SO na memoria: um reinicio do gunicorn, ou
    a expiracao de uma entrada, desloga todo mundo em silencio. Com `cached_db` o
    banco continua sendo a verdade e o cache e so atalho, entao esvaziar o cache
    custa uma consulta, e nao a sessao.
    """
    from django.core.cache import cache

    client.force_login(alguem)
    client.get(reverse("painel"))
    cache.clear()

    resposta = client.get(reverse("painel"))

    assert resposta.status_code == 200, "esvaziar o cache deslogou a pessoa"
