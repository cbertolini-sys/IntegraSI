import pytest
from django.contrib import messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import reverse

from apps.contas.models import Usuario
from apps.contas.views import painel


@pytest.fixture
def aluno(db):
    return Usuario.objects.create_user(
        email="aluno@ufsm.br",
        nome_completo="Ana Alves",
        cpf="529.982.247-25",
        papel=Usuario.ALUNO,
        matricula="201910101",
        password="senha-de-teste-123",
    )


@pytest.mark.django_db
def test_base_html_renderiza_as_mensagens_do_framework_de_messages(aluno):
    """django.contrib.messages está instalado com seu context processor, mas
    base.html só renderizava {% block conteudo %}. Sem uma região para
    {{ messages }}, toda mensagem enfileirada por messages.success(...) (Plano 2
    já faz isso) seria silenciosamente descartada -- nenhum template posterior
    adiciona essa região."""
    request = RequestFactory().get(reverse("painel"))
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request.user = aluno

    storage = FallbackStorage(request)
    storage.add(messages.SUCCESS, "Cadastro concluído com sucesso.")
    request._messages = storage

    resposta = painel(request)
    conteudo = resposta.content.decode()
    assert "Cadastro concluído com sucesso." in conteudo
