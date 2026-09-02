"""DEVOLVIDO deixou de ser status, e virou leitura do historico.

`DEVOLVIDO` e `RASCUNHO` eram o mesmo estado funcional: os dois `editavel`, e
nenhuma regra do sistema os distinguia. O que a fusao ameacava perder era o sinal
na LISTA de entregaveis do painel, que mostra so o status - um devolvido passaria
a ler "Rascunho", igual a um que ninguem tocou.

O sinal volta derivado da ultima revisao, e nao gravado numa segunda fonte de
verdade que sairia de sincronia na primeira edicao pelo Admin.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel
from apps.cursos.models import Revisao


@pytest.fixture
def slides_em_revisao(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    slides.status = StatusEntregavel.EM_REVISAO
    slides.save(update_fields=["status", "atualizado_em"])
    return slides


# --- o status sumiu -----------------------------------------------------------


def test_o_vocabulario_nao_tem_mais_devolvido():
    assert "DEVOLVIDO" not in StatusEntregavel.values
    # No historico ele continua: la a palavra descreve uma DECISAO, e nao um
    # estado, e e de la que a lista passa a ler o sinal.
    assert Revisao.DEVOLVIDO in dict(Revisao.DECISOES)


@pytest.mark.django_db
def test_devolver_deixa_o_entregavel_editavel_em_rascunho(slides_em_revisao, professor):
    services.devolver_entregavel(
        slides_em_revisao, por=professor, comentario="<p>Faltou a fonte.</p>"
    )
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.RASCUNHO
    assert slides_em_revisao.editavel


@pytest.mark.django_db
def test_reabrir_tambem_deixa_em_rascunho(slides_em_revisao, professor):
    services.aprovar_entregavel(slides_em_revisao, por=professor, comentario="Ok.")
    services.reabrir_entregavel(slides_em_revisao, por=professor, comentario="Faltou.")
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.RASCUNHO
    assert slides_em_revisao.editavel


# --- a situacao, derivada -----------------------------------------------------


@pytest.mark.django_db
def test_sem_revisao_a_situacao_e_o_proprio_status(dados_curso, professor):
    curso = services.criar_curso(**dados_curso)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    assert slides.situacao.rotulo == "Rascunho"
    assert slides.situacao.tom == ""


@pytest.mark.django_db
def test_devolvido_continua_se_anunciando_na_lista(slides_em_revisao, professor):
    services.devolver_entregavel(slides_em_revisao, por=professor, comentario="Faltou.")
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.situacao.rotulo == "Devolvido"
    assert slides_em_revisao.situacao.tom == "atencao"


@pytest.mark.django_db
def test_reaberto_se_anuncia_como_reaberto(slides_em_revisao, professor):
    """Nao e "devolvido": devolver responde a um envio, reabrir desfaz uma
    aprovacao. A lista mostra a diferenca porque o historico a guarda."""
    services.aprovar_entregavel(slides_em_revisao, por=professor, comentario="Ok.")
    services.reabrir_entregavel(slides_em_revisao, por=professor, comentario="Faltou.")
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.situacao.rotulo == "Reaberto"


@pytest.mark.django_db
def test_o_historico_nao_sobrepoe_o_estado_atual(slides_em_revisao, professor):
    """Um entregavel devolvido e reenviado esta EM REVISAO, e e isso que a lista
    mostra - a ultima revisao so fala quando o entregavel voltou para a equipe."""
    services.devolver_entregavel(slides_em_revisao, por=professor, comentario="Faltou.")
    slides_em_revisao.refresh_from_db()
    slides_em_revisao.status = StatusEntregavel.EM_REVISAO
    slides_em_revisao.save(update_fields=["status", "atualizado_em"])
    assert slides_em_revisao.situacao.rotulo == "Em revisão"

    slides_em_revisao.status = StatusEntregavel.APROVADO
    slides_em_revisao.save(update_fields=["status", "atualizado_em"])
    assert slides_em_revisao.situacao.rotulo == "Aprovado"


# --- a lista do painel --------------------------------------------------------


@pytest.mark.django_db
def test_a_lista_do_curso_mostra_devolvido(client, slides_em_revisao, professor):
    services.devolver_entregavel(slides_em_revisao, por=professor, comentario="Faltou.")
    client.force_login(professor)
    html = client.get(reverse("curso", args=[slides_em_revisao.curso.pk])).content.decode()
    lista = html[html.index("Entregáveis") : html.index("<aside")]
    assert "Devolvido" in lista


@pytest.mark.django_db
def test_a_lista_nao_custa_uma_consulta_por_cartao(client, dados_curso, professor):
    """A situacao le a ultima revisao de cada um dos seis. Sem prefetch sao seis
    consultas, e o numero so cresceria quando alguem acrescentasse um entregavel -
    tarde demais para descobrir."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.cursos.models import Revisao as R

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    with CaptureQueriesContext(connection) as consultas:
        client.get(reverse("curso", args=[curso.pk]))
    batidas = [c for c in consultas if R._meta.db_table in c["sql"]]
    assert len(batidas) <= 1, f"{len(batidas)} consultas na tabela de revisões"


@pytest.mark.django_db
def test_aprovado_com_devolucao_no_passado_nao_esta_com_a_equipe(
    slides_em_revisao, professor
):
    """Prende `voltou_para_a_equipe` DIRETO, e nao pelos chamadores.

    Os dois que existem (`na_revisao_de` e `situacao`) filtram RASCUNHO antes de
    perguntar, entao a guarda de estado dentro da propriedade nao tinha como
    falhar: apagar ela deixava a suite verde. A propriedade e publica e precisa
    valer sozinha - um entregavel APROVADO que ja foi devolvido no passado tem
    "Devolvido" na ultima revisao ate ser reenviado e reaprovado.
    """
    services.devolver_entregavel(slides_em_revisao, por=professor, comentario="Faltou.")
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.voltou_para_a_equipe

    # Reenviado e aprovado: o historico ainda guarda a devolucao, mas ele nao
    # esta mais com a equipe.
    slides_em_revisao.status = StatusEntregavel.EM_REVISAO
    slides_em_revisao.save(update_fields=["status", "atualizado_em"])
    assert not slides_em_revisao.voltou_para_a_equipe

    slides_em_revisao.status = StatusEntregavel.APROVADO
    slides_em_revisao.save(update_fields=["status", "atualizado_em"])
    assert not slides_em_revisao.voltou_para_a_equipe
