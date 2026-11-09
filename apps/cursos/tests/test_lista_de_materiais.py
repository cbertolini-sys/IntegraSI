"""A lista de materiais de um entregavel: o que e cada documento, num relance.

Antes, cada material era o titulo escolhido pela equipe e a descricao inteira,
com paragrafos e tudo. Nao dizia que arquivo era (um .docx? um PDF?) nem quanto
pesava, e tres descricoes longas ocupavam a tela toda. A coordenacao via ainda
menos: so os titulos, como etiquetas, sem link.

As regras que este arquivo prende:

 1. Material de arquivo mostra o nome do arquivo, com a extensao.
 2. ... um selo com o formato (DOCX, PDF), lido da extensao.
 3. ... e o tamanho.
 4. Link mostra o selo LINK e o dominio para onde aponta.
 5. A descricao vira um resumo curto: sem marcacao, com espaco onde havia
    quebra de paragrafo, cortado em PALAVRAS_DO_RESUMO palavras.
 6. O resumo e texto, nao HTML: o que a descricao escapava continua escapado.
 7. O rotulo de gabarito aparece, e "Sem rótulo" nao.
 8. A tela da coordenacao lista os materiais com o mesmo parcial, e nao so os
    titulos.
 9. Nenhuma das tres telas consulta o banco uma vez por material.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import Rotulo, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo, Arquivo


@pytest.fixture
def curso(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    return curso


@pytest.fixture
def caderno(curso):
    return curso.entregaveis.get(tipo=TipoEntregavel.CADERNO)


def arquivo(aluno, nome, tamanho=1_258_291, mime="application/zip"):
    from django.core.files.base import ContentFile

    registro = Arquivo(
        nome_original=nome, tamanho=tamanho, mime=mime,
        hash_conteudo="0" * 64, enviado_por=aluno,
    )
    registro.arquivo.save(nome, ContentFile(b"PK\x03\x04..."), save=False)
    registro.save()
    return registro


def anexa_arquivo(entregavel, aluno, nome="caderno-sem-gabarito.docx", **campos):
    return Anexo.objects.create(
        entregavel=entregavel, tipo_midia=TipoMidia.ARQUIVO,
        titulo=campos.pop("titulo", "Caderno sem gabarito"),
        arquivo=arquivo(aluno, nome), enviado_por=aluno, **campos,
    )


def anexa_link(entregavel, aluno, url="https://www.scratch.mit.edu/projects/123"):
    return Anexo.objects.create(
        entregavel=entregavel, tipo_midia=TipoMidia.LINK, titulo="Labirinto",
        url=url, enviado_por=aluno,
    )


def tela(client, entregavel):
    """So a lista de materiais: o formulario de anexar, na mesma tela, tem as
    opcoes de rotulo no select, e "Sem rótulo" la nao diz nada sobre a lista."""
    html = client.get(reverse("entregavel", args=[entregavel.pk])).content.decode()
    inicio = html.index('<ul class="registros materiais">')
    return html[inicio : html.index("</ul>", inicio)]


# --- Regras 1 a 4: o que e cada material ----------------------------------


@pytest.mark.django_db
def test_mostra_o_nome_do_arquivo(client, caderno, aluno):
    anexa_arquivo(caderno, aluno)
    client.force_login(aluno)
    assert "caderno-sem-gabarito.docx" in tela(client, caderno)


@pytest.mark.django_db
def test_mostra_o_formato_lido_da_extensao(client, caderno, aluno):
    anexa_arquivo(caderno, aluno, nome="Aula 3.Pptx")
    client.force_login(aluno)
    assert '<span class="material-formato formato-pptx">PPTX</span>' in tela(client, caderno)


@pytest.mark.django_db
def test_mostra_o_tamanho(client, caderno, aluno):
    anexa_arquivo(caderno, aluno)
    client.force_login(aluno)
    # filesizeformat junta numero e unidade com espaco que nao quebra.
    assert "1,2\xa0MB" in tela(client, caderno)


@pytest.mark.django_db
def test_link_mostra_o_selo_e_o_dominio(client, caderno, aluno):
    anexa_link(caderno, aluno)
    client.force_login(aluno)
    html = tela(client, caderno)
    assert '<span class="material-formato formato-link">LINK</span>' in html
    assert "scratch.mit.edu" in html
    # O dominio, e nao o endereco inteiro na linha de detalhe.
    assert ">www.scratch.mit.edu<" not in html


# --- Regras 5 e 6: o resumo ------------------------------------------------


@pytest.mark.django_db
def test_o_resumo_corta_a_descricao_longa(client, caderno, aluno):
    from apps.cursos.models.anexo import PALAVRAS_DO_RESUMO

    palavras = [f"palavra{i}" for i in range(PALAVRAS_DO_RESUMO + 10)]
    anexa_arquivo(caderno, aluno, descricao=f"<p>{' '.join(palavras)}</p>")
    client.force_login(aluno)
    html = tela(client, caderno)
    assert palavras[PALAVRAS_DO_RESUMO - 1] in html
    assert palavras[PALAVRAS_DO_RESUMO] not in html


@pytest.mark.django_db
def test_o_resumo_nao_cola_os_paragrafos(caderno, aluno):
    anexo = anexa_arquivo(caderno, aluno, descricao="<p>Primeiro.</p><p><strong>Segundo</strong>.</p>")
    assert anexo.resumo == "Primeiro. Segundo."


@pytest.mark.django_db
def test_o_resumo_e_texto_e_nao_html(client, caderno, aluno):
    """A descricao guarda `&lt;b&gt;` para o que a pessoa digitou como texto. O
    resumo desfaz a entidade para contar palavras, e a tela precisa escapar de
    novo: sem isso, o que era texto viraria marcacao."""
    anexa_arquivo(caderno, aluno, descricao="<p>Use a tag &lt;b&gt; no exemplo.</p>")
    client.force_login(aluno)
    html = tela(client, caderno)
    assert "Use a tag &lt;b&gt; no exemplo." in html
    assert "Use a tag <b>" not in html


# --- Regra 7: o rotulo de gabarito ----------------------------------------


@pytest.mark.django_db
def test_mostra_o_rotulo_de_gabarito(client, caderno, aluno):
    anexa_arquivo(caderno, aluno, rotulo=Rotulo.COM_GABARITO)
    client.force_login(aluno)
    assert "Versão com gabarito" in tela(client, caderno)


@pytest.mark.django_db
def test_sem_rotulo_nao_aparece(client, caderno, aluno):
    anexa_arquivo(caderno, aluno)
    client.force_login(aluno)
    assert "Sem rótulo" not in tela(client, caderno)


# --- Regra 8: a coordenacao ve a mesma lista -------------------------------


@pytest.mark.django_db
def test_a_coordenacao_ve_os_arquivos(client, curso, caderno, aluno, coordenador):
    anexo = anexa_arquivo(caderno, aluno)
    client.force_login(coordenador)
    html = client.get(reverse("analisar_curso", args=[curso.pk])).content.decode()
    assert "caderno-sem-gabarito.docx" in html
    assert reverse("baixar", args=[anexo.arquivo.identificador]) in html


# --- Regra 9: consultas ----------------------------------------------------


def consultas_a_arquivos(client, url):
    with CaptureQueriesContext(connection) as consultas:
        client.get(url)
    return [c for c in consultas if f'FROM "{Arquivo._meta.db_table}"' in c["sql"]]


@pytest.mark.django_db
@pytest.mark.parametrize("tela_", ["entregavel", "revisar", "analisar_curso"])
def test_nenhuma_tela_consulta_por_material(
    client, curso, caderno, aluno, professor, coordenador, tela_
):
    for i in range(3):
        anexa_arquivo(caderno, aluno, nome=f"material-{i}.docx", titulo=f"Material {i}")
    quem, alvo = {
        "entregavel": (aluno, caderno.pk),
        "revisar": (professor, caderno.pk),
        "analisar_curso": (coordenador, curso.pk),
    }[tela_]
    client.force_login(quem)
    batidas = consultas_a_arquivos(client, reverse(tela_, args=[alvo]))
    assert len(batidas) <= 1, f"{len(batidas)} consultas na tabela de arquivos"
