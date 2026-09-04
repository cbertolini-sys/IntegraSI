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
def test_o_aviso_diz_quem_responde_e_quem_esta_em_copia(client, curso_publicado):
    """A fila guarda um endereco por linha e o `send_mail` manda uma mensagem
    separada para cada: nao existe `Cc` no sistema, e ninguem ve quem mais
    recebeu. Sem esta linha, professor e coordenacao leem mensagens identicas e
    nenhuma delas diz quem deve responder - as duas esperam pela outra, ou as
    duas respondem.

    Afirmado no CORPO de quem recebe, e nao numa constante importada: o teste
    precisa falhar se a linha sumir do e-mail, e nao apenas se sumir do modulo.
    """
    client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos())

    corpos = Notificacao.objects.filter(evento="SOLICITACAO_RECEBIDA").values_list(
        "corpo", flat=True
    )
    assert corpos, "nenhuma notificação de solicitação foi enfileirada"
    for corpo in corpos:
        assert "enviada à coordenação, com cópia para o professor responsável" in corpo


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


# --- Quem é o cliente, atrás do proxy ----------------------------------------
# O limite por IP (spec 10) só vale se o IP não puder ser escolhido por quem
# está sendo limitado. Em produção o Django não fala com o visitante: fala com o
# nginx, e o endereço real chega em X-Forwarded-For.


@pytest.mark.django_db
def test_cabecalho_forjado_nao_ganha_cota_nova(client, curso_publicado):
    """X-Forwarded-For é uma lista onde cada proxy ACRESCENTA ao fim: o último
    elemento é o que o nosso nginx escreveu, os anteriores são texto do cliente.
    Lendo o primeiro, `X-Forwarded-For: 9.9.9.9` diferente a cada requisição dá
    cota nova toda vez e o limite nunca dispara."""
    from apps.catalogo.views import LIMITE_POR_IP_POR_HORA

    url = reverse("solicitar", args=[curso_publicado.pk])
    for _ in range(LIMITE_POR_IP_POR_HORA):
        client.post(url, dados_validos(), HTTP_X_FORWARDED_FOR="198.51.100.9")
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA

    # A mesma pessoa, agora forjando uma origem diferente na frente da lista --
    # exatamente o que o nginx produziria com $proxy_add_x_forwarded_for.
    recusada = client.post(
        url,
        dados_validos(),
        HTTP_X_FORWARDED_FOR="9.9.9.9, 198.51.100.9",
        follow=True,
    )
    assert "muitas solicitações" in recusada.content.decode().lower()
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA


@pytest.mark.django_db
def test_atras_do_proxy_o_limite_continua_sendo_por_ip(client, curso_publicado):
    """O nginx entrega toda requisição com REMOTE_ADDR 127.0.0.1. Se o Django
    olhasse só para ele, o limite viraria global e um visitante fecharia o
    formulário para toda a comunidade."""
    from apps.catalogo.views import LIMITE_POR_IP_POR_HORA

    url = reverse("solicitar", args=[curso_publicado.pk])
    for _ in range(LIMITE_POR_IP_POR_HORA):
        client.post(url, dados_validos(), REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.9")
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA

    client.post(url, dados_validos(), REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.4")
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA + 1


@pytest.mark.django_db
def test_sem_proxy_o_cabecalho_e_ignorado(client, curso_publicado, settings):
    """Sem nginx na frente, X-Forwarded-For é texto escrito pelo cliente e não
    vale nada: quem serve o gunicorn exposto direto na rede desliga
    CONFIAR_NO_PROXY e volta a contar por REMOTE_ADDR."""
    from apps.catalogo.views import LIMITE_POR_IP_POR_HORA

    settings.CONFIAR_NO_PROXY = False
    url = reverse("solicitar", args=[curso_publicado.pk])
    for _ in range(LIMITE_POR_IP_POR_HORA):
        client.post(url, dados_validos(), REMOTE_ADDR="198.51.100.9", HTTP_X_FORWARDED_FOR="1.1.1.1")
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA

    recusada = client.post(
        url,
        dados_validos(),
        REMOTE_ADDR="198.51.100.9",
        HTTP_X_FORWARDED_FOR="2.2.2.2",
        follow=True,
    )
    assert "muitas solicitações" in recusada.content.decode().lower()
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA


@pytest.mark.django_db
def test_ip_gravado_e_o_do_proxy_e_nao_o_forjado(client, curso_publicado):
    """O IP fica guardado na solicitação (spec 10): registrar o valor forjado
    envenenaria o histórico de quem pediu o quê."""
    url = reverse("solicitar", args=[curso_publicado.pk])
    client.post(url, dados_validos(), HTTP_X_FORWARDED_FOR="9.9.9.9, 198.51.100.9")
    assert Solicitacao.objects.get().ip_origem == "198.51.100.9"


@pytest.mark.django_db
def test_cabecalho_que_nao_e_ip_nao_derruba_o_formulario(client, curso_publicado):
    """ip_origem é um inet no PostgreSQL: lixo no cabeçalho viraria DataError e um
    500 na única porta anônima que escreve no banco."""
    url = reverse("solicitar", args=[curso_publicado.pk])
    resposta = client.post(
        url, dados_validos(), REMOTE_ADDR="198.51.100.9", HTTP_X_FORWARDED_FOR="nao-e-um-ip"
    )
    assert resposta.status_code == 200
    assert Solicitacao.objects.get().ip_origem == "198.51.100.9"


# --- Situacao (M3 da auditoria) ------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status,rotulo,tom",
    [
        (Solicitacao.RECEBIDA, "A responder", "espera"),
        (Solicitacao.EM_ANALISE, "A responder", "espera"),
        (Solicitacao.ACEITA, "Aceita", "ok"),
        (Solicitacao.RECUSADA, "Recusada", "atencao"),
    ],
)
def test_situacao_de_cada_status(curso_publicado, status, rotulo, tom):
    """A decisão de rótulo e tom estava em dois `{% if %}` diferentes, em duas
    telas (a de pendentes, com rótulo fixo "A responder"; a de respondidas, com
    `get_status_display` e só duas cores). `Situacao` unifica os dois: os quatro
    status precisam continuar respondendo o que já respondiam, cada um."""
    solicitacao = Solicitacao.objects.create(
        curso=curso_publicado, nome="Escola Teste", email="teste@escola.exemplo.br",
        num_participantes=10, instituicao="Escola Teste", status=status,
    )
    assert solicitacao.situacao.rotulo == rotulo
    assert solicitacao.situacao.tom == tom
