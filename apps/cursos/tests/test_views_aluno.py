import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo


@pytest.fixture
def curso_com_equipe(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso


@pytest.mark.django_db
def test_meus_cursos_lista_so_os_do_aluno(client, curso_com_equipe, aluno, outro_aluno):
    client.force_login(outro_aluno)
    resposta = client.get(reverse("meus_cursos"))
    assert curso_com_equipe.titulo not in resposta.content.decode()
    client.force_login(aluno)
    resposta = client.get(reverse("meus_cursos"))
    assert curso_com_equipe.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_curso_de_outra_equipe_devolve_403(client, curso_com_equipe, outro_aluno):
    client.force_login(outro_aluno)
    resposta = client.get(reverse("curso", args=[curso_com_equipe.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_painel_do_curso_mostra_os_cinco_entregaveis(client, curso_com_equipe, aluno):
    client.force_login(aluno)
    resposta = client.get(reverse("curso", args=[curso_com_equipe.pk]))
    conteudo = resposta.content.decode()
    assert conteudo.count("entregavel-card") == 5


@pytest.mark.django_db
def test_entregavel_mostra_o_que_falta(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.get(reverse("entregavel", args=[slides.pk]))
    assert "Anexe ao menos um arquivo de slides." in resposta.content.decode()


@pytest.mark.django_db
def test_entregavel_de_outra_equipe_devolve_403(client, curso_com_equipe, outro_aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(outro_aluno)
    resposta = client.get(reverse("entregavel", args=[slides.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_anexar_em_entregavel_em_revisao_e_bloqueado(client, curso_com_equipe, aluno, arquivo_qualquer):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()
    Anexo.objects.create(
        entregavel=plano, tipo_midia=TipoMidia.ARQUIVO, titulo="Plano",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    services.enviar_para_revisao(plano, por=aluno)
    client.force_login(aluno)
    resposta = client.post(reverse("anexar", args=[plano.pk]), {"titulo": "Outro", "url": "https://exemplo.org"})
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_salvar_secao_guarda_o_conteudo_e_o_autor(client, curso_com_equipe, aluno):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    client.force_login(aluno)
    resposta = client.post(reverse("salvar_secao", args=[secao.pk]), {"conteudo": "<p>Ementa nova</p>"})
    assert resposta.status_code == 200
    secao.refresh_from_db()
    assert "Ementa nova" in secao.conteudo
    assert secao.atualizado_por == aluno


@pytest.mark.django_db
def test_salvar_secao_de_entregavel_em_revisao_e_bloqueado(client, curso_com_equipe, aluno, arquivo_qualquer):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()
    Anexo.objects.create(
        entregavel=plano, tipo_midia=TipoMidia.ARQUIVO, titulo="Plano",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    services.enviar_para_revisao(plano, por=aluno)
    client.force_login(aluno)
    resposta = client.post(reverse("salvar_secao", args=[secao.pk]), {"conteudo": "<p>Mudanca</p>"})
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_enviar_para_revisao_pela_tela(client, curso_com_equipe, aluno, arquivo_qualquer):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    client.force_login(aluno)
    resposta = client.post(reverse("enviar_entregavel", args=[slides.pk]), follow=True)
    assert resposta.status_code == 200
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.EM_REVISAO


@pytest.mark.django_db
def test_enviar_com_pendencia_mostra_a_lista(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.post(reverse("enviar_entregavel", args=[slides.pk]), follow=True)
    assert "Anexe ao menos um arquivo de slides." in resposta.content.decode()
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.RASCUNHO
