"""Conftest da raiz. Existe por um motivo unico, e deliberadamente nao define
fixture nenhuma que os testes possam pedir pelo nome -- o conftest de
apps/catalogo/tests explica por que este projeto evitou um conftest global.
"""

import pytest
from django.conf import settings


@pytest.fixture(autouse=True, scope="session")
def _sem_redirecionamento_https_na_suite():
    """Desliga SECURE_SSL_REDIRECT durante a suite, e so ele.

    O cliente de teste fala http. Com SECURE_SSL_REDIRECT ligado -- que e o
    padrao de producao a partir do Plano 4 -- toda requisicao de teste viraria
    um 301 para https e a suite mediria o middleware de seguranca em vez das
    regras do sistema.

    Que ele nasca LIGADO em producao nao depende desta linha: quem prova isso e
    tests/test_configuracao.py, importando as settings num subprocesso com
    ambiente de producao, fora do alcance do pytest. As duas provas sao
    independentes de proposito -- esta aqui nao pode encobrir aquela.

    As demais chaves de seguranca (cookies Secure, HSTS, nosniff, X-Frame) ficam
    LIGADAS durante a suite inteira: elas nao atrapalham o cliente de teste, e e
    melhor que os testes rodem contra a configuracao de producao onde der.
    """
    anterior = settings.SECURE_SSL_REDIRECT
    settings.SECURE_SSL_REDIRECT = False
    yield
    settings.SECURE_SSL_REDIRECT = anterior
