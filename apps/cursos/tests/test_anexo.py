import pytest
from django.core.exceptions import ValidationError

from apps.cursos.arquivos import detecta_mime, valida_upload
from apps.cursos.choices import TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo

PDF = b"%PDF-1.7\n%..."
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
ZIP = b"PK\x03\x04" + b"\x00" * 8


def test_detecta_pdf_png_e_zip():
    assert detecta_mime(PDF) == "application/pdf"
    assert detecta_mime(PNG) == "image/png"
    assert detecta_mime(ZIP) == "application/zip"


def test_conteudo_desconhecido_nao_e_detectado():
    assert detecta_mime(b"nao sou arquivo conhecido") is None


def test_extensao_mentirosa_e_recusada():
    with pytest.raises(ValidationError):
        valida_upload("relatorio.pdf", tamanho=100, cabecalho=b"MZ\x90\x00 executavel")


def test_pdf_acima_do_limite_e_recusado():
    with pytest.raises(ValidationError):
        valida_upload("plano.pdf", tamanho=21 * 1024 * 1024, cabecalho=PDF)


def test_pdf_dentro_do_limite_devolve_o_mime():
    assert valida_upload("plano.pdf", tamanho=19 * 1024 * 1024, cabecalho=PDF) == "application/pdf"


def test_imagem_acima_do_limite_e_recusada():
    with pytest.raises(ValidationError):
        valida_upload("card.png", tamanho=11 * 1024 * 1024, cabecalho=PNG)


@pytest.fixture
def entregavel_cards(dados_curso):
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    return curso.entregaveis.get(tipo=TipoEntregavel.CARDS)


@pytest.mark.django_db
def test_anexo_de_link_nao_aceita_arquivo(entregavel_cards, aluno):
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.LINK,
        titulo="Atividade no Scratch",
        url="",
        enviado_por=aluno,
    )
    with pytest.raises(ValidationError):
        anexo.full_clean()


@pytest.mark.django_db
def test_anexo_de_arquivo_exige_arquivo(entregavel_cards, aluno):
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.ARQUIVO,
        titulo="Card 1",
        enviado_por=aluno,
    )
    with pytest.raises(ValidationError):
        anexo.full_clean()


@pytest.mark.django_db
def test_video_exige_duracao(entregavel_cards, aluno, arquivo_qualquer):
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.VIDEO,
        titulo="Aula 1",
        arquivo=arquivo_qualquer,
        enviado_por=aluno,
    )
    with pytest.raises(ValidationError):
        anexo.full_clean()
