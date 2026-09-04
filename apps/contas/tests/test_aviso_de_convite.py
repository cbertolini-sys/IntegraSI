"""A tela nao pode dizer "enviado" enquanto o e-mail ainda esta na fila.

Aconteceu em producao, no primeiro convite de verdade: a tela respondeu "Convite
enviado para cbertolini@gmail.com", a caixa ficou vazia, e o defeito procurado
nao existia. O sistema nao envia dentro da requisicao de proposito (spec 9): ele
enfileira, e o cron entrega. Entre uma coisa e outra passam-se minutos.

Quem conhece o sistema perdeu tempo procurando erro. Um professor convidando um
aluno reenviaria o convite, ou concluiria que o sistema esta quebrado.

O par deste teste, para a alocacao de aluno, mora em `apps/cursos/tests/`, porque
a fixture do curso vive la e `contas` nao conhece `cursos`.
"""

import pytest
from django.urls import reverse

from apps.contas.models import Usuario


@pytest.mark.django_db
def test_cadastro_de_professor_nao_afirma_que_o_email_ja_saiu(client, coordenador):
    client.force_login(coordenador)

    resposta = client.post(
        reverse("pessoas"),
        {"acao": "CRIAR_PROFESSOR", "email": "nova.professora@ufsm.br"},
        follow=True,
    )

    assert Usuario.objects.filter(email="nova.professora@ufsm.br").exists()
    texto = " ".join(str(m) for m in resposta.context["messages"])
    assert "Convite enviado" not in texto, texto
    # A espera precisa estar dita: sem isso a frase so fica vaga, e quem ler
    # continua sem saber se deve esperar ou reenviar.
    assert "minutos" in texto, texto
