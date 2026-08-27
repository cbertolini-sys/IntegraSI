import pytest
from django.urls import reverse

from apps.cursos import services, validacoes
from apps.cursos.admin import CursoAdmin
from apps.cursos.choices import StatusCurso, TipoEntregavel
from apps.referenciais.models import Categoria, Competencia, Referencial


def test_curso_admin_usa_filtro_horizontal_para_competencias_e_temas():
    assert "competencias" in CursoAdmin.filter_horizontal
    assert "temas" in CursoAdmin.filter_horizontal


@pytest.mark.django_db
def test_coordenador_anexa_competencias_pelo_admin_libera_a_pendencia_do_plano(
    client, dados_curso, coordenador
):
    """Sem Curso registrado no Admin, nada no sistema escreve Curso.competencias
    (CursoForm exclui o campo de proposito), entao um curso com referencial fica
    para sempre bloqueado nesta pendencia (item 3 da revisao de branco). Este teste
    prova o desbloqueio ponta a ponta: o Admin grava a M2M e a mesma pendencia que
    bloqueava o Plano de Ensino desaparece."""
    curso = services.criar_curso(**dados_curso)
    referencial = Referencial.objects.create(
        nome="BNCC da Computacao", sigla="BNCC-COMP", min_competencias=1, max_competencias=5
    )
    categoria = Categoria.objects.create(referencial=referencial, nome="Mundo Digital", ordem=1)
    competencia = Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="EF05CO01",
        descricao="Descricao", etapa="EF05", ordem=1,
    )
    curso.referencial = referencial
    curso.save()

    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    assert any("competências" in f for f in validacoes.pendencias(plano))

    coordenador.is_staff = True
    coordenador.is_superuser = True
    coordenador.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(coordenador)

    resposta = client.post(
        reverse("admin:cursos_curso_change", args=[curso.pk]),
        {
            "titulo": curso.titulo,
            "resumo": curso.resumo,
            "edicao": curso.edicao_id,
            "professor_responsavel": curso.professor_responsavel_id,
            "tipo_publico": curso.tipo_publico,
            "etapa_ano": curso.etapa_ano,
            "publico_descricao": curso.publico_descricao,
            "referencial": referencial.pk,
            "competencias": [competencia.pk],
            "carga_horaria": curso.carga_horaria,
            "formato": curso.formato,
            "pre_requisitos": curso.pre_requisitos,
            "temas": [],
            "palavras_chave": curso.palavras_chave,
            "status": curso.status,
        },
    )
    if resposta.status_code == 200:
        assert not resposta.context["adminform"].form.errors, resposta.context[
            "adminform"
        ].form.errors
    assert resposta.status_code == 302

    curso.refresh_from_db()
    assert list(curso.competencias.values_list("pk", flat=True)) == [competencia.pk]
    assert not any("competências" in f for f in validacoes.pendencias(plano))


def test_curso_admin_declara_status_somente_leitura():
    assert "status" in CursoAdmin.readonly_fields


@pytest.mark.django_db
def test_curso_admin_nao_aceita_editar_status_pelo_formulario(client, dados_curso, coordenador):
    """R56: so services.py move status de Curso. Sem readonly_fields, este POST
    publicaria o curso sem passar por services.publicar_curso - portanto sem
    publicado_em, sem LogTransicaoCurso e sem a notificacao a equipe que o
    servico enfileira."""
    curso = services.criar_curso(**dados_curso)
    assert curso.status == StatusCurso.RASCUNHO

    coordenador.is_staff = True
    coordenador.is_superuser = True
    coordenador.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(coordenador)

    resposta = client.post(
        reverse("admin:cursos_curso_change", args=[curso.pk]),
        {
            "titulo": curso.titulo,
            "resumo": curso.resumo,
            "edicao": curso.edicao_id,
            "professor_responsavel": curso.professor_responsavel_id,
            "tipo_publico": curso.tipo_publico,
            "etapa_ano": curso.etapa_ano,
            "publico_descricao": curso.publico_descricao,
            "carga_horaria": curso.carga_horaria,
            "formato": curso.formato,
            "pre_requisitos": curso.pre_requisitos,
            "temas": [],
            "competencias": [],
            "palavras_chave": curso.palavras_chave,
            "status": StatusCurso.PUBLICADO,
        },
    )
    if resposta.status_code == 200:
        assert not resposta.context["adminform"].form.errors, resposta.context[
            "adminform"
        ].form.errors
    assert resposta.status_code == 302

    curso.refresh_from_db()
    assert curso.status == StatusCurso.RASCUNHO
    assert curso.publicado_em is None


@pytest.mark.django_db
def test_curso_admin_recusa_adicionar_curso(client, coordenador):
    """R56: criar Curso pelo Admin pula services.criar_curso e, com ele, os cinco
    Entregavel que o resto do sistema pressupoe que todo curso tem."""
    coordenador.is_staff = True
    coordenador.is_superuser = True
    coordenador.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(coordenador)
    resposta = client.get(reverse("admin:cursos_curso_add"))
    assert resposta.status_code == 403
