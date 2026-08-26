import pytest
from django.core.exceptions import ValidationError

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel
from apps.cursos.models import Entregavel, Secao


@pytest.mark.django_db
def test_criar_curso_gera_os_cinco_entregaveis(dados_curso):
    curso = services.criar_curso(**dados_curso)
    tipos = list(curso.entregaveis.values_list("tipo", flat=True))
    assert sorted(tipos) == sorted([t.value for t in TipoEntregavel])
    assert all(e.status == StatusEntregavel.RASCUNHO for e in curso.entregaveis.all())


@pytest.mark.django_db
def test_criar_curso_gera_as_secoes_do_plano_de_ensino(dados_curso):
    curso = services.criar_curso(**dados_curso)
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    titulos = list(plano.secoes.order_by("ordem").values_list("titulo", flat=True))
    assert titulos == services.SECOES_PLANO_ENSINO
    assert all(secao.conteudo == "" for secao in plano.secoes.all())


@pytest.mark.django_db
def test_apenas_o_plano_de_ensino_nasce_com_secoes(dados_curso):
    curso = services.criar_curso(**dados_curso)
    outros = curso.entregaveis.exclude(tipo=TipoEntregavel.PLANO_ENSINO)
    assert Secao.objects.filter(entregavel__in=outros).count() == 0


@pytest.mark.django_db
def test_adicionar_o_primeiro_membro_leva_o_curso_para_producao(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    assert curso.status == StatusCurso.RASCUNHO
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO


@pytest.mark.django_db
def test_entregavel_repetido_no_mesmo_curso_e_recusado(dados_curso):
    curso = services.criar_curso(**dados_curso)
    with pytest.raises(ValidationError):
        Entregavel.objects.create(curso=curso, tipo=TipoEntregavel.SLIDES)


@pytest.mark.django_db
def test_conteudo_da_secao_e_sanitizado(dados_curso):
    curso = services.criar_curso(**dados_curso)
    secao = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO).secoes.first()
    secao.conteudo = "<p>Texto</p><script>alert(1)</script>"
    secao.save()
    secao.refresh_from_db()
    assert "<p>Texto</p>" in secao.conteudo
    assert "script" not in secao.conteudo


@pytest.mark.django_db
def test_sanitizacao_roda_mesmo_com_update_fields(dados_curso):
    """A sanitizacao nao pode viver dentro do guarda do update_fields: um save
    direcionado e exatamente o caminho que um form de edicao rapida usaria, e e
    o caminho que mais precisa ficar seguro contra script no navegador."""
    curso = services.criar_curso(**dados_curso)
    secao = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO).secoes.first()
    secao.conteudo = "<p>Texto</p><script>alert(1)</script>"
    secao.save(update_fields=["conteudo"])
    secao.refresh_from_db()
    assert "<p>Texto</p>" in secao.conteudo
    assert "script" not in secao.conteudo


@pytest.mark.django_db
def test_criar_curso_e_atomico(dados_curso):
    dados_curso["carga_horaria"] = 0
    from apps.cursos.models import Curso

    with pytest.raises(ValidationError):
        services.criar_curso(**dados_curso)
    assert Curso.objects.count() == 0
    assert Entregavel.objects.count() == 0
