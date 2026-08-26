import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia, TipoPublico
from apps.cursos.forms import CursoForm
from apps.cursos.models import Anexo, Curso, Tema


def test_curso_form_nao_inclui_competencias():
    # Competencias depende do referencial escolhido e e editada depois que o curso
    # ja existe (docs/onde-mora-a-validacao.md); resolver isso no mesmo formulario
    # exigiria campo dependente em JavaScript, que este projeto nao usa.
    assert "competencias" not in CursoForm().fields


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
        reverse("nova_proposta"),
        {
            "titulo": "Robotica com sucata",
            "resumo": "Oficina de robotica de baixo custo.",
            "edicao": edicao.pk,
            "tipo_publico": TipoPublico.ESCOLAR,
            "etapa_ano": "EF09",
            "publico_descricao": "",
            "carga_horaria": 8,
            "formato": "PRESENCIAL",
            "palavras_chave": "robotica, sucata",
        },
        follow=True,
    )
    assert resposta.status_code == 200
    curso = Curso.objects.get(titulo="Robotica com sucata")
    assert curso.professor_responsavel == professor
    assert curso.entregaveis.count() == 5


@pytest.mark.django_db
def test_professor_cria_proposta_com_temas(client, professor, edicao):
    tema1 = Tema.objects.create(nome="Robotica Educacional")
    tema2 = Tema.objects.create(nome="Pensamento Computacional")
    client.force_login(professor)
    resposta = client.post(
        reverse("nova_proposta"),
        {
            "titulo": "Curso com temas associados",
            "resumo": "Resumo qualquer para o curso de teste.",
            "edicao": edicao.pk,
            "tipo_publico": TipoPublico.ESCOLAR,
            "etapa_ano": "EF09",
            "publico_descricao": "",
            "carga_horaria": 8,
            "formato": "PRESENCIAL",
            "palavras_chave": "",
            "temas": [tema1.pk, tema2.pk],
        },
        follow=True,
    )
    assert resposta.status_code == 200
    curso = Curso.objects.get(titulo="Curso com temas associados")
    assert set(curso.temas.values_list("pk", flat=True)) == {tema1.pk, tema2.pk}


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
def test_coordenador_nao_cria_proposta(client, coordenador):
    # Curso.clean() exige que professor_responsavel.e_professor seja verdadeiro; um
    # coordenador nao e professor, entao deixar esta view aceitar coordenador fazia
    # services.criar_curso() estourar ValidationError sem tratamento (500) assim que
    # o form validasse (o FK so e checado dentro de Curso.save()). Deixar o
    # coordenador escolher outro professor responsavel seria uma tela nova (Plano 3),
    # nao um conserto deste bug.
    client.force_login(coordenador)
    resposta = client.get(reverse("nova_proposta"))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_professor_monta_equipe(client, professor, dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.post(reverse("equipe", args=[curso.pk]), {"aluno": aluno.pk}, follow=True)
    assert resposta.status_code == 200
    assert curso.tem_membro(aluno)


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

    monkeypatch.setattr(services, "adicionar_membro", sempre_recusa)
    client.force_login(professor)
    resposta = client.post(reverse("equipe", args=[curso.pk]), {"aluno": aluno.pk}, follow=True)
    conteudo = resposta.content.decode()
    assert "Primeira mensagem de erro." in conteudo
    assert "Segunda mensagem de erro." in conteudo


@pytest.mark.django_db
def test_equipe_sem_aluno_selecionado_nao_quebra(client, professor, dados_curso):
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.post(reverse("equipe", args=[curso.pk]), {}, follow=True)
    assert resposta.status_code == 200
    assert "Selecione um aluno" in resposta.content.decode()


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
def test_fila_de_outro_professor_esta_vazia(client, slides_em_revisao, db):
    from apps.contas.models import Usuario

    outro = Usuario.objects.create_user(
        email="outro.prof@ufsm.br", nome_completo="Elisa Esteves", cpf="111.444.777-35",
        papel=Usuario.PROFESSOR, siape="9999999", password="senha-de-teste-123",
    )
    client.force_login(outro)
    resposta = client.get(reverse("fila_revisao"))
    assert slides_em_revisao.curso.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_aprovar_pela_tela(client, professor, slides_em_revisao):
    client.force_login(professor)
    client.post(reverse("decidir", args=[slides_em_revisao.pk]), {"decisao": "APROVAR", "comentario": ""})
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.APROVADO


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
def test_equipe_de_outro_professor_devolve_403(client, dados_curso):
    from apps.contas.models import Usuario

    curso = services.criar_curso(**dados_curso)
    outro = Usuario.objects.create_user(
        email="outro.prof@ufsm.br", nome_completo="Elisa Esteves", cpf="111.444.777-35",
        papel=Usuario.PROFESSOR, siape="9999999", password="senha-de-teste-123",
    )
    client.force_login(outro)
    resposta = client.get(reverse("equipe", args=[curso.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_aluno_nao_acessa_equipe(client, dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    client.force_login(aluno)
    resposta = client.get(reverse("equipe", args=[curso.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_revisar_de_outro_professor_devolve_403(client, slides_em_revisao):
    from apps.contas.models import Usuario

    outro = Usuario.objects.create_user(
        email="outro.prof@ufsm.br", nome_completo="Elisa Esteves", cpf="111.444.777-35",
        papel=Usuario.PROFESSOR, siape="9999999", password="senha-de-teste-123",
    )
    client.force_login(outro)
    resposta = client.get(reverse("revisar", args=[slides_em_revisao.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_aluno_nao_acessa_revisar(client, aluno, slides_em_revisao):
    client.force_login(aluno)
    resposta = client.get(reverse("revisar", args=[slides_em_revisao.pk]))
    assert resposta.status_code == 403


@pytest.fixture
def plano_em_revisao(dados_curso, aluno, arquivo_qualquer):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Texto exclusivo da ementa de teste.</p>"
    secao.save()
    Anexo.objects.create(
        entregavel=plano, tipo_midia=TipoMidia.ARQUIVO, titulo="Plano de Ensino Definitivo",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
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
def test_revisar_mostra_conteudo_e_materiais(client, professor, plano_em_revisao):
    # "Slides" nao serve de pista aqui: aparece no <h1> via get_tipo_display mesmo
    # que a lista de materiais e o loop de secoes quebrem por completo (falso
    # positivo apontado na revisao). Por isso o fixture usa titulo e conteudo de
    # secao proprios, que so aparecem se os respectivos loops do template rodarem.
    client.force_login(professor)
    resposta = client.get(reverse("revisar", args=[plano_em_revisao.pk]))
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Plano de Ensino Definitivo" in conteudo
    assert "Texto exclusivo da ementa de teste." in conteudo
