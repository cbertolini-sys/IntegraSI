import pytest
from django.urls import reverse

from apps.catalogo.models import Solicitacao
from apps.cursos import services
from apps.cursos.choices import StatusEntregavel
from apps.notificacoes.models import Notificacao


@pytest.fixture
def curso_publicado(dados_curso, outro_aluno, professor, coordenador):
    # adicionar_membro tira o curso de RASCUNHO para EM_PRODUCAO (services.py); sem
    # isso submeter_ao_coordenador recusa por status, nao pelos entregaveis (mesma
    # lacuna documentada em apps/catalogo/tests/test_catalogo.py).
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, outro_aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    return curso


def dados_validos():
    return {
        "nome": "Escola Municipal São José",
        "email": "direcao@escola.exemplo.br",
        "telefone": "55999999999",
        "instituicao": "EMEF São José",
        "num_participantes": 25,
        "periodo_pretendido": "Março de 2027",
        "mensagem": "Gostaríamos de oferecer a oficina para o 5º ano.",
        "confirmacao": "",
    }


@pytest.mark.django_db
def test_visitante_solicita_sem_login(client, curso_publicado):
    resposta = client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos(), follow=True)
    assert resposta.status_code == 200
    solicitacao = Solicitacao.objects.get()
    assert solicitacao.curso == curso_publicado
    assert solicitacao.status == Solicitacao.RECEBIDA


@pytest.mark.django_db
def test_solicitacao_avisa_professor_e_coordenador(client, curso_publicado, professor, coordenador):
    client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos())
    destinatarios = set(Notificacao.objects.values_list("destinatario", flat=True))
    assert {professor.email, coordenador.email} <= destinatarios


@pytest.mark.django_db
def test_nao_se_solicita_curso_nao_publicado(client, dados_curso):
    curso = services.criar_curso(**dados_curso)
    resposta = client.post(reverse("solicitar", args=[curso.pk]), dados_validos())
    assert resposta.status_code == 404
    assert Solicitacao.objects.count() == 0


@pytest.mark.django_db
def test_get_nao_cria_solicitacao(client, curso_publicado):
    resposta = client.get(reverse("solicitar", args=[curso_publicado.pk]))
    assert resposta.status_code == 200
    assert Solicitacao.objects.count() == 0


@pytest.mark.django_db
def test_honeypot_preenchido_e_descartado_em_silencio(client, curso_publicado):
    dados = dados_validos()
    dados["confirmacao"] = "sou um robo"
    resposta = client.post(reverse("solicitar", args=[curso_publicado.pk]), dados, follow=True)
    assert resposta.status_code == 200
    assert Solicitacao.objects.count() == 0


@pytest.mark.django_db
def test_limite_por_ip(client, curso_publicado):
    from apps.catalogo.views import LIMITE_POR_IP_POR_HORA

    for _ in range(LIMITE_POR_IP_POR_HORA):
        client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos())
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA
    resposta = client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos(), follow=True)
    assert "muitas solicitações" in resposta.content.decode().lower()
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA


@pytest.mark.django_db
def test_mensagem_gigante_e_recusada(client, curso_publicado):
    dados = dados_validos()
    dados["mensagem"] = "x" * 5000
    client.post(reverse("solicitar", args=[curso_publicado.pk]), dados)
    assert Solicitacao.objects.count() == 0


@pytest.mark.django_db
def test_formulario_declara_a_finalidade_dos_dados(client, curso_publicado):
    resposta = client.get(reverse("solicitar", args=[curso_publicado.pk]))
    conteudo = resposta.content.decode().lower()
    assert "finalidade" in conteudo or "seus dados" in conteudo
