"""Cada item de "Esperando por você" diz quem o produziu.

Autor e quem deixou marca no entregavel: escreveu uma secao (`Secao.atualizado_por`)
ou enviou um anexo (`Anexo.enviado_por`). Sem os nomes, o professor que orienta
varias equipes abre o item para descobrir de quem e o trabalho que vai julgar.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo


@pytest.fixture
def curso(dados_curso, professor, aluno, outro_aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    services.adicionar_membro(curso, outro_aluno, por=professor)
    return curso


def em_revisao(curso, tipo):
    e = curso.entregaveis.get(tipo=tipo)
    e.status = StatusEntregavel.EM_REVISAO
    e.save(update_fields=["status", "atualizado_em"])
    return e


def escreveu(entregavel, pessoa):
    secao = entregavel.secoes.first()
    secao.conteudo = "<p>Texto.</p>"
    secao.atualizado_por = pessoa
    secao.save()


def anexou(entregavel, pessoa, titulo="Link"):
    Anexo.objects.create(
        entregavel=entregavel, tipo_midia=TipoMidia.LINK, titulo=titulo,
        url="https://exemplo.org", enviado_por=pessoa,
    )


def linha(client, entregavel):
    """So o <li> do entregavel, para que um nome de outra linha nao conte."""
    html = client.get(reverse("fila_revisao")).content.decode()
    inicio = html.index(reverse("revisar", args=[entregavel.pk]))
    return html[inicio : html.index("</li>", inicio)]


@pytest.mark.django_db
def test_quem_escreveu_secao_aparece(client, curso, professor, aluno):
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    escreveu(plano, aluno)
    em_revisao(curso, TipoEntregavel.PLANO_ENSINO)

    client.force_login(professor)
    assert "Ana Alves" in linha(client, plano)


@pytest.mark.django_db
def test_quem_enviou_anexo_aparece(client, curso, professor, outro_aluno):
    cards = em_revisao(curso, TipoEntregavel.CARDS)
    anexou(cards, outro_aluno)

    client.force_login(professor)
    assert "Davi Dias" in linha(client, cards)


@pytest.mark.django_db
def test_cada_autor_aparece_uma_vez(client, curso, professor, aluno):
    cards = em_revisao(curso, TipoEntregavel.CARDS)
    anexou(cards, aluno, "Um")
    anexou(cards, aluno, "Dois")

    client.force_login(professor)
    assert linha(client, cards).count("Ana Alves") == 1


@pytest.mark.django_db
def test_autor_de_outro_entregavel_nao_entra_na_linha(
    client, curso, professor, aluno, outro_aluno
):
    """Membro da equipe que nao tocou neste entregavel nao e autor dele: a linha
    nao pode virar a lista da equipe."""
    cards = em_revisao(curso, TipoEntregavel.CARDS)
    videos = em_revisao(curso, TipoEntregavel.VIDEOS)
    anexou(cards, aluno)
    anexou(videos, outro_aluno)

    client.force_login(professor)
    assert "Davi Dias" not in linha(client, cards)
    assert "Ana Alves" not in linha(client, videos)


@pytest.mark.django_db
def test_os_autores_nao_custam_uma_consulta_por_item(client, curso, professor, aluno):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.contas.models import Usuario

    for tipo in (TipoEntregavel.PLANO_ENSINO, TipoEntregavel.CARDS, TipoEntregavel.VIDEOS):
        e = em_revisao(curso, tipo)
        anexou(e, aluno)
        if e.secoes.exists():
            escreveu(e, aluno)
    # Sem secao escrita, tirar o prefetch das secoes passaria calado.
    assert any(e.secoes.filter(atualizado_por=aluno).exists() for e in curso.entregaveis.all())

    client.force_login(professor)
    with CaptureQueriesContext(connection) as consultas:
        client.get(reverse("fila_revisao"))
    tabela = Usuario._meta.db_table
    batidas = [c for c in consultas if f'FROM "{tabela}"' in c["sql"]]
    # Uma para a sessao (request.user) e no maximo duas para os autores
    # (secoes e anexos), seja qual for o numero de itens.
    assert len(batidas) <= 3, f"{len(batidas)} consultas na tabela de usuários"
