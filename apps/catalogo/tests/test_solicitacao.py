import datetime

import pytest
from django.urls import reverse
from django.utils import timezone

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
    # curso_publicado ja enfileira notificacoes para professor e coordenador so
    # de percorrer o ciclo de vida do curso (CURSO_SUBMETIDO, CURSO_PUBLICADO);
    # filtrar por evento='SOLICITACAO_RECEBIDA' e o que garante que e a view
    # deste teste - nao a fixture - quem esta avisando os dois. Sem o filtro o
    # teste passa mesmo que a view nunca chame enfileirar (achado do self-review).
    client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos())
    destinatarios = set(
        Notificacao.objects.filter(evento="SOLICITACAO_RECEBIDA").values_list("destinatario", flat=True)
    )
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
    # Pino o motivo de existir o branch de metodo na view (achado da revisao): sem
    # ele, GET tambem construiria SolicitacaoForm(request.POST) com um QueryDict
    # vazio - form "bound" e sujo de erro em todo campo obrigatorio na primeira
    # visita a pagina, nunca a exibicao limpa que um formulario de entrada espera.
    form = resposta.context["form"]
    assert not form.is_bound
    assert not form.errors


@pytest.mark.django_db
def test_honeypot_preenchido_e_descartado_em_silencio(client, curso_publicado):
    resposta_humana = client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos(), follow=True)

    dados_robo = dados_validos()
    dados_robo["confirmacao"] = "sou um robo"
    resposta_robo = client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_robo, follow=True)

    assert resposta_robo.status_code == 200
    # Nao basta nao escrever nada: uma pagina de erro distinguivel tambem
    # cumpriria "nao escreveu", mas ensinaria o robo o que mudar da proxima vez.
    # A resposta ao robo precisa ser byte a byte a mesma que a pessoa recebeu.
    assert resposta_robo.content == resposta_humana.content
    assert Solicitacao.objects.count() == 1  # so a submissao humana


@pytest.mark.django_db
def test_limite_por_ip(client, curso_publicado):
    from apps.catalogo.views import LIMITE_POR_IP_POR_HORA

    for _ in range(LIMITE_POR_IP_POR_HORA):
        client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos())
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA

    recusada = client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos(), follow=True)
    assert "muitas solicitações" in recusada.content.decode().lower()
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA

    # O limite e por IP, nao global: de outro endereco, a solicitacao seguinte
    # precisa ser aceita mesmo com o primeiro IP esgotado. Um count() sem o
    # filtro de ip_origem recusaria esta tambem.
    client.post(
        reverse("solicitar", args=[curso_publicado.pk]), dados_validos(), REMOTE_ADDR="203.0.113.7"
    )
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA + 1


@pytest.mark.django_db
def test_limite_por_hora(client, curso_publicado):
    from apps.catalogo.views import LIMITE_POR_IP_POR_HORA

    for _ in range(LIMITE_POR_IP_POR_HORA):
        client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos())
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA

    # Empurra as solicitacoes existentes para fora da janela de uma hora.
    # criado_em e auto_now_add: so um update() de queryset (que ignora o
    # comportamento automatico do campo) consegue reescreve-lo.
    mais_de_uma_hora_atras = timezone.now() - datetime.timedelta(hours=2)
    Solicitacao.objects.update(criado_em=mais_de_uma_hora_atras)

    # Com a janela expirada, o mesmo IP volta a poder solicitar. Sem o filtro de
    # criado_em__gte, o limite valeria para sempre e este POST seguiria recusado.
    client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos())
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA + 1


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
