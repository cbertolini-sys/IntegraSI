import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoPublico
from apps.cursos.models import Tema


def publica(curso, membro_equipe, professor, coordenador):
    # adicionar_membro tira o curso de RASCUNHO para EM_PRODUCAO (services.py); sem
    # isso submeter_ao_coordenador recusa por status, nao pelos entregaveis. Usa um
    # aluno so da producao (nao a fixture 'aluno') para o teste de dado pessoal
    # poder adicionar 'aluno' por conta propria, sem colidir com a constraint de
    # membro unico por curso.
    services.adicionar_membro(curso, membro_equipe, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    return curso


@pytest.fixture
def curso_publicado(dados_curso, outro_aluno, professor, coordenador):
    curso = services.criar_curso(**dados_curso)
    return publica(curso, outro_aluno, professor, coordenador)


@pytest.mark.django_db
def test_catalogo_e_publico(client, curso_publicado):
    resposta = client.get(reverse("catalogo"))
    assert resposta.status_code == 200
    assert curso_publicado.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_curso_em_producao_nao_aparece(client, dados_curso):
    curso = services.criar_curso(**dados_curso)
    resposta = client.get(reverse("catalogo"))
    assert curso.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_curso_despublicado_sai_do_catalogo(client, curso_publicado, coordenador):
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Desatualizado.")
    resposta = client.get(reverse("catalogo"))
    assert curso_publicado.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_pagina_publica_de_curso_nao_publicado_devolve_404(client, dados_curso):
    curso = services.criar_curso(**dados_curso)
    resposta = client.get(reverse("catalogo_curso", args=[curso.pk]))
    assert resposta.status_code == 404


@pytest.mark.django_db
def test_pagina_publica_mostra_dados_do_curso_e_nao_os_materiais(client, curso_publicado):
    resposta = client.get(reverse("catalogo_curso", args=[curso_publicado.pk]))
    conteudo = resposta.content.decode()
    assert curso_publicado.resumo in conteudo
    assert "Plano de Ensino" not in conteudo


@pytest.mark.django_db
def test_filtro_por_publico_alvo(client, curso_publicado, dados_curso, outro_aluno, professor, coordenador):
    dados_curso.update(
        titulo="Cidadania digital para adultos", tipo_publico=TipoPublico.COMUNITARIO,
        etapa_ano="", publico_descricao="Adultos em vulnerabilidade digital",
    )
    publica(services.criar_curso(**dados_curso), outro_aluno, professor, coordenador)

    resposta = client.get(reverse("catalogo"), {"etapa": "EF05"})
    conteudo = resposta.content.decode()
    assert curso_publicado.titulo in conteudo
    assert "Cidadania digital para adultos" not in conteudo


@pytest.mark.django_db
def test_filtro_por_tema(client, curso_publicado, professor):
    tema = Tema.objects.create(nome="Robotica Educacional")
    services.definir_temas(curso_publicado, [tema], por=professor)
    assert curso_publicado.titulo in client.get(reverse("catalogo"), {"tema": tema.slug}).content.decode()
    assert curso_publicado.titulo not in client.get(reverse("catalogo"), {"tema": "outro"}).content.decode()


@pytest.mark.django_db
def test_busca_no_catalogo(client, curso_publicado):
    assert curso_publicado.titulo in client.get(reverse("catalogo"), {"q": "pensamento"}).content.decode()
    assert curso_publicado.titulo not in client.get(reverse("catalogo"), {"q": "astronomia"}).content.decode()


@pytest.mark.django_db
def test_catalogo_nao_expoe_dado_pessoal_da_equipe(client, curso_publicado, aluno, professor):
    services.adicionar_membro(curso_publicado, aluno, por=professor)
    resposta = client.get(reverse("catalogo_curso", args=[curso_publicado.pk]))
    conteudo = resposta.content.decode()
    assert aluno.cpf not in conteudo
    assert aluno.email not in conteudo
