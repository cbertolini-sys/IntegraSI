import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia, TipoPublico
from apps.cursos.forms import PropostaForm
from apps.cursos.models import Anexo, Curso, Tema


def test_proposta_pede_so_o_titulo():
    """Spec 4.3: a criacao pede o titulo e mais nada.

    Assercao por lista exata, e nao por `"x" not in fields`: listar o conteudo faz
    qualquer campo novo aparecer aqui, e pedir mais alguma coisa na criacao passa a
    ser decisao deliberada em vez de acrescimo silencioso. A versao anterior deste
    teste conferia so a ausencia de `competencias`, e teria ficado verde com o
    formulario inteiro de volta."""
    assert list(PropostaForm().fields) == ["titulo"]


@pytest.fixture
def slides_em_revisao(dados_curso, aluno, arquivo_qualquer):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    services.enviar_para_revisao(slides, por=aluno)
    return slides


@pytest.mark.django_db
def test_professor_cria_proposta(client, professor, edicao):
    client.force_login(professor)
    resposta = client.post(
        reverse("nova_proposta"), {"titulo": "Robotica com sucata"}, follow=True
    )
    assert resposta.status_code == 200
    curso = Curso.objects.get(titulo="Robotica com sucata")
    assert curso.professor_responsavel == professor
    assert curso.edicao == edicao
    assert curso.entregaveis.count() == 6


@pytest.mark.django_db
def test_criacao_ignora_campos_de_ficha_enviados_no_post(client, professor, edicao):
    """O formulario de criacao tem um campo so, entao o que vier alem dele no POST
    nao pode entrar. Prende a porta pelo lado de fora: alguem que reintroduzisse
    `resumo` em PropostaForm quebraria este teste alem do da lista de campos."""
    client.force_login(professor)
    client.post(
        reverse("nova_proposta"),
        {"titulo": "So o titulo", "resumo": "Nao deveria entrar", "carga_horaria": 8},
        follow=True,
    )
    curso = Curso.objects.get(titulo="So o titulo")
    assert curso.resumo == ""
    assert curso.carga_horaria is None


@pytest.mark.django_db
def test_temas_nao_sao_definidos_na_criacao(client, professor, edicao):
    """Ate o Plano 6 esta tela associava temas. Agora eles moram na ficha, junto
    com o resto do que a equipe preenche, e a criacao os ignora.

    A cobertura de "definir tema associa e reindexa" nao se perdeu: ela vive em
    test_ficha.py, do lado onde a regra passou a valer."""
    tema = Tema.objects.create(nome="Robotica Educacional")
    client.force_login(professor)
    client.post(
        reverse("nova_proposta"),
        {"titulo": "Curso sem temas", "temas": [tema.pk]},
        follow=True,
    )
    curso = Curso.objects.get(titulo="Curso sem temas")
    assert curso.temas.count() == 0


@pytest.mark.django_db
def test_professor_ve_formulario_de_nova_proposta(client, professor):
    client.force_login(professor)
    resposta = client.get(reverse("nova_proposta"))
    assert resposta.status_code == 200
    assert "Nova proposta de curso" in resposta.content.decode()


@pytest.mark.django_db
def test_aluno_nao_cria_proposta(client, aluno):
    client.force_login(aluno)
    resposta = client.get(reverse("nova_proposta"))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_coordenador_cria_proposta(client, coordenador):
    """Inverteu no Plano 5. Ate o Plano 4 esta tela devolvia 403 ao coordenador --
    nao por decisao de produto, mas por conserto de bug: `Curso.clean()` exigia
    `professor_responsavel.e_professor`, o coordenador nao era professor, e o
    `ValidationError` saia como 500 depois que o form validava.

    A regra 1 do Plano 5 removeu a causa: o coordenador e professor, `Curso.clean`
    o aceita, e nao ha excecao a tratar. Ele fica responsavel pelo proprio curso.
    """
    client.force_login(coordenador)
    resposta = client.get(reverse("nova_proposta"))
    assert resposta.status_code == 200


@pytest.mark.django_db
def test_professor_monta_equipe(client, professor, dados_curso):
    """Contrato novo no Plano 5: a tela recebe nome e e-mail, e nao o pk de uma
    conta que ja existe (regra 2). O que se prende continua sendo o mesmo -- a
    pessoa entra na equipe pela tela do professor."""
    from apps.contas.models import Usuario

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.post(
        reverse("equipe", args=[curso.pk]),
        # `acao` explicito, como o formulario da tela sempre mandou: o desvio da
        # view deixou de ter ramo pega-tudo quando o terceiro formulario entrou.
        {"acao": "aluno", "nome": "Joana Silva", "email": "joana@acad.ufsm.br"},
        follow=True,
    )
    assert resposta.status_code == 200
    nova = Usuario.objects.get(email="joana@acad.ufsm.br")
    assert curso.tem_membro(nova)
    assert nova.convites.filter(usado_em__isnull=True).count() == 1


@pytest.mark.django_db
def test_equipe_mostra_todas_as_mensagens_de_erro_do_servico(
    client, professor, dados_curso, aluno, monkeypatch
):
    # MembroEquipe.full_clean() pode levantar mais de uma mensagem; erro.messages[0]
    # mostrava so a primeira e descartava o resto em silencio (item 6 da revisao de
    # branco). Simula um ValidationError com duas mensagens para provar que ambas
    # chegam ao usuario, sem depender de reproduzir as duas condicoes reais que o
    # model levantaria juntas.
    curso = services.criar_curso(**dados_curso)

    def sempre_recusa(*args, **kwargs):
        raise ValidationError(["Primeira mensagem de erro.", "Segunda mensagem de erro."])

    # Alvo trocado no Plano 5 (a view chama alocar_aluno agora); a REGRA que este
    # teste prende e outra e continua valendo: todas as mensagens chegam, nao so
    # a primeira.
    monkeypatch.setattr(services, "alocar_aluno", sempre_recusa)
    client.force_login(professor)
    resposta = client.post(
        reverse("equipe", args=[curso.pk]),
        {"acao": "aluno", "nome": "Joana Silva", "email": "joana@acad.ufsm.br"},
        follow=True,
    )
    conteudo = resposta.content.decode()
    assert "Primeira mensagem de erro." in conteudo
    assert "Segunda mensagem de erro." in conteudo


@pytest.mark.django_db
def test_equipe_com_formulario_vazio_nao_quebra(client, professor, dados_curso):
    """POST incompleto devolve mensagem, nunca 500.

    A regra sobrevive ao Plano 5; so a mensagem mudou. E ela quase se perdeu junto
    com o contrato antigo: `create_user` levanta `ValueError` para e-mail vazio, a
    view so captura `ValidationError`, e o formulario novo reintroduziu o 500 ate
    o servico passar a recusar explicitamente.

    Manda `acao` de proposito: e o formulario do aluno novo que precisa ser
    exercitado. Um POST sem `acao` nenhuma para no desvio da view e nunca chega ao
    servico, entao provaria outra coisa - essa outra coisa tem teste proprio, em
    test_alocar_aluno_existente.py.
    """
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.post(
        reverse("equipe", args=[curso.pk]), {"acao": "aluno"}, follow=True
    )
    assert resposta.status_code == 200
    assert "Informe o e-mail" in resposta.content.decode()


@pytest.mark.django_db
def test_fila_mostra_o_que_espera_por_mim(client, professor, slides_em_revisao):
    client.force_login(professor)
    resposta = client.get(reverse("fila_revisao"))
    assert slides_em_revisao.curso.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_fila_nao_mostra_entregavel_ainda_nao_enviado(client, professor, dados_curso):
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.get(reverse("fila_revisao"))
    assert curso.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_fila_de_outro_professor_esta_vazia(client, slides_em_revisao, outro_professor):
    client.force_login(outro_professor)
    resposta = client.get(reverse("fila_revisao"))
    assert slides_em_revisao.curso.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_aprovar_pela_tela(client, professor, slides_em_revisao):
    client.force_login(professor)
    client.post(
        # Comentario preenchido: aprovar passou a exigi-lo, como devolver ja
        # exigia. O caso do vazio virou teste proprio, logo abaixo.
        reverse("decidir", args=[slides_em_revisao.pk]),
        {"decisao": "APROVAR", "comentario": "<p>Ficou bom.</p>"},
    )
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.APROVADO


@pytest.mark.django_db
def test_aprovar_sem_comentario_e_barrado_na_tela(client, professor, slides_em_revisao):
    """O gemeo de `test_devolver_sem_comentario_e_barrado_na_tela`: as duas
    decisoes exigem um porque, e a recusa chega como mensagem, nunca como 500."""
    client.force_login(professor)
    resposta = client.post(
        reverse("decidir", args=[slides_em_revisao.pk]),
        {"decisao": "APROVAR", "comentario": "  "},
        follow=True,
    )
    assert resposta.status_code == 200
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.EM_REVISAO
    assert "comentário" in resposta.content.decode()


@pytest.mark.django_db
def test_devolver_sem_comentario_e_barrado_na_tela(client, professor, slides_em_revisao):
    client.force_login(professor)
    resposta = client.post(
        reverse("decidir", args=[slides_em_revisao.pk]),
        {"decisao": "DEVOLVER", "comentario": "  "},
        follow=True,
    )
    assert "Escreva o que precisa ser corrigido" in resposta.content.decode()
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.EM_REVISAO


@pytest.mark.django_db
def test_aluno_nao_decide(client, aluno, slides_em_revisao):
    client.force_login(aluno)
    resposta = client.post(reverse("decidir", args=[slides_em_revisao.pk]), {"decisao": "APROVAR"})
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_decidir_via_get_e_rejeitado(client, professor, slides_em_revisao):
    client.force_login(professor)
    resposta = client.get(reverse("decidir", args=[slides_em_revisao.pk]))
    assert resposta.status_code == 405
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.EM_REVISAO


@pytest.mark.django_db
def test_decidir_mostra_todas_as_mensagens_de_erro_do_servico(
    client, professor, slides_em_revisao, monkeypatch
):
    def sempre_recusa(*args, **kwargs):
        raise ValidationError(["Primeira mensagem de erro.", "Segunda mensagem de erro."])

    monkeypatch.setattr(services, "aprovar_entregavel", sempre_recusa)
    client.force_login(professor)
    resposta = client.post(
        reverse("decidir", args=[slides_em_revisao.pk]),
        {"decisao": "APROVAR", "comentario": ""},
        follow=True,
    )
    conteudo = resposta.content.decode()
    assert "Primeira mensagem de erro." in conteudo
    assert "Segunda mensagem de erro." in conteudo


@pytest.mark.django_db
def test_equipe_rejeita_metodo_nao_suportado(client, professor, dados_curso):
    # equipe atende GET (formulario) e POST (adicionar membro) legitimamente, entao
    # nao pode levar @require_POST na funcao inteira; ainda assim outros verbos
    # (DELETE, PUT, ...) devem ser recusados, nao cair no ramo de leitura por acaso.
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.delete(reverse("equipe", args=[curso.pk]))
    assert resposta.status_code == 405


@pytest.mark.django_db
def test_equipe_de_outro_professor_devolve_403(client, dados_curso, outro_professor):
    curso = services.criar_curso(**dados_curso)
    client.force_login(outro_professor)
    resposta = client.get(reverse("equipe", args=[curso.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_aluno_nao_acessa_equipe(client, dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    client.force_login(aluno)
    resposta = client.get(reverse("equipe", args=[curso.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_revisar_de_outro_professor_devolve_403(client, slides_em_revisao, outro_professor):
    client.force_login(outro_professor)
    resposta = client.get(reverse("revisar", args=[slides_em_revisao.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_aluno_nao_acessa_revisar(client, aluno, slides_em_revisao):
    client.force_login(aluno)
    resposta = client.get(reverse("revisar", args=[slides_em_revisao.pk]))
    assert resposta.status_code == 403


@pytest.fixture
def plano_em_revisao(dados_curso, aluno):
    """O plano exige as SETE secoes escritas e nao tem mais anexo.

    O conteudo da primeira e proprio de proposito: "Plano de Ensino" aparece no
    <h1> pelo get_tipo_display mesmo que o laco de secoes quebre por completo, e um
    texto exclusivo e o que distingue as duas coisas.
    """
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    for secao in plano.secoes.all():
        secao.conteudo = f"<p>Conteúdo de {secao.titulo}.</p>"
        secao.save()
    primeira = plano.secoes.first()
    primeira.conteudo = "<p>Texto exclusivo da ementa de teste.</p>"
    primeira.save()
    services.enviar_para_revisao(plano, por=aluno)
    return plano


@pytest.mark.django_db
def test_revisar_mostra_pendencia_que_surgiu_depois_do_envio(client, professor, plano_em_revisao):
    # Ruling do controller: o curso pode ser editado depois que o entregavel foi
    # enviado, entao uma pendencia pode aparecer so depois - o professor precisa ver
    # isso ENQUANTO revisa, nao so depois de aprovar. Contorna o full_clean() de
    # Curso.save() de proposito (update() nao chama save()) para simular esse dado
    # que ficou invalido depois do envio, sem reabrir o entregavel.
    Curso.objects.filter(pk=plano_em_revisao.curso_id).update(formato="")
    client.force_login(professor)
    resposta = client.get(reverse("revisar", args=[plano_em_revisao.pk]))
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Informe o formato do curso." in conteudo


@pytest.mark.django_db
def test_revisar_mostra_o_conteudo_das_secoes(client, professor, plano_em_revisao):
    # O nome do entregavel nao serve de pista: aparece no <h1> via get_tipo_display
    # mesmo que o laco de secoes quebre por completo (falso positivo apontado na
    # revisao). Por isso o fixture usa um conteudo de secao proprio, que so aparece
    # se o laco rodar.
    client.force_login(professor)
    resposta = client.get(reverse("revisar", args=[plano_em_revisao.pk]))
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Texto exclusivo da ementa de teste." in conteudo
    # O plano nao tem materiais, e a tela de revisao nao mostra o bloco vazio.
    assert "<h2>Materiais</h2>" not in conteudo


@pytest.mark.django_db
def test_revisar_mostra_os_materiais_de_quem_tem(client, professor, slides_em_revisao):
    """A outra metade do teste anterior, no entregavel que de fato tem material."""
    client.force_login(professor)
    conteudo = client.get(reverse("revisar", args=[slides_em_revisao.pk])).content.decode()
    assert "<h2>Materiais</h2>" in conteudo
    assert "Slides" in conteudo
