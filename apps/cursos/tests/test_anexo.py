import hashlib

import pytest
from django.core.exceptions import ValidationError

from apps.cursos.arquivos import calcula_hash, detecta_mime, valida_upload
from apps.cursos.choices import TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo

PDF = b"%PDF-1.7\n%..."
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
ZIP = b"PK\x03\x04" + b"\x00" * 8


def test_detecta_pdf_png_e_zip():
    assert detecta_mime(PDF) == "application/pdf"
    assert detecta_mime(PNG) == "image/png"
    assert detecta_mime(ZIP) == "application/zip"


class _UploadSemRead:
    """Dublê de upload que so tem chunks() e seek(0) - de proposito sem read()
    nenhum. calcula_hash so pode passar aqui se nunca tentar ler o arquivo inteiro
    de uma vez (upload.read()): um AttributeError provaria isso na hora."""

    def __init__(self, pedacos):
        self._pedacos = pedacos
        self.posicao_apos_percorrer = None

    def chunks(self):
        yield from self._pedacos
        self.posicao_apos_percorrer = "fim"

    def seek(self, posicao):
        assert posicao == 0
        self.posicao_apos_percorrer = "inicio"


def test_calcula_hash_le_em_pedacos_e_devolve_o_ponteiro_ao_inicio():
    # O upload de 1 GB do Plano 4 herda este mesmo caminho; o argumento inteiro da
    # spec e que 1 GB nunca pode sentar inteiro num worker Python (item 8 da revisao
    # de branco) - dai o dublê nao ter read() para provocar.
    pedacos = [b"parte um ", b"parte dois ", b"parte tres"]
    upload = _UploadSemRead(pedacos)

    resultado = calcula_hash(upload)

    assert resultado == hashlib.sha256(b"".join(pedacos)).hexdigest()
    assert upload.posicao_apos_percorrer == "inicio"


def test_conteudo_desconhecido_nao_e_detectado():
    assert detecta_mime(b"nao sou arquivo conhecido") is None


def test_conteudo_nao_reconhecido_e_recusado():
    with pytest.raises(ValidationError):
        valida_upload("relatorio.pdf", tamanho=100, cabecalho=b"MZ\x90\x00 executavel")


def test_extensao_mentirosa_e_recusada():
    # Conteudo e um PNG de verdade (assinatura reconhecida), mas o nome mente
    # dizendo que e um PDF: isto tem que cair no ramo de extensao incompativel,
    # nao no de "conteudo desconhecido".
    with pytest.raises(ValidationError):
        valida_upload("x.pdf", tamanho=100, cabecalho=PNG)


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
def test_anexo_de_link_exige_url(entregavel_cards, aluno):
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
def test_anexo_de_link_com_arquivo_e_recusado(entregavel_cards, aluno, arquivo_qualquer):
    # Diferente do teste acima: aqui a url esta preenchida, entao so o ramo
    # "link nao pode carregar arquivo" pode derrubar full_clean().
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.LINK,
        titulo="Atividade no Scratch",
        url="https://scratch.mit.edu/projects/123",
        arquivo=arquivo_qualquer,
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
def test_anexo_de_arquivo_nao_aceita_url(entregavel_cards, aluno, arquivo_qualquer):
    # Diferente do teste acima: aqui o arquivo esta preenchido, entao so o ramo
    # "anexo de arquivo nao pode ter link" pode derrubar full_clean().
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.ARQUIVO,
        titulo="Card 1",
        arquivo=arquivo_qualquer,
        url="https://exemplo.org/card.pdf",
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


@pytest.mark.django_db
def test_anexo_de_arquivo_bem_formado_passa_na_validacao(entregavel_cards, aluno, arquivo_qualquer):
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.ARQUIVO,
        titulo="Card 1",
        arquivo=arquivo_qualquer,
        enviado_por=aluno,
    )
    anexo.full_clean()


@pytest.mark.django_db
def test_anexo_de_video_bem_formado_passa_na_validacao(entregavel_cards, aluno, arquivo_qualquer):
    anexo = Anexo(
        entregavel=entregavel_cards,
        tipo_midia=TipoMidia.VIDEO,
        titulo="Aula 1",
        arquivo=arquivo_qualquer,
        duracao_minutos=10,
        enviado_por=aluno,
    )
    anexo.full_clean()
