"""Um selo so, uma lista de curso so, uma lista de material so (A4, A5 e A6).

A cadeia de `{% if curso.status == ... %}` estava em QUATRO templates, e eles ja
tinham divergido: `cursos_no_catalogo` pintava so PUBLICADO, os outros tres
pintavam tres estados. Um curso despublicado aparecia sem cor numa tela e com cor
nas outras - a duplicacao ja tinha cobrado o preco dela.

A lista de materiais tambem estava escrita duas vezes, e as duas nao eram iguais:
a da revisao nao mostrava a DESCRICAO do anexo, entao quem revisa nao lia o que a
equipe escreveu sobre o proprio material.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo


@pytest.fixture
def curso(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    return curso


# --- A6: o selo do curso ------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status,tom",
    [
        (StatusCurso.PUBLICADO, "ok"),
        (StatusCurso.AGUARDANDO_COORDENADOR, "espera"),
        (StatusCurso.DEVOLVIDO, "atencao"),
        (StatusCurso.DESPUBLICADO, "atencao"),
        (StatusCurso.EM_PRODUCAO, ""),
    ],
)
def test_o_curso_sabe_dizer_a_propria_situacao(curso, status, tom):
    curso.status = status
    assert curso.situacao.rotulo == curso.get_status_display()
    assert curso.situacao.tom == tom


def test_nenhum_template_repete_a_cadeia_de_status():
    """A regra do selo mora no modelo, e nao em quatro `{% if %}` que divergem."""
    import subprocess
    from pathlib import Path

    arquivos = subprocess.run(
        ["git", "ls-files", "templates"], capture_output=True, text=True
    ).stdout.split()
    achados = []
    for caminho in (a for a in arquivos if a.endswith(".html")):
        texto = Path(caminho).read_text(encoding="utf-8")
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if "curso.status ==" in linha or "entregavel.status ==" in linha:
                achados.append(f"{caminho}:{numero}")
    assert achados == [], "cadeia de status em template:\n" + "\n".join(achados)


@pytest.mark.django_db
def test_o_despublicado_tem_o_mesmo_tom_nas_duas_telas(
    client, dados_curso, aluno, professor, coordenador
):
    """O defeito que a duplicacao ja tinha causado."""
    from apps.catalogo.tests.test_catalogo import publica

    curso = services.criar_curso(**dados_curso)
    publica(curso, aluno, professor, coordenador)
    services.despublicar_curso(curso, por=coordenador, motivo="Material desatualizado.")

    client.force_login(coordenador)
    inventario = client.get(reverse("cursos_no_catalogo")).content.decode()
    analise = client.get(reverse("analisar_curso", args=[curso.pk])).content.decode()
    assert 'class="estado atencao"' in inventario
    assert 'class="estado atencao"' in analise


# --- A5: a lista de materiais -------------------------------------------------


@pytest.mark.django_db
def test_quem_revisa_ve_a_descricao_do_material(client, curso, professor, aluno):
    """A lista da revisao nao mostrava a descricao: o professor decidia sobre o
    material sem ler o que a equipe escreveu sobre ele."""
    cards = curso.entregaveis.get(tipo=TipoEntregavel.CARDS)
    cards.status = StatusEntregavel.EM_REVISAO
    cards.save(update_fields=["status", "atualizado_em"])
    Anexo.objects.create(
        entregavel=cards, tipo_midia=TipoMidia.LINK, titulo="Card 1",
        descricao="<p>Explica <strong>senhas fortes</strong>.</p>",
        url="https://exemplo.org/c", enviado_por=aluno,
    )
    client.force_login(professor)
    html = client.get(reverse("revisar", args=[cards.pk])).content.decode()
    assert "<strong>senhas fortes</strong>" in html


@pytest.mark.django_db
def test_as_duas_telas_desenham_o_material_igual(client, curso, professor, aluno):
    """Mesmo anexo, mesma marcacao nas duas telas."""
    cards = curso.entregaveis.get(tipo=TipoEntregavel.CARDS)
    Anexo.objects.create(
        entregavel=cards, tipo_midia=TipoMidia.LINK, titulo="Card 1",
        descricao="<p>Um card.</p>", referencia_bibliografica="BNCC, 2018.",
        url="https://exemplo.org/c", enviado_por=aluno,
    )
    client.force_login(professor)
    producao = client.get(reverse("entregavel", args=[cards.pk])).content.decode()
    revisao = client.get(reverse("revisar", args=[cards.pk])).content.decode()
    for marca in ("Card 1", "BNCC, 2018.", "Um card."):
        assert marca in producao, marca
        assert marca in revisao, marca


# --- A4 e A5: um arquivo por lista --------------------------------------------


def test_as_listas_repetidas_viraram_include():
    """Prende a existencia dos arquivos e o uso deles: sem isto, alguem pode
    recriar a marcacao ao lado do include e a duplicacao volta calada."""
    from pathlib import Path

    for parcial, usuarios in (
        ("cursos/_curso_na_lista.html", ("cursos/fila_coordenacao.html", "cursos/cursos_no_catalogo.html")),
        ("cursos/_anexo_na_lista.html", ("cursos/entregavel.html", "cursos/revisar.html")),
        ("cursos/_selo.html", ("cursos/curso.html", "cursos/meus_cursos.html")),
    ):
        assert Path("templates", parcial).exists(), parcial
        for usuario in usuarios:
            texto = Path("templates", usuario).read_text(encoding="utf-8")
            assert parcial in texto, f"{usuario} não usa {parcial}"
