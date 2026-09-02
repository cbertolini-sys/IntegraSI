"""As duas telas do mesmo entregavel: produzir e decidir.

Sao paginas diferentes de proposito, e divergiam em coisas que nao deviam: o
cabecalho de uma ficou no padrao antigo, a fila levava ao lugar errado, e o
motivo da ultima decisao aparecia num formato em cada uma.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel


@pytest.fixture
def reaberto(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    slides.status = StatusEntregavel.EM_REVISAO
    slides.save(update_fields=["status", "atualizado_em"])
    services.aprovar_entregavel(slides, por=professor, comentario="<p>Ficou bom.</p>")
    services.reabrir_entregavel(slides, por=professor, comentario="<p>Faltou a aula 3.</p>")
    return slides


def cabecalho(html):
    return html[html.index("cabecalho-pagina") : html.index("corpo-trabalho")]


# --- U1: o mesmo cabecalho nas duas ------------------------------------------


@pytest.mark.django_db
def test_a_tela_de_decisao_usa_a_migalha(client, reaberto, professor):
    """A tela de producao ganhou a migalha `curso › Etapa N` numa rodada anterior
    e a de decisao ficou com o padrao velho: selo solto acima do titulo e o nome
    do curso num paragrafo cru. Era a mesma correcao, esquecida numa das duas."""
    client.force_login(professor)
    topo = cabecalho(client.get(reverse("revisar", args=[reaberto.pk])).content.decode())
    assert 'class="migalha"' in topo
    assert reverse("curso", args=[reaberto.curso.pk]) in topo
    assert "selo-etapa" in topo
    assert 'class="sub"' not in topo


@pytest.mark.django_db
def test_as_duas_telas_tem_o_mesmo_cabecalho(client, reaberto, professor):
    """Mesma migalha, mesmo selo de situacao, mesmo titulo."""
    client.force_login(professor)
    producao = cabecalho(client.get(reverse("entregavel", args=[reaberto.pk])).content.decode())
    decisao = cabecalho(client.get(reverse("revisar", args=[reaberto.pk])).content.decode())
    for marca in ('class="migalha"', "selo-etapa", 'class="estado atencao"', reaberto.nome):
        assert marca in producao, f"produção: {marca}"
        assert marca in decisao, f"decisão: {marca}"


# --- U2: a fila leva ao lugar certo ------------------------------------------


@pytest.mark.django_db
def test_o_grupo_com_a_equipe_leva_a_producao(client, reaberto, professor):
    """A fila listava o item e a tela de decisao respondia "não está aguardando
    decisão". Quem esta com a equipe se ve na tela de producao."""
    client.force_login(professor)
    html = client.get(reverse("fila_revisao")).content.decode()
    grupo = html[html.index("Com a equipe") :]
    assert reverse("entregavel", args=[reaberto.pk]) in grupo
    assert reverse("revisar", args=[reaberto.pk]) not in grupo


@pytest.mark.django_db
def test_o_grupo_que_espera_decisao_continua_levando_a_decisao(
    client, dados_curso, professor, aluno
):
    """O outro lado: quem espera decisao continua abrindo a tela de decidir."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    cards = curso.entregaveis.get(tipo=TipoEntregavel.CARDS)
    cards.status = StatusEntregavel.EM_REVISAO
    cards.save(update_fields=["status", "atualizado_em"])

    client.force_login(professor)
    html = client.get(reverse("fila_revisao")).content.decode()
    grupo = html[html.index("Esperando por você") : html.index("Com a equipe") if "Com a equipe" in html else len(html)]
    assert reverse("revisar", args=[cards.pk]) in grupo


# --- U4: caminho cruzado ------------------------------------------------------


@pytest.mark.django_db
def test_a_decisao_leva_ao_material(client, reaberto, professor):
    """A producao ja levava a decisao; faltava a volta."""
    client.force_login(professor)
    topo = cabecalho(client.get(reverse("revisar", args=[reaberto.pk])).content.decode())
    assert reverse("entregavel", args=[reaberto.pk]) in topo
    assert "Ver o material" in topo


# --- U3: o historico nas duas -------------------------------------------------


@pytest.mark.django_db
def test_a_producao_mostra_o_historico_das_decisoes(client, reaberto, aluno):
    """A equipe via so o ultimo recado, na tarja. A sequencia das idas e vindas
    fica na mesma marcacao que a tela de decisao usa."""
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[reaberto.pk])).content.decode()
    assert "Decisões anteriores" in html
    assert "Ficou bom." in html, "a aprovação anterior faz parte da sequência"


@pytest.mark.django_db
def test_a_tarja_do_ultimo_recado_fica_so_na_producao(client, reaberto, professor, aluno):
    """A tarja e para a equipe: e o que ela precisa ler antes de voltar a
    trabalhar. Na tela de decisao o mesmo texto ja esta no historico, e repetir
    seria dizer duas vezes a mesma coisa na mesma pagina."""
    client.force_login(aluno)
    producao = client.get(reverse("entregavel", args=[reaberto.pk])).content.decode()
    assert "Reaberto pelo professor" in producao

    client.force_login(professor)
    decisao = client.get(reverse("revisar", args=[reaberto.pk])).content.decode()
    assert "Reaberto pelo professor" not in decisao


def test_o_historico_e_um_arquivo_so():
    from pathlib import Path

    parcial = Path("templates/cursos/_historico.html")
    assert parcial.exists()
    for usuario in ("cursos/revisar.html", "cursos/entregavel.html"):
        assert "cursos/_historico.html" in Path("templates", usuario).read_text(encoding="utf-8")
