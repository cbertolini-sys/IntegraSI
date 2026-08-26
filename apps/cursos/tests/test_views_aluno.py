import os

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import Rotulo, StatusEntregavel, TipoEntregavel, TipoMidia, TipoPratica
from apps.cursos.models import Anexo, Arquivo


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
    conteudo = resposta.content.decode()
    assert conteudo.count("Entregável enviado para revisão do professor.") == 1


@pytest.mark.django_db
def test_enviar_com_pendencia_mostra_a_lista(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.post(reverse("enviar_entregavel", args=[slides.pk]), follow=True)
    assert "Anexe ao menos um arquivo de slides." in resposta.content.decode()
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.RASCUNHO


@pytest.mark.django_db
def test_secao_de_entregavel_congelado_mostra_conteudo_sem_formulario(
    client, curso_com_equipe, aluno, arquivo_qualquer
):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa fixada</p>"
    secao.save()
    Anexo.objects.create(
        entregavel=plano, tipo_midia=TipoMidia.ARQUIVO, titulo="Plano",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    services.enviar_para_revisao(plano, por=aluno)
    client.force_login(aluno)
    resposta = client.get(reverse("entregavel", args=[plano.pk]))
    conteudo = resposta.content.decode()
    assert "Ementa fixada" in conteudo
    assert "Salvar seção" not in conteudo


@pytest.mark.django_db
def test_salvar_secao_de_outra_equipe_e_bloqueado(client, curso_com_equipe, outro_aluno):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    assert plano.editavel
    secao = plano.secoes.first()
    client.force_login(outro_aluno)
    resposta = client.post(reverse("salvar_secao", args=[secao.pk]), {"conteudo": "<p>Invasao</p>"})
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_anexar_de_outra_equipe_e_bloqueado(client, curso_com_equipe, outro_aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    assert slides.editavel
    client.force_login(outro_aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]),
        {
            "titulo": "Invasao", "url": "https://exemplo.org",
            "rotulo": Rotulo.NENHUM, "tipo_pratica": TipoPratica.NENHUM,
        },
    )
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_enviar_entregavel_de_outra_equipe_e_bloqueado(client, curso_com_equipe, outro_aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    assert slides.editavel
    client.force_login(outro_aluno)
    resposta = client.post(reverse("enviar_entregavel", args=[slides.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_enviar_entregavel_via_get_e_rejeitado(client, curso_com_equipe, aluno, arquivo_qualquer):
    # A vulnerabilidade que este teste crava: sem @require_POST, um GET (por exemplo
    # <img src="/entregaveis/N/enviar/"> numa pagina qualquer que o aluno logado
    # visite) bastava para committar RASCUNHO -> EM_REVISAO, porque CSRF nao se
    # aplica a GET.
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    client.force_login(aluno)
    resposta = client.get(reverse("enviar_entregavel", args=[slides.pk]))
    assert resposta.status_code == 405
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.RASCUNHO


@pytest.mark.django_db
def test_salvar_secao_via_get_e_rejeitado(client, curso_com_equipe, aluno):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    client.force_login(aluno)
    resposta = client.get(reverse("salvar_secao", args=[secao.pk]))
    assert resposta.status_code == 405


@pytest.mark.django_db
def test_anexar_via_get_e_rejeitado(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.get(reverse("anexar", args=[slides.pk]))
    assert resposta.status_code == 405


@pytest.mark.django_db
def test_anexar_arquivo_cria_o_anexo(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    upload = SimpleUploadedFile(
        "slides.pdf", b"%PDF-1.7\n%conteudo de teste\n", content_type="application/pdf"
    )
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]),
        {
            "titulo": "Slides da aula 1", "rotulo": Rotulo.NENHUM, "tipo_pratica": TipoPratica.NENHUM,
            "upload": upload,
        },
        follow=True,
    )
    assert resposta.status_code == 200
    anexo = slides.anexos.get(titulo="Slides da aula 1")
    assert anexo.tipo_midia == TipoMidia.ARQUIVO
    assert anexo.arquivo is not None
    assert anexo.arquivo.mime == "application/pdf"
    assert len(anexo.arquivo.hash_conteudo) == 64
    assert resposta.content.decode().count("Material anexado.") == 1


@pytest.mark.django_db
def test_anexar_link_cria_o_anexo_sem_arquivo(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]),
        {
            "titulo": "Slides no Drive", "url": "https://exemplo.org/slides",
            "rotulo": Rotulo.NENHUM, "tipo_pratica": TipoPratica.NENHUM,
        },
        follow=True,
    )
    assert resposta.status_code == 200
    anexo = slides.anexos.get(titulo="Slides no Drive")
    assert anexo.tipo_midia == TipoMidia.LINK
    assert anexo.arquivo is None
    assert not Arquivo.objects.exists()


@pytest.mark.django_db
def test_anexar_arquivo_e_link_juntos_e_recusado_sem_quebrar(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    upload = SimpleUploadedFile(
        "slides.pdf", b"%PDF-1.7\n%conteudo de teste\n", content_type="application/pdf"
    )
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]),
        {
            "titulo": "Slides duplos", "url": "https://exemplo.org/slides",
            "rotulo": Rotulo.NENHUM, "tipo_pratica": TipoPratica.NENHUM,
            "upload": upload,
        },
        follow=True,
    )
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Anexo de arquivo não tem link." in conteudo
    assert not Anexo.objects.filter(titulo="Slides duplos").exists()
    # A rejeicao nao pode deixar o Arquivo (linha e arquivo em disco) pra tras: o
    # aluno so tentou de novo, mas sem isso cada tentativa acumularia um registro e
    # um arquivo orfaos, e limpar_arquivos_orfaos so existe no Plano 4.
    assert Arquivo.objects.count() == 0
    arquivos_em_disco = [
        nome for _, _, nomes in os.walk(settings.MEDIA_ROOT) for nome in nomes
    ]
    assert arquivos_em_disco == []
