"""O coordenador e um professor como qualquer outro, mais as funcoes de catalogo.

A regra antiga dizia `usuario.e_coordenador or (e_professor and e_responsavel)`,
o que dava ao coordenador poder de producao em TODO curso: aprovar entregavel da
equipe alheia, mexer na equipe dos outros, editar a ficha de qualquer curso.

A spec dizia "tudo o que um professor faz, mais...", e a frase e ambigua: "tudo o
que um professor faz" pode ser NOS CURSOS DELE ou EM TODOS. O codigo escolhia "em
todos"; a decisao do produto e "nos cursos dele".

O que ele faz em curso alheio continua: autorizar (publicar e devolver),
despublicar, republicar e gerenciar pessoas. E VER, porque nao da para autorizar
o que nao se pode ler.
"""

import pytest

from apps.cursos import permissions, services
from apps.cursos.models import Curso


@pytest.fixture
def curso_da_ana(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    return curso


@pytest.fixture
def curso_do_coordenador(dados_curso, coordenador):
    """O coordenador tambem propoe curso: ali ele e o professor responsavel."""
    dados = dict(dados_curso)
    dados["professor_responsavel"] = coordenador
    return services.criar_curso(**dados)


# --- em curso alheio, ele nao produz -----------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "regra", ["pode_revisar", "pode_gerir_equipe", "pode_editar_ficha"]
)
def test_o_coordenador_nao_produz_em_curso_alheio(curso_da_ana, coordenador, regra):
    assert getattr(permissions, regra)(coordenador, curso_da_ana) is False


@pytest.mark.django_db
def test_mas_abrir_nova_versao_continua_sendo_dele(curso_da_ana, coordenador):
    """A excecao entre as quatro, e ela tem tres testemunhas.

    Abrir nova versao e cuidado do CATALOGO, e nao producao: a spec 4.5 diz "o
    coordenador ou o professor responsavel pela versao atual", o fluxo da
    coordenacao na pagina Sobre a lista ao lado de despublicar e republicar, e
    quarenta testes de versao a exercitam pelo coordenador. E por ela que um curso
    desatualizado no ar volta a ser corrigido.
    """
    assert permissions.pode_abrir_versao(coordenador, curso_da_ana) is True


@pytest.mark.django_db
def test_mas_continua_vendo_o_curso_alheio(curso_da_ana, coordenador):
    """Nao da para autorizar o que nao se pode ler: a tela de analise mostra as
    secoes e os anexos."""
    assert permissions.pode_ver_curso(coordenador, curso_da_ana) is True


@pytest.mark.django_db
def test_e_continua_autorizando_e_despublicando(coordenador):
    assert permissions.pode_publicar(coordenador) is True


# --- no curso dele, ele e professor -------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "regra", ["pode_revisar", "pode_gerir_equipe", "pode_editar_ficha", "pode_abrir_versao"]
)
def test_no_proprio_curso_ele_faz_tudo_de_professor(curso_do_coordenador, coordenador, regra):
    assert getattr(permissions, regra)(coordenador, curso_do_coordenador) is True


@pytest.mark.django_db
def test_o_professor_responsavel_nao_perdeu_nada(curso_da_ana, professor):
    """O outro lado: a mudanca e sobre o coordenador em curso alheio, e nao pode
    ter tirado poder de quem responde pelo curso."""
    for regra in ("pode_revisar", "pode_gerir_equipe", "pode_editar_ficha", "pode_abrir_versao"):
        assert getattr(permissions, regra)(professor, curso_da_ana) is True, regra


# --- e a tela recusa junto ----------------------------------------------------


@pytest.mark.django_db
def test_a_tela_de_decisao_recusa_o_coordenador_em_curso_alheio(
    client, curso_da_ana, coordenador
):
    """Nao basta a regra: era digitando o endereco que o coordenador alcancava a
    revisao de um curso que nao e dele."""
    from django.urls import reverse
    from apps.cursos.choices import TipoEntregavel

    slides = curso_da_ana.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(coordenador)
    assert client.get(reverse("revisar", args=[slides.pk])).status_code == 403


@pytest.mark.django_db
def test_a_tela_de_equipe_tambem(client, curso_da_ana, coordenador):
    from django.urls import reverse

    client.force_login(coordenador)
    assert client.get(reverse("equipe", args=[curso_da_ana.pk])).status_code == 403


@pytest.mark.django_db
def test_a_tela_de_analise_continua_aberta_para_ele(client, curso_da_ana, coordenador):
    """O que ele faz em curso alheio continua alcancavel."""
    from django.urls import reverse

    client.force_login(coordenador)
    assert client.get(reverse("analisar_curso", args=[curso_da_ana.pk])).status_code == 200
