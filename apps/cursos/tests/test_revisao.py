import pytest
from django.core.exceptions import ValidationError

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo, Revisao


@pytest.fixture
def slides_prontos(dados_curso, aluno, arquivo_qualquer):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    return slides


@pytest.mark.django_db
def test_enviar_para_revisao_muda_o_estado(slides_prontos, aluno):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.EM_REVISAO
    assert slides_prontos.editavel is False


@pytest.mark.django_db
def test_enviar_com_pendencia_e_recusado(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    with pytest.raises(ValidationError) as erro:
        services.enviar_para_revisao(slides, por=aluno)
    assert "slides" in erro.value.messages[0].lower()
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.RASCUNHO


@pytest.mark.django_db
def test_aprovar_registra_revisao(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.aprovar_entregavel(slides_prontos, por=professor, comentario="Otimo trabalho.")
    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.APROVADO
    revisao = Revisao.objects.get(entregavel=slides_prontos)
    assert revisao.decisao == Revisao.APROVADO
    assert revisao.revisor == professor


@pytest.mark.django_db
def test_devolver_exige_comentario(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    with pytest.raises(ValidationError):
        services.devolver_entregavel(slides_prontos, por=professor, comentario="   ")
    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.EM_REVISAO


@pytest.mark.django_db
def test_devolver_reabre_para_edicao(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.devolver_entregavel(slides_prontos, por=professor, comentario="Faltou a ultima aula.")
    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.DEVOLVIDO
    assert slides_prontos.editavel is True


@pytest.mark.django_db
def test_ciclo_de_devolucao_e_reenvio_guarda_o_historico(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.devolver_entregavel(slides_prontos, por=professor, comentario="Corrija a capa.")
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.aprovar_entregavel(slides_prontos, por=professor)
    assert list(Revisao.objects.filter(entregavel=slides_prontos).values_list("decisao", flat=True)) == [
        Revisao.DEVOLVIDO,
        Revisao.APROVADO,
    ]


@pytest.mark.django_db
def test_nao_se_aprova_entregavel_que_nao_esta_em_revisao(slides_prontos, professor):
    with pytest.raises(ValidationError):
        services.aprovar_entregavel(slides_prontos, por=professor)


@pytest.mark.django_db
def test_nao_se_reenvia_entregavel_aprovado(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.aprovar_entregavel(slides_prontos, por=professor)
    with pytest.raises(ValidationError):
        services.enviar_para_revisao(slides_prontos, por=aluno)


@pytest.mark.django_db
def test_nao_se_reenvia_entregavel_ja_em_revisao(slides_prontos, aluno):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    with pytest.raises(ValidationError):
        services.enviar_para_revisao(slides_prontos, por=aluno)
    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.EM_REVISAO


@pytest.mark.django_db
def test_nao_se_devolve_entregavel_que_nao_esta_em_revisao(slides_prontos, professor):
    with pytest.raises(ValidationError):
        services.devolver_entregavel(slides_prontos, por=professor, comentario="Corrija algo.")


@pytest.mark.django_db
def test_aprovar_sem_comentario_grava_comentario_vazio(slides_prontos, aluno, professor):
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.aprovar_entregavel(slides_prontos, por=professor)
    revisao = Revisao.objects.get(entregavel=slides_prontos)
    assert revisao.comentario == ""


@pytest.mark.django_db
def test_aprovar_e_atomico_e_desfaz_o_status_se_a_revisao_falhar(slides_prontos, aluno, professor, monkeypatch):
    services.enviar_para_revisao(slides_prontos, por=aluno)

    def explode(*args, **kwargs):
        raise RuntimeError("falha simulada ao gravar a revisao")

    monkeypatch.setattr(Revisao.objects, "create", explode)

    with pytest.raises(RuntimeError):
        services.aprovar_entregavel(slides_prontos, por=professor)

    slides_prontos.refresh_from_db()
    assert slides_prontos.status == StatusEntregavel.EM_REVISAO
    assert not Revisao.objects.filter(entregavel=slides_prontos).exists()


@pytest.mark.django_db
def test_curso_so_fica_pronto_com_os_cinco_aprovados(slides_prontos, aluno, professor):
    curso = slides_prontos.curso
    assert curso.pronto_para_o_coordenador is False
    services.enviar_para_revisao(slides_prontos, por=aluno)
    services.aprovar_entregavel(slides_prontos, por=professor)
    curso.refresh_from_db()
    assert curso.pronto_para_o_coordenador is False
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    assert curso.pronto_para_o_coordenador is True
