"""O rastro administrativo do curso, na tela.

`LogTransicaoCurso` existe desde o Plano 3 e a spec 11 diz para que serve:
responder "por que este curso saiu do ar?" seis meses depois. Ele nao aparecia em
tela nenhuma - os dois textos que a coordenacao escreve (o comentario da
devolucao e o motivo da despublicacao) eram gravados e nunca lidos por ninguem.

Era o quarto "campo que so entra" desta base, depois de `Anexo.descricao`,
`Revisao.comentario` e as decisoes do professor.
"""

import pytest
from django.urls import reverse

from apps.catalogo.tests.test_catalogo import publica
from apps.cursos import services
from apps.cursos.models import LogTransicaoCurso


@pytest.fixture
def despublicado(dados_curso, aluno, professor, coordenador):
    curso = services.criar_curso(**dados_curso)
    publica(curso, aluno, professor, coordenador)
    services.despublicar_curso(
        curso, por=coordenador, motivo="<p>Material <strong>desatualizado</strong>.</p>"
    )
    return curso


@pytest.mark.django_db
def test_a_tela_do_curso_mostra_o_rastro(client, despublicado, professor):
    """A equipe precisa saber por que o curso saiu do ar - e ela que vai
    corrigir."""
    client.force_login(professor)
    html = client.get(reverse("curso", args=[despublicado.pk])).content.decode()
    assert "Histórico do curso" in html
    assert "<strong>desatualizado</strong>" in html, "o motivo chega formatado"
    assert "Despublicado" in html


@pytest.mark.django_db
def test_a_tela_da_coordenacao_tambem(client, despublicado, coordenador):
    """Quem decide precisa ver as decisoes anteriores, como na tela do professor."""
    client.force_login(coordenador)
    html = client.get(reverse("analisar_curso", args=[despublicado.pk])).content.decode()
    assert "Histórico do curso" in html
    assert "desatualizado" in html


@pytest.mark.django_db
def test_do_mais_novo_para_o_mais_antigo(client, despublicado, coordenador):
    """A ultima decisao e a que explica o estado de agora."""
    services.publicar_curso(despublicado, por=coordenador)
    client.force_login(coordenador)
    html = client.get(reverse("curso", args=[despublicado.pk])).content.decode()
    historico = html[html.index("Histórico do curso") :]
    assert historico.index("Publicado") < historico.index("Despublicado")


@pytest.mark.django_db
def test_mostra_quem_decidiu_e_quando(client, despublicado, coordenador, professor):
    client.force_login(professor)
    html = client.get(reverse("curso", args=[despublicado.pk])).content.decode()
    historico = html[html.index("Histórico do curso") :]
    assert coordenador.nome_completo in historico
    assert "<time" in historico


@pytest.mark.django_db
def test_curso_sem_transicao_nao_mostra_cartao_vazio(client, dados_curso, professor):
    """Curso em rascunho nunca mudou de situacao: um cartao vazio ali seria um
    espaco pedindo explicacao."""
    curso = services.criar_curso(**dados_curso)
    assert not LogTransicaoCurso.objects.filter(curso=curso).exists()
    client.force_login(professor)
    html = client.get(reverse("curso", args=[curso.pk])).content.decode()
    assert "Histórico do curso" not in html


@pytest.mark.django_db
def test_o_rastro_nao_custa_uma_consulta_por_linha(client, despublicado, coordenador):
    """Cada linha le o nome de quem decidiu."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    for _ in range(3):
        services.publicar_curso(despublicado, por=coordenador)
        services.despublicar_curso(despublicado, por=coordenador, motivo="De novo.")

    client.force_login(coordenador)
    with CaptureQueriesContext(connection) as consultas:
        client.get(reverse("curso", args=[despublicado.pk]))
    batidas = [c for c in consultas if LogTransicaoCurso._meta.db_table in c["sql"]]
    assert len(batidas) <= 1, f"{len(batidas)} consultas na tabela de transições"


def test_o_rastro_e_um_arquivo_so():
    from pathlib import Path

    parcial = Path("templates/cursos/_historico_do_curso.html")
    assert parcial.exists()
    for usuario in ("cursos/curso.html", "cursos/analisar_curso.html"):
        assert "cursos/_historico_do_curso.html" in Path("templates", usuario).read_text(encoding="utf-8")
