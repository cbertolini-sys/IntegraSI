"""A fila do professor mostra tambem o que voltou para a equipe.

Depois da fusao de DEVOLVIDO em RASCUNHO, devolver ou reabrir tira o entregavel
da fila: ela filtra EM_REVISAO. O professor perde de vista exatamente o que ele
mandou corrigir.

Sao dois grupos, e nao uma lista so: um espera decisao dele, o outro espera
trabalho da equipe. Misturados, o professor abriria a tela sem saber quais itens
pedem alguma coisa dele agora.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel
from apps.cursos.models import Entregavel


@pytest.fixture
def curso(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    return curso


def em_revisao(curso, tipo):
    e = curso.entregaveis.get(tipo=tipo)
    e.status = StatusEntregavel.EM_REVISAO
    e.save(update_fields=["status", "atualizado_em"])
    return e


def fila(client):
    return client.get(reverse("fila_revisao")).content.decode()


@pytest.mark.django_db
def test_o_reaberto_aparece_na_fila(client, curso, professor):
    slides = em_revisao(curso, TipoEntregavel.SLIDES)
    services.aprovar_entregavel(slides, por=professor, comentario="Ok.")
    services.reabrir_entregavel(slides, por=professor, comentario="Faltou a aula 3.")

    client.force_login(professor)
    html = fila(client)
    assert "Slides e Apresentações" in html
    assert "Reaberto" in html


@pytest.mark.django_db
def test_o_devolvido_tambem(client, curso, professor):
    """Da perspectiva de quem revisa e a mesma situacao: voltou para a equipe por
    decisao dele, e some da vista se a fila so olhar EM_REVISAO."""
    cards = em_revisao(curso, TipoEntregavel.CARDS)
    services.devolver_entregavel(cards, por=professor, comentario="Faltou a fonte.")

    client.force_login(professor)
    assert "Infográficos e Cards Educativos" in fila(client)


@pytest.mark.django_db
def test_os_dois_grupos_ficam_separados(client, curso, professor):
    """Um espera decisao, o outro espera a equipe. A tela precisa dizer qual e
    qual, senao o professor abre nove itens para descobrir quais sao dele."""
    em_revisao(curso, TipoEntregavel.VIDEOS)
    cards = em_revisao(curso, TipoEntregavel.CARDS)
    services.devolver_entregavel(cards, por=professor, comentario="Faltou a fonte.")

    client.force_login(professor)
    html = fila(client)
    assert "Esperando por você" in html
    assert "Com a equipe" in html
    # O que espera decisao vem primeiro: e o que pede acao agora.
    assert html.index("Esperando por você") < html.index("Com a equipe")


@pytest.mark.django_db
def test_rascunho_que_nunca_saiu_dali_nao_entra(client, curso, professor):
    """A fila e do que passou pela revisao. Um entregavel que a equipe ainda nem
    enviou nao voltou de lugar nenhum."""
    client.force_login(professor)
    html = fila(client)
    assert "Caderno de Exercícios" not in html


@pytest.mark.django_db
def test_aprovado_nao_entra(client, curso, professor):
    slides = em_revisao(curso, TipoEntregavel.SLIDES)
    services.aprovar_entregavel(slides, por=professor, comentario="Ok.")
    client.force_login(professor)
    assert "Slides e Apresentações" not in fila(client)


@pytest.mark.django_db
def test_curso_de_outro_professor_nao_entra(
    client, dados_curso, professor, outro_professor, outro_aluno
):
    dados = dict(dados_curso)
    dados["professor_responsavel"] = outro_professor
    alheio = services.criar_curso(**dados)
    services.adicionar_membro(alheio, outro_aluno, por=outro_professor)
    slides = alheio.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    slides.status = StatusEntregavel.EM_REVISAO
    slides.save(update_fields=["status", "atualizado_em"])
    services.devolver_entregavel(slides, por=outro_professor, comentario="Faltou.")

    client.force_login(professor)
    assert "Slides e Apresentações" not in fila(client)


@pytest.mark.django_db
def test_o_numero_do_cartao_bate_com_a_tela(client, curso, professor):
    """O cartao do painel conta o que a tela lista - o defeito que ja apareceu
    duas vezes nesta base foi justamente o numero divergir do destino."""
    from apps.painel.views import _resumo

    em_revisao(curso, TipoEntregavel.VIDEOS)
    cards = em_revisao(curso, TipoEntregavel.CARDS)
    services.devolver_entregavel(cards, por=professor, comentario="Faltou.")

    valor = next(i["valor"] for i in _resumo(professor) if i["url"] == "fila_revisao")
    assert valor == 2

    client.force_login(professor)
    assert fila(client).count("entregavel-da-fila") == 2


@pytest.mark.django_db
def test_a_fila_nao_custa_uma_consulta_por_item(client, curso, professor):
    """Cada linha le a ultima revisao, para dizer se voltou por devolucao ou por
    reabertura."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.cursos.models import Revisao

    for tipo in (TipoEntregavel.SLIDES, TipoEntregavel.CARDS, TipoEntregavel.VIDEOS):
        e = em_revisao(curso, tipo)
        services.devolver_entregavel(e, por=professor, comentario="Faltou.")

    client.force_login(professor)
    with CaptureQueriesContext(connection) as consultas:
        fila(client)
    batidas = [c for c in consultas if Revisao._meta.db_table in c["sql"]]
    assert len(batidas) <= 1, f"{len(batidas)} consultas na tabela de revisões"
