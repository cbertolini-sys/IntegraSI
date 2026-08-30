import datetime
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cursos import services
from apps.cursos.choices import TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo, Arquivo, UploadEmAndamento


@pytest.fixture
def entregavel_videos(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso.entregaveis.get(tipo=TipoEntregavel.VIDEOS)


def novo_upload(entregavel, aluno, nome="aula.mp4"):
    upload = UploadEmAndamento.objects.create(
        usuario=aluno, entregavel=entregavel, nome_original=nome, tamanho_total=10
    )
    upload.acrescentar(b"123")
    return upload


def envelhecer_upload(upload, horas):
    UploadEmAndamento.objects.filter(pk=upload.pk).update(
        atualizado_em=timezone.now() - datetime.timedelta(hours=horas)
    )


def novo_arquivo(aluno, nome="material.pdf"):
    from django.core.files.base import ContentFile

    registro = Arquivo(
        nome_original=nome, tamanho=12, mime="application/pdf",
        hash_conteudo="0" * 64, enviado_por=aluno,
    )
    registro.arquivo.save(nome, ContentFile(b"%PDF-1.7\n..."), save=False)
    registro.save()
    return registro


def envelhecer_arquivo(arquivo, horas):
    Arquivo.objects.filter(pk=arquivo.pk).update(
        enviado_em=timezone.now() - datetime.timedelta(hours=horas)
    )


# --- limpar_uploads -------------------------------------------------------


# Regras 1 e 2
@pytest.mark.django_db
def test_upload_antigo_e_removido_com_o_arquivo_parcial(
    entregavel_videos, aluno, django_capture_on_commit_callbacks
):
    """Dois de propósito: o agendamento do apagamento acontece dentro de um laço, e
    um fechamento de escopo tardio (o `lambda` clássico) apagaria duas vezes o
    parcial do último e deixaria o do primeiro no disco para sempre."""
    primeiro = novo_upload(entregavel_videos, aluno, nome="aula-1.mp4")
    segundo = novo_upload(entregavel_videos, aluno, nome="aula-2.mp4")
    caminhos = [primeiro.caminho(), segundo.caminho()]
    assert all(c.exists() for c in caminhos)
    envelhecer_upload(primeiro, 25)
    envelhecer_upload(segundo, 25)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_uploads")

    assert UploadEmAndamento.objects.count() == 0
    assert [c for c in caminhos if c.exists()] == []


# Regra 3
@pytest.mark.django_db
def test_upload_recente_e_preservado(entregavel_videos, aluno, django_capture_on_commit_callbacks):
    upload = novo_upload(entregavel_videos, aluno)
    caminho = upload.caminho()

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_uploads")

    assert UploadEmAndamento.objects.count() == 1
    assert caminho.exists()


# Regra 4
@pytest.mark.django_db
def test_limpar_uploads_honra_horas(entregavel_videos, aluno, django_capture_on_commit_callbacks):
    """Duas horas de idade: sobreviveria ao corte padrão de 24 h, some com --horas 1.
    O sentido é este de propósito -- se o filtro de idade sumisse inteiro, o upload
    seria removido de qualquer jeito e o teste passaria sem provar nada sobre --horas."""
    upload = novo_upload(entregavel_videos, aluno)
    envelhecer_upload(upload, 2)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_uploads", "--horas", "1")

    assert UploadEmAndamento.objects.count() == 0


# Regra 5
@pytest.mark.django_db
def test_limpeza_de_upload_desfeita_nao_apaga_o_parcial(entregavel_videos, aluno):
    """Os bytes só podem sumir depois que o banco confirmou. Apagar o parcial dentro
    da transação é a inversão que a Task 2 já pagou uma vez: o rollback devolve a
    linha ao banco apontando para um arquivo que não existe mais, e o dono não
    consegue nem retomar nem concluir o upload."""
    upload = novo_upload(entregavel_videos, aluno)
    caminho = upload.caminho()
    envelhecer_upload(upload, 25)
    pk = upload.pk

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            call_command("limpar_uploads")
            raise RuntimeError("algo falhou depois da limpeza")

    assert UploadEmAndamento.objects.filter(pk=pk).exists()
    assert caminho.exists()


# Regra 6
@pytest.mark.django_db
def test_limpar_uploads_e_reexecutavel_com_o_parcial_ja_ausente(
    entregavel_videos, aluno, django_capture_on_commit_callbacks
):
    """Linha viva com o parcial já fora do disco -- meia execução anterior, faxina
    manual, restauração de backup. A rotina é de cron: se ela estourar aqui, os
    uploads abandonados seguintes nunca são limpos."""
    upload = novo_upload(entregavel_videos, aluno)
    envelhecer_upload(upload, 25)
    upload.caminho().unlink()

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_uploads")

    assert UploadEmAndamento.objects.count() == 0


# --- limpar_arquivos_orfaos ----------------------------------------------


# Regras 7 e 8
@pytest.mark.django_db
def test_arquivo_orfao_e_antigo_e_removido(aluno, django_capture_on_commit_callbacks):
    """Dois de propósito, pelo mesmo motivo do teste dos parciais: um fechamento de
    escopo tardio dentro do laço apagaria os bytes do último duas vezes."""
    primeiro = novo_arquivo(aluno, nome="um.pdf")
    segundo = novo_arquivo(aluno, nome="dois.pdf")
    caminhos = [Path(primeiro.arquivo.path), Path(segundo.arquivo.path)]
    assert all(c.exists() for c in caminhos)
    envelhecer_arquivo(primeiro, 25)
    envelhecer_arquivo(segundo, 25)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_arquivos_orfaos")

    assert Arquivo.objects.count() == 0
    assert [c for c in caminhos if c.exists()] == []


# Regra 9
@pytest.mark.django_db
def test_arquivo_orfao_recente_e_preservado(arquivo_qualquer, django_capture_on_commit_callbacks):
    """Entre o fim do upload e o salvamento do Anexo existe uma janela em que o
    arquivo não tem referência nenhuma e não é lixo (spec 13). Sem o corte por
    idade, a rotina de cron apagaria o vídeo de 1 GB que um aluno acabou de subir,
    no intervalo de milissegundos entre `arquivo.save()` e `Anexo.objects.create()`."""
    caminho = Path(arquivo_qualquer.arquivo.path)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_arquivos_orfaos")

    assert Arquivo.objects.count() == 1
    assert caminho.exists()


# Regra 10
@pytest.mark.django_db
def test_arquivo_referenciado_por_qualquer_versao_e_preservado(
    arquivo_qualquer, entregavel_videos, aluno, django_capture_on_commit_callbacks
):
    Anexo.objects.create(
        entregavel=entregavel_videos, tipo_midia=TipoMidia.VIDEO, titulo="Aula",
        arquivo=arquivo_qualquer, duracao_minutos=7, enviado_por=aluno,
    )
    caminho = Path(arquivo_qualquer.arquivo.path)
    envelhecer_arquivo(arquivo_qualquer, 24 * 400)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_arquivos_orfaos")

    assert Arquivo.objects.count() == 1
    assert caminho.exists()


# Regra 11
@pytest.mark.django_db
def test_orfao_sai_e_referenciado_fica_na_mesma_passada(
    entregavel_videos, aluno, django_capture_on_commit_callbacks
):
    """As duas metades da consulta ao mesmo tempo. `NOT IN` com um NULL na lista não
    devolve linha nenhuma em SQL, e `Anexo.arquivo` é anulável: uma consulta escrita
    assim casa com o vazio e passa em qualquer teste que só afirme "o referenciado
    ficou". Aqui, casar com nada derruba a primeira asserção e casar com tudo derruba
    a segunda."""
    orfao = novo_arquivo(aluno, nome="orfao.pdf")
    referenciado = novo_arquivo(aluno, nome="em-uso.pdf")
    Anexo.objects.create(
        entregavel=entregavel_videos, tipo_midia=TipoMidia.VIDEO, titulo="Aula",
        arquivo=referenciado, duracao_minutos=7, enviado_por=aluno,
    )
    # Anexo sem arquivo (um link) e o NULL que envenena o `NOT IN` ingênuo.
    Anexo.objects.create(
        entregavel=entregavel_videos, tipo_midia=TipoMidia.LINK, titulo="Leitura",
        url="https://ufsm.br/", enviado_por=aluno,
    )
    envelhecer_arquivo(orfao, 25)
    envelhecer_arquivo(referenciado, 25)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_arquivos_orfaos")

    assert not Arquivo.objects.filter(pk=orfao.pk).exists()
    assert Arquivo.objects.filter(pk=referenciado.pk).exists()


# Regra 12
@pytest.mark.django_db
def test_limpar_arquivos_orfaos_honra_horas(aluno, django_capture_on_commit_callbacks):
    """Mesmo sentido do teste de --horas dos uploads: duas horas de idade sobrevivem
    ao padrão de 24 h e só somem com --horas 1."""
    arquivo = novo_arquivo(aluno)
    envelhecer_arquivo(arquivo, 2)

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_arquivos_orfaos", "--horas", "1")

    assert Arquivo.objects.count() == 0


# Regra 13
@pytest.mark.django_db
def test_selecao_de_orfaos_trava_as_linhas(aluno, django_capture_on_commit_callbacks):
    """`select_for_update()` é a metade da spec 13 que impede a corrida: sem a trava,
    um Anexo pode ser gravado apontando para um Arquivo entre o SELECT que o julgou
    órfão e o DELETE que o apaga. Deliberadamente não usamos contador de referências
    -- contador denormalizado desanda em rollback ou clone de versão, e o modo de
    falha dele é apagar arquivo em uso."""
    arquivo = novo_arquivo(aluno)
    envelhecer_arquivo(arquivo, 25)

    with CaptureQueriesContext(connection) as consultas:
        with django_capture_on_commit_callbacks(execute=True):
            call_command("limpar_arquivos_orfaos")

    selects = [
        c["sql"] for c in consultas.captured_queries
        if c["sql"].lstrip().upper().startswith("SELECT") and "cursos_arquivo" in c["sql"]
    ]
    assert selects, "a rotina nem consultou cursos_arquivo"
    assert any("FOR UPDATE" in sql for sql in selects)


# Regra 14
@pytest.mark.django_db
def test_limpeza_de_orfaos_desfeita_nao_apaga_os_bytes(arquivo_qualquer):
    """Mesma inversão dos parciais: apagar os bytes dentro da transação deixa, depois
    de um rollback, a linha de Arquivo de volta no banco apontando para um caminho
    que já não existe -- e o Anexo que a referencia entrega 404 para sempre."""
    caminho = Path(arquivo_qualquer.arquivo.path)
    envelhecer_arquivo(arquivo_qualquer, 25)
    pk = arquivo_qualquer.pk

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            call_command("limpar_arquivos_orfaos")
            raise RuntimeError("algo falhou depois da limpeza")

    assert Arquivo.objects.filter(pk=pk).exists()
    assert caminho.exists()


# Regra 15
@pytest.mark.django_db
def test_limpar_arquivos_orfaos_e_reexecutavel_com_o_arquivo_ja_ausente(
    arquivo_qualquer, django_capture_on_commit_callbacks
):
    """Linha viva com os bytes já fora do disco. Mesma razão dos parciais: a rotina é
    de cron e não pode estourar no primeiro registro meio apagado."""
    envelhecer_arquivo(arquivo_qualquer, 25)
    Path(arquivo_qualquer.arquivo.path).unlink()

    with django_capture_on_commit_callbacks(execute=True):
        call_command("limpar_arquivos_orfaos")

    assert Arquivo.objects.count() == 0
