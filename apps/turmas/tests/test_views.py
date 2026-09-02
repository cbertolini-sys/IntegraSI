import datetime

import pytest
from django.core import mail
from django.core.management import call_command
from django.urls import reverse

from apps.catalogo.models import Solicitacao
from apps.notificacoes.models import Notificacao
from apps.turmas import services
from apps.turmas.models import Turma


def dados_do_formulario(professor):
    return {
        "decisao": "ACEITAR",
        "professor": professor.pk,
        "data_inicio": "2027-03-01",
        "data_fim": "2027-03-30",
        "local": "EMEF São José",
        "vagas": 25,
    }


@pytest.fixture
def turma(solicitacao, professor, coordenador):
    return services.aceitar_solicitacao(
        solicitacao,
        professor=professor,
        dados_turma={
            "data_inicio": datetime.date(2027, 3, 1),
            "data_fim": datetime.date(2027, 3, 30),
            "local": "EMEF São José",
            "vagas": 25,
        },
        por=coordenador,
    )


# --- portão de login ---------------------------------------------------------


@pytest.mark.parametrize(
    "rota, args",
    [("solicitacoes", []), ("responder_solicitacao", [1]), ("minhas_turmas", [])],
)
@pytest.mark.django_db
def test_visitante_anonimo_vai_para_o_login(client, rota, args):
    """Nenhuma das três rotas pode estourar 500 para quem não está logado.

    permissions.pode_publicar lê usuario.e_coordenador, atributo que AnonymousUser
    não tem: sem @login_required *antes* da checagem de papel, a resposta seria um
    AttributeError, não um redirecionamento. O teste prende a ordem, não a boa
    vontade do decorador.
    """
    resposta = client.get(reverse(rota, args=args))
    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))


# --- lista de solicitações ---------------------------------------------------


@pytest.mark.django_db
def test_coordenador_ve_as_solicitacoes(client, coordenador, solicitacao):
    client.force_login(coordenador)
    conteudo = client.get(reverse("solicitacoes")).content.decode()
    assert solicitacao.nome in conteudo
    assert reverse("responder_solicitacao", args=[solicitacao.pk]) in conteudo


@pytest.mark.django_db
def test_pendentes_incluem_em_analise_e_excluem_as_respondidas(
    client, coordenador, professor, curso_publicado, solicitacao
):
    # Só afirmar que a solicitação certa aparece deixaria passar um filtro que
    # virasse "todas as solicitações": o que este teste crava é a exclusão. As
    # três irmãs usam o mesmo curso, então o título não distingue nada - a marca
    # de que a linha está na lista de pendentes é o link para respondê-la.
    def outra(status):
        return Solicitacao.objects.create(
            curso=curso_publicado, nome=f"Escola {status}", email="outra@escola.exemplo.br",
            num_participantes=10, status=status,
        )

    em_analise = outra(Solicitacao.EM_ANALISE)
    aceita = outra(Solicitacao.ACEITA)
    recusada = outra(Solicitacao.RECUSADA)

    client.force_login(coordenador)
    conteudo = client.get(reverse("solicitacoes")).content.decode()
    assert reverse("responder_solicitacao", args=[solicitacao.pk]) in conteudo
    assert reverse("responder_solicitacao", args=[em_analise.pk]) in conteudo
    assert reverse("responder_solicitacao", args=[aceita.pk]) not in conteudo
    assert reverse("responder_solicitacao", args=[recusada.pk]) not in conteudo
    # As respondidas não somem da tela; migram para o histórico embaixo.
    assert "Aceita" in conteudo
    assert "Recusada" in conteudo


@pytest.mark.django_db
def test_lista_vazia_avisa_em_portugues_acentuado(client, coordenador):
    client.force_login(coordenador)
    conteudo = client.get(reverse("solicitacoes")).content.decode()
    assert "Nenhuma solicitação pendente." in conteudo


@pytest.mark.django_db
def test_aluno_nao_ve_as_solicitacoes(client, aluno, solicitacao):
    client.force_login(aluno)
    assert client.get(reverse("solicitacoes")).status_code == 403


@pytest.mark.django_db
def test_professor_nao_ve_as_solicitacoes(client, professor, solicitacao):
    """"Aluno é barrado" não prova "só a coordenação passa".

    Uma guarda afrouxada para aceitar qualquer professor continuaria barrando o
    aluno. O professor é o papel mais próximo do autorizado - ele é até o
    responsável pelo curso desta solicitação - e é ele quem discrimina a guarda.
    """
    client.force_login(professor)
    assert client.get(reverse("solicitacoes")).status_code == 403


# --- responder: permissão ----------------------------------------------------


@pytest.mark.django_db
def test_aluno_nao_responde_solicitacao(client, aluno, solicitacao):
    client.force_login(aluno)
    assert client.get(reverse("responder_solicitacao", args=[solicitacao.pk])).status_code == 403


@pytest.mark.django_db
def test_professor_nao_abre_a_solicitacao(client, professor, solicitacao):
    """Este é o teste que prende a guarda da *view* de responder, e é o GET.

    Nos dois POST abaixo a guarda da view é redundante: mesmo afrouxada para
    aceitar qualquer professor, services.aceitar_solicitacao e
    services.recusar_solicitacao levantam PermissionDenied por conta própria e a
    resposta continua 403 - a mutação sobrevive aos dois. O GET é o único caminho
    em que a guarda da view carrega o peso sozinha, e o que ela protege é a ficha
    da solicitação: nome, e-mail, telefone e mensagem de terceiro externo (spec
    10). Sem esta linha, afrouxar a guarda abriria essa ficha em silêncio.
    """
    client.force_login(professor)
    assert client.get(reverse("responder_solicitacao", args=[solicitacao.pk])).status_code == 403
    assert solicitacao.email not in client.get(
        reverse("responder_solicitacao", args=[solicitacao.pk])
    ).content.decode()


@pytest.mark.django_db
def test_professor_nao_aceita_pela_tela(client, professor, outro_professor, solicitacao):
    """Prende que a tela passa pelo serviço, e não por um Turma.objects.create
    escrito na view: o 403 aqui vem do portão de services.aceitar_solicitacao.
    Quem prende a guarda da própria view é test_professor_nao_abre_a_solicitacao.
    """
    client.force_login(professor)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        dados_do_formulario(outro_professor),
    )
    assert resposta.status_code == 403
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA
    assert not Turma.objects.exists()


@pytest.mark.django_db
def test_professor_nao_recusa_pela_tela(client, professor, solicitacao):
    client.force_login(professor)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        {"decisao": "RECUSAR", "resposta": "Não temos agenda."},
    )
    assert resposta.status_code == 403
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA


# --- responder: aceitar ------------------------------------------------------


@pytest.mark.django_db
def test_aceitar_pela_tela_cria_a_turma(client, coordenador, professor, solicitacao):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        dados_do_formulario(professor),
        follow=True,
    )
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.ACEITA
    turma = Turma.objects.get()
    assert turma.professor == professor
    assert turma.solicitacao == solicitacao
    assert turma.curso == solicitacao.curso
    assert "Turma agendada e solicitante avisado." in resposta.content.decode()


@pytest.mark.django_db
def test_aceitar_pela_tela_avisa_o_solicitante(client, coordenador, professor, solicitacao):
    # Filtrado por evento E por destinatário: o ciclo de vida do curso publicado
    # já enfileira notificações por conta própria, e sem os dois filtros o teste
    # passaria mesmo se a tela não avisasse ninguém.
    client.force_login(coordenador)
    client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        dados_do_formulario(professor),
        follow=True,
    )
    assert Notificacao.objects.filter(
        evento="SOLICITACAO_ACEITA", destinatario=solicitacao.email
    ).exists()


@pytest.mark.django_db
def test_aceitar_sem_professor_nao_cria_turma(client, coordenador, solicitacao):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        {
            "decisao": "ACEITAR",
            "data_inicio": "2027-03-01",
            "data_fim": "2027-03-30",
            "local": "EMEF São José",
            "vagas": 25,
        },
    )
    assert resposta.status_code == 200
    assert not Turma.objects.exists()
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA
    assert "Este campo é obrigatório." in resposta.content.decode()


@pytest.mark.django_db
def test_aceitar_solicitacao_ja_respondida_vira_mensagem_e_nao_erro_500(
    client, coordenador, professor, solicitacao, turma
):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        dados_do_formulario(professor),
        follow=True,
    )
    assert resposta.status_code == 200
    assert resposta.content.decode().count("Esta solicitação já foi respondida.") == 1
    assert Turma.objects.count() == 1


@pytest.mark.django_db
def test_aceitar_com_fim_antes_do_inicio_e_barrado(client, coordenador, professor, solicitacao):
    client.force_login(coordenador)
    dados = dados_do_formulario(professor) | {"data_fim": "2027-02-01"}
    resposta = client.post(reverse("responder_solicitacao", args=[solicitacao.pk]), dados)
    assert resposta.status_code == 200
    assert not Turma.objects.exists()
    assert "O fim não pode ser anterior ao início." in resposta.content.decode()


@pytest.mark.django_db
def test_formulario_sugere_as_vagas_pedidas(client, coordenador, solicitacao):
    client.force_login(coordenador)
    conteudo = client.get(reverse("responder_solicitacao", args=[solicitacao.pk])).content.decode()
    assert f'name="vagas" value="{solicitacao.num_participantes}"' in conteudo


# --- responder: recusar ------------------------------------------------------


@pytest.mark.django_db
def test_recusar_pela_tela_registra_a_resposta(client, coordenador, solicitacao):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        {"decisao": "RECUSAR", "resposta": "Sem professor disponível neste semestre."},
        follow=True,
    )
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECUSADA
    assert solicitacao.resposta == "Sem professor disponível neste semestre."
    assert "Solicitante avisado." in resposta.content.decode()
    assert Notificacao.objects.filter(
        evento="SOLICITACAO_RECUSADA", destinatario=solicitacao.email
    ).exists()
    assert not Turma.objects.exists()


@pytest.mark.django_db
def test_recusar_sem_resposta_e_barrado(client, coordenador, solicitacao):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        {"decisao": "RECUSAR", "resposta": " "},
        follow=True,
    )
    conteudo = resposta.content.decode()
    # count == 1, e não apenas "in": base.html já renderiza a região de messages
    # desde o Plano 1. Um {% for mensagem in messages %} deixado no template -
    # como o rascunho do plano trazia - duplicaria toda mensagem desta tela.
    assert conteudo.count("Escreva a resposta ao solicitante.") == 1
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA


@pytest.mark.django_db
def test_recusa_barrada_nao_suja_o_formulario_de_aceitar(client, coordenador, solicitacao):
    """Duas ações moram na mesma página, e uma não pode contaminar a outra.

    Ligar o formulário de aceitar a request.POST em toda requisição POST o deixa
    *bound* e vazio quando quem postou queria recusar - e o ramo de recusa nunca
    chama is_valid(), então o usuário volta para a página com "Este campo é
    obrigatório." em todos os campos de um formulário que ele nem tocou. É o
    mesmo defeito que a Task 6 já tinha corrigido em outra tela.
    """
    client.force_login(coordenador)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        {"decisao": "RECUSAR", "resposta": ""},
        follow=True,
    )
    conteudo = resposta.content.decode()
    assert "Este campo é obrigatório." not in conteudo
    assert "errorlist" not in conteudo


@pytest.mark.django_db
def test_post_sem_decisao_nao_responde_a_solicitacao(client, coordenador, solicitacao):
    """Um POST que não diz o que quer não pode recusar por omissão.

    Tratar "tudo que não é ACEITAR" como recusa faz um POST sem o campo decisao
    - e com uma resposta qualquer - recusar a solicitação e disparar o e-mail ao
    solicitante. A decisão precisa ser dita, não inferida.
    """
    client.force_login(coordenador)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        {"resposta": "qualquer coisa"},
    )
    assert resposta.status_code == 200
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA
    assert not Notificacao.objects.filter(evento="SOLICITACAO_RECUSADA").exists()


@pytest.mark.django_db
def test_get_em_responder_nao_muda_nada(client, coordenador, solicitacao):
    client.force_login(coordenador)
    resposta = client.get(reverse("responder_solicitacao", args=[solicitacao.pk]))
    assert resposta.status_code == 200
    assert solicitacao.nome in resposta.content.decode()
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA
    assert not Turma.objects.exists()


# --- minhas turmas -----------------------------------------------------------


@pytest.mark.django_db
def test_professor_ve_apenas_as_proprias_turmas(client, professor, outro_professor, turma):
    client.force_login(outro_professor)
    assert turma.local not in client.get(reverse("minhas_turmas")).content.decode()
    client.force_login(professor)
    assert turma.local in client.get(reverse("minhas_turmas")).content.decode()


@pytest.mark.django_db
def test_coordenador_ve_todas_as_turmas(client, coordenador, turma):
    client.force_login(coordenador)
    assert turma.local in client.get(reverse("minhas_turmas")).content.decode()


@pytest.mark.django_db
def test_aluno_nao_entra_em_minhas_turmas(client, aluno, turma):
    """Decisão registrada: aluno não alcança a tela de turmas.

    Sem guarda explícita, o aluno recebe uma página vazia - inofensiva hoje só
    porque Turma.professor nunca aponta para um aluno (Turma.clean o proíbe). A
    ausência de vazamento seria acidente de dado, não regra; e uma regra sem
    guarda não tem o que apagar, então nenhum teste a prende. A guarda existe
    para que esta linha possa falhar.
    """
    client.force_login(aluno)
    assert client.get(reverse("minhas_turmas")).status_code == 403


@pytest.mark.django_db
def test_sem_turma_a_tela_avisa_em_portugues_acentuado(client, professor):
    client.force_login(professor)
    assert "Nenhuma turma agendada." in client.get(reverse("minhas_turmas")).content.decode()


# --- painel ------------------------------------------------------------------


@pytest.mark.django_db
def test_painel_oferece_os_links_conforme_o_papel(client, aluno, professor, coordenador):
    turmas = reverse("minhas_turmas")
    solicitacoes = reverse("solicitacoes")

    client.force_login(coordenador)
    conteudo = client.get(reverse("painel")).content.decode()
    # Turmas saiu do painel dos DOIS papeis, a pedido: e modulo de outra etapa, a
    # desenvolver. A tela e a permissao continuam de pe; o que sumiu foi o
    # caminho. Solicitacoes continua, porque continua sendo trabalho de agora.
    assert turmas not in conteudo
    assert solicitacoes in conteudo

    client.force_login(professor)
    conteudo = client.get(reverse("painel")).content.decode()
    # O professor deixou de ver o link de Turmas no painel, a pedido: os cartoes
    # dele sao de producao, e a conducao de turma e a etapa seguinte. A regra
    # mudou por decisao, e nao por descuido - ver
    # `test_o_professor_nao_tem_mais_porta_para_turmas`, que registra o que isso
    # custou.
    assert turmas not in conteudo
    assert solicitacoes not in conteudo

    client.force_login(aluno)
    conteudo = client.get(reverse("painel")).content.decode()
    assert turmas not in conteudo
    assert solicitacoes not in conteudo


# --- o ciclo inteiro ---------------------------------------------------------


@pytest.mark.django_db
def test_ciclo_do_curso_publicado_ate_a_turma_agendada(
    client, curso_publicado, professor, coordenador
):
    """O passo 7 do plano, que pedia um passeio manual no runserver, escrito como
    teste: curso publicado -> busca pública -> solicitação -> coordenação aceita
    -> turma na tela do professor -> e-mail saindo da fila."""
    # 1. o visitante anônimo encontra o curso pela busca do catálogo
    resposta = client.get(reverse("catalogo"), {"q": "Pensamento"})
    assert curso_publicado.titulo in resposta.content.decode()

    # 2. e solicita, sem login
    client.post(
        reverse("solicitar", args=[curso_publicado.pk]),
        {
            "nome": "Escola Municipal São José",
            "email": "direcao@escola.exemplo.br",
            "telefone": "55999999999",
            "instituicao": "EMEF São José",
            "num_participantes": 25,
            "periodo_pretendido": "Março de 2027",
            "mensagem": "Gostaríamos de oferecer a oficina para o 5º ano.",
            "confirmacao": "",
        },
    )
    solicitacao = Solicitacao.objects.get()
    assert solicitacao.status == Solicitacao.RECEBIDA

    # 3. a coordenação vê a solicitação na fila
    client.force_login(coordenador)
    conteudo = client.get(reverse("solicitacoes")).content.decode()
    assert reverse("responder_solicitacao", args=[solicitacao.pk]) in conteudo

    # 4. e aceita, designando o professor
    client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        dados_do_formulario(professor),
        follow=True,
    )
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.ACEITA

    # 5. a turma aparece para o professor designado
    client.force_login(professor)
    assert "EMEF São José" in client.get(reverse("minhas_turmas")).content.decode()

    # 6. e o solicitante recebe o e-mail quando o cron roda
    call_command("enviar_notificacoes")
    destinos = [m.to for m in mail.outbox]
    assert ["direcao@escola.exemplo.br"] in destinos
