import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia, TipoPublico
from apps.cursos.models import Anexo, Curso


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
def test_aluno_nao_cria_proposta(client, aluno):
    client.force_login(aluno)
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


@pytest.mark.django_db
def test_revisar_mostra_conteudo_e_materiais(client, professor, slides_em_revisao):
    client.force_login(professor)
    resposta = client.get(reverse("revisar", args=[slides_em_revisao.pk]))
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Slides" in conteudo
    assert slides_em_revisao.curso.titulo in conteudo
