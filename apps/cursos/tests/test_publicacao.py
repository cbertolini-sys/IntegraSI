import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel
from apps.cursos.models import LogTransicaoCurso, Revisao
from apps.notificacoes.models import Notificacao


@pytest.fixture
def curso_pronto(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    return curso


@pytest.mark.django_db
def test_submeter_exige_os_cinco_aprovados(dados_curso, professor):
    curso = services.criar_curso(**dados_curso)
    with pytest.raises(ValidationError):
        services.submeter_ao_coordenador(curso, por=professor)


@pytest.mark.django_db
def test_submeter_muda_o_estado_e_registra_o_log(curso_pronto, professor):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.AGUARDANDO_COORDENADOR
    log = LogTransicaoCurso.objects.get(curso=curso_pronto)
    assert log.de_status == StatusCurso.EM_PRODUCAO
    assert log.usuario == professor


@pytest.mark.django_db
def test_submeter_revalida_os_dados_do_curso(curso_pronto, professor):
    """O curso pode ser editado depois do plano de ensino aprovado (spec 6)."""
    curso_pronto.carga_horaria = 1
    curso_pronto.save()
    curso_pronto.referencial = None
    curso_pronto.save()
    from apps.cursos.models import Curso

    # carga_horaria nao tem null=True (NOT NULL no banco); 0 e o valor falso que
    # o .update() aceita sem violar a constraint, e continua acionando "informe a
    # carga horaria" em validacoes.dados_do_curso.
    Curso.objects.filter(pk=curso_pronto.pk).update(carga_horaria=0)
    curso_pronto.refresh_from_db()
    with pytest.raises(ValidationError):
        services.submeter_ao_coordenador(curso_pronto, por=professor)


@pytest.mark.django_db
def test_aluno_nao_submete(curso_pronto, aluno):
    with pytest.raises(PermissionDenied):
        services.submeter_ao_coordenador(curso_pronto, por=aluno)


@pytest.mark.django_db
def test_professor_nao_publica(curso_pronto, professor):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    with pytest.raises(PermissionDenied):
        services.publicar_curso(curso_pronto, por=professor)


@pytest.mark.django_db
def test_professor_nao_devolve(curso_pronto, professor):
    """Apenas o coordenador devolve o curso (spec 5, 11) - mesmo o professor
    responsavel, que submeteu, nao pode se auto-devolver."""
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    with pytest.raises(PermissionDenied):
        services.devolver_curso(curso_pronto, por=professor, comentario="Preciso revisar.")


@pytest.mark.django_db
def test_professor_nao_despublica(curso_pronto, professor, coordenador):
    """Apenas o coordenador despublica o curso (spec 5, 11)."""
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    with pytest.raises(PermissionDenied):
        services.despublicar_curso(curso_pronto, por=professor, motivo="Material desatualizado.")


@pytest.mark.django_db
def test_coordenador_publica_e_avisa_a_equipe(curso_pronto, professor, coordenador, aluno):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.PUBLICADO
    assert curso_pronto.publicado_em is not None
    destinatarios = set(Notificacao.objects.values_list("destinatario", flat=True))
    assert {aluno.email, professor.email} <= destinatarios


@pytest.mark.django_db
def test_publicar_curso_que_nao_foi_submetido_e_recusado(curso_pronto, coordenador):
    with pytest.raises(ValidationError):
        services.publicar_curso(curso_pronto, por=coordenador)


@pytest.mark.django_db
def test_devolver_ao_professor_exige_comentario(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    with pytest.raises(ValidationError):
        services.devolver_curso(curso_pronto, por=coordenador, comentario=" ")


@pytest.mark.django_db
def test_devolvido_volta_a_producao_ao_ser_submetido_de_novo(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.devolver_curso(curso_pronto, por=coordenador, comentario="Faltou detalhar o cronograma.")
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.DEVOLVIDO
    curso_pronto.entregaveis.update(status=StatusEntregavel.APROVADO)
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.AGUARDANDO_COORDENADOR


@pytest.mark.django_db
def test_despublicar_registra_o_motivo(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    services.despublicar_curso(curso_pronto, por=coordenador, motivo="Material desatualizado.")
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.DESPUBLICADO
    log = LogTransicaoCurso.objects.filter(para_status=StatusCurso.DESPUBLICADO).get()
    assert log.observacao == "Material desatualizado."


@pytest.mark.django_db
def test_devolver_curso_reabre_os_cinco_entregaveis(curso_pronto, professor, coordenador, aluno):
    """R54: o coordenador devolve o curso, nao cada entregavel - mas os cinco
    entregaveis continuam APROVADO (portanto congelados) se ninguem os reabrir, e a
    equipe fica sem poder agir sobre o feedback recebido. devolver_curso precisa
    devolver tambem os cinco entregaveis, na mesma transacao, sem criar Revisao (a
    decisao pedagogica sobre cada entrega continua sendo so do professor)."""
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    total_revisoes_antes = Revisao.objects.count()

    services.devolver_curso(curso_pronto, por=coordenador, comentario="Revisar o material didatico.")

    status_entregaveis = set(curso_pronto.entregaveis.values_list("status", flat=True))
    assert status_entregaveis == {StatusEntregavel.DEVOLVIDO}
    assert all(e.editavel for e in curso_pronto.entregaveis.all())
    assert Revisao.objects.count() == total_revisoes_antes

    # A equipe consegue voltar a editar uma secao do plano de ensino.
    plano = curso_pronto.entregaveis.get(tipo="PLANO_ENSINO")
    secao = plano.secoes.first()
    secao.conteudo = "Texto revisado apos a devolucao."
    secao.atualizado_por = aluno
    secao.save()
    secao.refresh_from_db()
    assert "revisado" in secao.conteudo
