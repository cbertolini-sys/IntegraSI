"""Registro de upload em blocos (Plano 4, Task 1).

As regras que este arquivo prende, na ordem em que aparecem:

 1. `detecta_mime` reconhece MP4 pela caixa `ftyp` nos bytes 4:8 (nao ha
    assinatura fixa no inicio do arquivo).
 2. `detecta_mime` continua devolvendo None para conteudo desconhecido.
 3. `LIMITE_VIDEO` vale exatamente 1 GiB (spec 8).
 4. `.mp4` esta na tabela de extensoes e `video/mp4` na de limites, com o teto
    de 1 GiB — sem as duas entradas `valida_upload` recusa um MP4 legitimo.
 5. `valida_upload` recusa acima do limite do tipo.
 6. `valida_upload` continua recusando conteudo que nao bate com a extensao.
 7. `caminho()` sai do `identificador`, nunca do `nome_original`, e fica dentro
    de MEDIA_ROOT.
 8. `clean()` recusa `tamanho_total` acima de LIMITE_VIDEO, e a criacao valida.
 9. `save()` nao revalida o objeto inteiro quando vem `update_fields`
    (CLAUDE.md; aqui custa uma consulta por bloco de 5 MB).
10. `acrescentar()` recusa bloco que ultrapasse o tamanho declarado.
11. `acrescentar()` soma o recebido e remonta o arquivo na ordem.
12. `acrescentar()` e idempotente por bloco: reenviar um bloco cujo registro nao
    avancou reescreve no mesmo offset em vez de duplicar.
13. Sobra de bloco interrompido nao sobrevive ao reenvio: o arquivo parcial tem
    sempre exatamente `tamanho_recebido` bytes.
14. `completo` e verdadeiro quando o recebido alcanca o total.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError

from apps.cursos.arquivos import LIMITE_VIDEO, detecta_mime, valida_upload
from apps.cursos.choices import TipoEntregavel
from apps.cursos.models import UploadEmAndamento

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


# --- Regras 1 a 6: deteccao e limite do MP4 -------------------------------


def test_detecta_mp4_pela_caixa_ftyp():
    assert detecta_mime(MP4) == "video/mp4"


def test_conteudo_desconhecido_continua_sem_mime():
    assert detecta_mime(b"nao sou arquivo nenhum") is None


def test_video_ate_um_giga_e_aceito():
    assert LIMITE_VIDEO == 1024 * 1024 * 1024
    assert valida_upload("aula.mp4", tamanho=LIMITE_VIDEO, cabecalho=MP4) == "video/mp4"


def test_video_acima_de_um_giga_e_recusado():
    with pytest.raises(ValidationError):
        valida_upload("aula.mp4", tamanho=LIMITE_VIDEO + 1, cabecalho=MP4)


def test_mp4_com_extensao_de_pdf_e_recusado():
    with pytest.raises(ValidationError):
        valida_upload("aula.pdf", tamanho=len(MP4), cabecalho=MP4)


# --- O modelo -------------------------------------------------------------


@pytest.fixture
def entregavel_videos(dados_curso, aluno):
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso.entregaveis.get(tipo=TipoEntregavel.VIDEOS)


@pytest.fixture
def novo_upload(entregavel_videos, aluno):
    def cria(tamanho_total, nome_original="aula.mp4"):
        return UploadEmAndamento.objects.create(
            usuario=aluno,
            entregavel=entregavel_videos,
            nome_original=nome_original,
            tamanho_total=tamanho_total,
        )

    return cria


# Regra 7
@pytest.mark.django_db
def test_caminho_sai_do_identificador_e_ignora_o_nome_original(novo_upload):
    """`nome_original` e texto livre do cliente. Se `caminho()` um dia passasse a
    usa-lo, um nome com `../` escaparia de MEDIA_ROOT."""
    upload = novo_upload(4, nome_original="../../../etc/passwd")
    caminho = upload.caminho()

    assert caminho.name == f"{upload.identificador.hex}.parcial"
    assert "passwd" not in str(caminho)
    assert Path(settings.MEDIA_ROOT).resolve() in caminho.resolve().parents


# Regra 8
@pytest.mark.django_db
def test_upload_declarado_acima_do_limite_e_recusado_na_criacao(novo_upload):
    with pytest.raises(ValidationError):
        novo_upload(LIMITE_VIDEO + 1)


# Regra 9
@pytest.mark.django_db
def test_acrescentar_nao_revalida_o_objeto_inteiro(novo_upload, monkeypatch):
    """Sem o guarda de `update_fields`, cada bloco de 5 MB dispara um
    `full_clean()` completo — `validate_unique()` em `identificador` inclusive,
    uma ida ao banco por bloco, ~200 por GB."""
    upload = novo_upload(8)
    chamadas = []
    monkeypatch.setattr(
        UploadEmAndamento, "full_clean", lambda self, *a, **k: chamadas.append(1)
    )

    upload.acrescentar(b"1234")

    assert chamadas == []
    assert upload.tamanho_recebido == 4


# Regra 10
@pytest.mark.django_db
def test_bloco_que_ultrapassa_o_tamanho_declarado_e_recusado(novo_upload):
    upload = novo_upload(4)

    with pytest.raises(ValidationError):
        upload.acrescentar(b"123456")

    assert upload.tamanho_recebido == 0
    assert not upload.caminho().exists()


# Regras 11 e 14
@pytest.mark.django_db
def test_acrescentar_blocos_soma_o_recebido(novo_upload):
    upload = novo_upload(8)

    upload.acrescentar(b"1234")
    assert upload.tamanho_recebido == 4
    assert upload.completo is False

    upload.acrescentar(b"5678")
    assert upload.tamanho_recebido == 8
    assert upload.completo is True
    assert upload.caminho().read_bytes() == b"12345678"


# Regra 12
@pytest.mark.django_db
def test_bloco_reenviado_apos_falha_no_registro_nao_duplica_bytes(novo_upload, monkeypatch):
    """O motivo de existir desta tarefa: o upload sobrevive a queda de conexao.
    Se os bytes chegam mas o registro nao avanca, o cliente reenvia o bloco — e
    um append cego escreveria os mesmos bytes duas vezes, corrompendo o arquivo
    enquanto `tamanho_recebido` continua parecendo certo."""
    upload = novo_upload(8)
    upload.acrescentar(b"1234")

    def save_que_falha(self, *args, **kwargs):
        raise RuntimeError("conexão caiu depois de gravar os bytes")

    monkeypatch.setattr(UploadEmAndamento, "save", save_que_falha)
    with pytest.raises(RuntimeError):
        upload.acrescentar(b"5678")
    monkeypatch.undo()

    assert upload.tamanho_recebido == 4
    assert UploadEmAndamento.objects.get(pk=upload.pk).tamanho_recebido == 4

    upload.acrescentar(b"5678")

    assert upload.tamanho_recebido == 8
    assert upload.caminho().read_bytes() == b"12345678"


# Regra 13
@pytest.mark.django_db
def test_sobra_de_bloco_interrompido_nao_sobrevive_ao_reenvio(novo_upload):
    """Um bloco cuja escrita morreu no meio deixa bytes alem do offset
    registrado. O reenvio escreve a partir do offset e corta o resto."""
    upload = novo_upload(8)
    upload.acrescentar(b"1234")
    with open(upload.caminho(), "r+b") as parcial:
        parcial.seek(4)
        parcial.write(b"56XXXXXXXX")

    upload.acrescentar(b"5678")

    assert upload.caminho().read_bytes() == b"12345678"
    assert upload.caminho().stat().st_size == upload.tamanho_recebido
