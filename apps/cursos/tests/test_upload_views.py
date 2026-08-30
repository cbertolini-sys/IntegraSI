"""Endpoints do upload em blocos (Plano 4, Task 2).

As regras que este arquivo prende, na ordem em que aparecem:

 1. `upload_iniciar` cria o registro e devolve `{identificador, recebido: 0}`.
 2. `upload_iniciar` exige `pode_editar_producao`: aluno de fora da equipe -> 403.
 3. `upload_iniciar` exige `pode_editar_producao`: entregavel congelado -> 403.
 4. A extensao declarada precisa mapear para um tipo conhecido -> 400 sem registro.
 5. O tamanho declarado tem que caber no teto DAQUELE tipo, na abertura, nao so na
    conclusao: um `.pdf` de 900 MB nao pode passar meia hora enchendo o disco para
    so entao ouvir que PDF para em 20 MB.
 6. Arquivo declarado vazio (0 bytes) e recusado na abertura.
 6b. `upload_iniciar` so abre upload no entregavel de VIDEOS: a conclusao cria um
    Anexo de tipo VIDEO, e num entregavel de SLIDES ele contaria como material de
    slides. Recusado ANTES do primeiro byte, como toda regra que nao precisa ver
    conteudo.
 7. `upload_bloco` remonta os blocos em sequencia e devolve o recebido.
 8. `upload_bloco` recusa bloco que ultrapasse o declarado -> 400.
 9. `upload_estado` devolve recebido/total, que e o que permite retomar.
10. As tres rotas com identificador devolvem 404 (nao 403) para upload de outro
    usuario: 403 confirmaria que o identificador existe.
11. `upload_concluir` cria Arquivo + Anexo de video e apaga o registro.
12. `upload_concluir` recusa upload incompleto -> 400, sem Anexo.
13. `upload_concluir` recusa conteudo que nao bate com a extensao declarada.
13b. Inclusive no sentido inverso: MP4 declarado como `.pdf`. E o unico caso em
    que a conferencia de extensao da conclusao aparece sozinha — nos outros a
    regra "so video" ja teria barrado, e as duas guardas ficariam indistinguiveis.
14. `upload_concluir` recusa arquivo que nao e video MP4.
14b. `upload_concluir` reconfere que o entregavel e o de VIDEOS. Nao e a mesma
    guarda da regra 6b: aqui o registro nasce por fora da view, que e a unica
    forma de a guarda do servico aparecer sozinha.
15. `upload_concluir` reconfere `pode_editar_producao`: meia hora de upload cabe
    inteira dentro da janela em que o professor aprova o entregavel.
16. Duracao ausente ou zero e recusada ANTES de qualquer byte ir para o disco:
    senao a validacao de Anexo derruba a transacao e deixa o arquivo copiado orfao.
16b. Titulo em branco, pelo mesmo motivo e antes dos mesmos bytes.
16c. E a regra geral da qual 16 e 16b sao casos particulares: NENHUMA recusa do
    Anexo acontece depois da copia. Titulo acima de `max_length` nao era pre-
    validado por linha nenhuma e vazava os bytes para sempre — sem linha de
    Arquivo apontando para eles, `limpar_arquivos_orfaos` nunca os acharia.
16d. Rede embaixo de 16c: uma falha inesperada depois da copia (a que a pre-
    validacao nao soube prever) apaga os bytes copiados.
17. O parcial so e apagado depois do commit: uma conclusao desfeita nao pode
    deixar o registro de volta apontando para um arquivo que nao existe mais.
18. Uma conclusao que commita apaga o parcial.
19. Corpo que nao e JSON valido -> 400, nunca 500.
19b. Corpo que e uma lista JSON com os nomes dos campos dentro: passa pela
    checagem de chave (`"titulo" in ["titulo", ...]` e verdadeiro) e so morre no
    `dados["titulo"]`. Quem barra e a exigencia de que o corpo seja um objeto.
20. Chave obrigatoria ausente -> 400, nunca 500.
21. Campo numerico com lixo -> 400, nunca 500.
21b. Campo textual com lixo tambem: `Path(["aula.mp4"])` levanta TypeError.
22. Metodo errado -> 405 nas quatro rotas.
23. Visitante anonimo vai para o login nas quatro rotas.
24. A conclusao nunca le o arquivo inteiro de uma vez (spec 8).
"""

import io
import json
import uuid
from pathlib import Path

import pytest
from django.conf import settings
from django.db import transaction
from django.db.models.fields.files import FieldFile
from django.urls import reverse

from apps.cursos import services, validacoes
from apps.cursos.arquivos import MEGA
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo, Arquivo, UploadEmAndamento

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 56
PDF = b"%PDF-1.7 nao sou video" + b"\x00" * 40


@pytest.fixture
def entregavel_videos(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso.entregaveis.get(tipo=TipoEntregavel.VIDEOS)


def inicia(client, entregavel, tamanho=len(MP4), nome="aula.mp4"):
    return client.post(
        reverse("upload_iniciar"),
        data=json.dumps({"entregavel": entregavel.pk, "nome": nome, "tamanho": tamanho}),
        content_type="application/json",
    )


def envia(client, identificador, conteudo):
    return client.post(
        reverse("upload_bloco", args=[identificador]),
        data=conteudo,
        content_type="application/octet-stream",
    )


def conclui(client, identificador, titulo="Aula 1", duracao_minutos=7):
    return client.post(
        reverse("upload_concluir", args=[identificador]),
        data=json.dumps({"titulo": titulo, "duracao_minutos": duracao_minutos}),
        content_type="application/json",
    )


@pytest.fixture
def upload_completo(aluno, entregavel_videos):
    """Registro ja com todos os bytes de um MP4 em disco, pronto para concluir."""
    upload = UploadEmAndamento.objects.create(
        usuario=aluno, entregavel=entregavel_videos, nome_original="aula.mp4",
        tamanho_total=len(MP4),
    )
    upload.acrescentar(MP4)
    return upload


def congela(entregavel):
    """Entregavel enviado para revisao deixa de ser editavel (Entregavel.editavel)."""
    entregavel.status = StatusEntregavel.EM_REVISAO
    entregavel.save(update_fields=["status", "atualizado_em"])
    return entregavel


def materiais_em_disco():
    pasta = Path(settings.MEDIA_ROOT) / "materiais"
    return [caminho for caminho in pasta.rglob("*") if caminho.is_file()]


# --- Regras 1 a 6: abertura do upload -------------------------------------


# Regra 1
@pytest.mark.django_db
def test_iniciar_devolve_identificador(client, aluno, entregavel_videos):
    client.force_login(aluno)
    resposta = inicia(client, entregavel_videos)

    assert resposta.status_code == 200
    upload = UploadEmAndamento.objects.get()
    assert upload.tamanho_total == len(MP4)
    assert resposta.json() == {"identificador": str(upload.identificador), "recebido": 0}


# Regra 2
@pytest.mark.django_db
def test_aluno_de_fora_nao_inicia_upload(client, outro_aluno, entregavel_videos):
    client.force_login(outro_aluno)

    assert inicia(client, entregavel_videos).status_code == 403
    assert not UploadEmAndamento.objects.exists()


# Regra 3
@pytest.mark.django_db
def test_nao_inicia_upload_em_entregavel_congelado(client, aluno, entregavel_videos):
    congela(entregavel_videos)
    client.force_login(aluno)

    assert inicia(client, entregavel_videos).status_code == 403
    assert not UploadEmAndamento.objects.exists()


# Regra 4
@pytest.mark.django_db
def test_extensao_desconhecida_e_recusada_na_abertura(client, aluno, entregavel_videos):
    client.force_login(aluno)
    resposta = inicia(client, entregavel_videos, nome="agenda.exe")

    assert resposta.status_code == 400
    assert not UploadEmAndamento.objects.exists()


# Regra 5
@pytest.mark.django_db
def test_teto_do_tipo_declarado_vale_na_abertura(client, aluno, entregavel_videos):
    """O teto por tipo so era aplicado na conclusao. Um cliente declarava
    `a.pdf` com 900 MB, o registro nascia (900 MB < 1 GB, o unico teto que o
    modelo conhecia), meia hora de upload consumia um giga de disco — e so no
    fim vinha o "PDF para em 20 MB". A regra existia e era testada; o caminho
    da abertura simplesmente nao a atravessava."""
    client.force_login(aluno)
    resposta = inicia(client, entregavel_videos, nome="material.pdf", tamanho=900 * MEGA)

    assert resposta.status_code == 400
    assert not UploadEmAndamento.objects.exists()


# Regra 6
@pytest.mark.django_db
def test_arquivo_vazio_e_recusado_na_abertura(client, aluno, entregavel_videos):
    """Um upload de 0 byte nasce `completo` sem nunca ter tocado o disco, e a
    conclusao iria stat() um arquivo que nao existe."""
    client.force_login(aluno)
    resposta = inicia(client, entregavel_videos, tamanho=0)

    assert resposta.status_code == 400
    assert not UploadEmAndamento.objects.exists()


# Regra 6b
@pytest.mark.django_db
def test_upload_em_blocos_so_abre_no_entregavel_de_videos(client, aluno, entregavel_videos):
    """A conclusao cria `Anexo(tipo_midia=VIDEO)`, e so o entregavel D o comporta.
    Enquanto isso morava so no `{% if entregavel.tipo == "VIDEOS" %}` do template,
    a UI era a unica aplicacao da regra: um POST direto punha um .mp4 dentro de
    SLIDES. Recusado na abertura para nao gastar meia hora de upload antes."""
    slides = entregavel_videos.curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)

    resposta = inicia(client, slides)

    assert resposta.status_code == 400
    assert not UploadEmAndamento.objects.exists()


# --- Regras 7 a 10: blocos, estado e dono ---------------------------------


# Regra 7
@pytest.mark.django_db
def test_blocos_em_sequencia_montam_o_arquivo(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]
    meio = len(MP4) // 2

    envia(client, identificador, MP4[:meio])
    resposta = envia(client, identificador, MP4[meio:])

    assert resposta.json() == {"recebido": len(MP4), "total": len(MP4)}
    assert UploadEmAndamento.objects.get().caminho().read_bytes() == MP4


# Regra 8
@pytest.mark.django_db
def test_bloco_alem_do_declarado_e_recusado(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]

    resposta = envia(client, identificador, MP4 + b"sobrando")

    assert resposta.status_code == 400
    assert UploadEmAndamento.objects.get().tamanho_recebido == 0


# Regra 9
@pytest.mark.django_db
def test_estado_permite_retomar_de_onde_parou(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]
    envia(client, identificador, MP4[:10])

    estado = client.get(reverse("upload_estado", args=[identificador])).json()

    assert estado == {"recebido": 10, "total": len(MP4)}


# Regra 10
@pytest.mark.django_db
@pytest.mark.parametrize("rota", ["upload_bloco", "upload_estado", "upload_concluir"])
def test_upload_de_outro_usuario_devolve_404(client, aluno, outro_aluno, upload_completo, rota):
    """404 e nao 403 de proposito: 403 confirmaria a quem nao e dono que aquele
    identificador existe. Uma rota que buscasse o registro so por
    `identificador` deixaria o vizinho mandar bloco no upload alheio."""
    identificador = str(upload_completo.identificador)
    client.force_login(outro_aluno)

    if rota == "upload_estado":
        resposta = client.get(reverse(rota, args=[identificador]))
    elif rota == "upload_bloco":
        resposta = envia(client, identificador, MP4)
    else:
        resposta = conclui(client, identificador)

    assert resposta.status_code == 404
    assert not Anexo.objects.exists()


# --- Regras 11 a 16: conclusao --------------------------------------------


# Regra 11
@pytest.mark.django_db
def test_concluir_cria_arquivo_e_anexo_de_video(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]
    envia(client, identificador, MP4)

    resposta = conclui(client, identificador)

    assert resposta.status_code == 200
    anexo = Anexo.objects.get()
    assert anexo.tipo_midia == TipoMidia.VIDEO
    assert anexo.duracao_minutos == 7
    assert anexo.enviado_por == aluno
    assert anexo.arquivo.mime == "video/mp4"
    assert anexo.arquivo.tamanho == len(MP4)
    # Aberto em `with`: um `.read()` solto deixa o descritor do FieldFile aberto ate
    # o coletor de lixo passar, e o ResourceWarning que ele levanta la na frente vira
    # erro (filterwarnings = ["error"]) atribuido a um teste seguinte, ao acaso.
    with anexo.arquivo.arquivo.open("rb") as conteudo:
        assert conteudo.read() == MP4
    assert Arquivo.objects.count() == 1
    assert UploadEmAndamento.objects.count() == 0


# Regra 12
@pytest.mark.django_db
def test_concluir_upload_incompleto_e_recusado(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]
    envia(client, identificador, MP4[:10])

    resposta = conclui(client, identificador)

    assert resposta.status_code == 400
    assert Anexo.objects.count() == 0
    assert UploadEmAndamento.objects.count() == 1


# Regra 13
@pytest.mark.django_db
def test_conteudo_que_nao_bate_com_a_extensao_e_recusado_na_conclusao(
    client, aluno, entregavel_videos
):
    """O nome declarado na abertura nao prova nada sobre os bytes que chegaram:
    a conferencia de conteudo continua sendo obrigatoria no fim."""
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos, tamanho=len(PDF)).json()["identificador"]
    envia(client, identificador, PDF)

    resposta = conclui(client, identificador)

    assert resposta.status_code == 400
    assert Anexo.objects.count() == 0


# Regra 13b
@pytest.mark.django_db
def test_mp4_declarado_com_extensao_de_pdf_e_recusado_na_conclusao(
    client, aluno, entregavel_videos
):
    """O contrario da regra 13, e o unico caso que separa as duas guardas da
    conclusao. Conteudo que nao e video morre na regra "so video MP4" mesmo sem
    conferencia de extensao; MP4 anunciado como `.pdf` atravessa essa regra
    (o conteudo E video/mp4) e so `valida_upload` o barra. Sem ela, o Anexo
    entraria com um nome_original que mente sobre o conteudo — e o teto cobrado
    na abertura teria sido o do PDF, nao o do video."""
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos, nome="aula.pdf").json()["identificador"]
    envia(client, identificador, MP4)

    resposta = conclui(client, identificador)

    assert resposta.status_code == 400
    assert not Anexo.objects.exists()


# Regra 14
@pytest.mark.django_db
def test_arquivo_coerente_que_nao_e_video_e_recusado_na_conclusao(
    client, aluno, entregavel_videos
):
    """PDF anunciado como PDF e enviado como PDF: passa por `valida_upload`
    inteira. Quem o barra e a regra separada de que esta rota so monta Anexo de
    video — sem ela, um PDF viraria um Anexo com tipo_midia=VIDEO."""
    client.force_login(aluno)
    identificador = inicia(
        client, entregavel_videos, tamanho=len(PDF), nome="material.pdf"
    ).json()["identificador"]
    envia(client, identificador, PDF)

    resposta = conclui(client, identificador)

    assert resposta.status_code == 400
    assert Anexo.objects.count() == 0


# Regra 14b
@pytest.mark.django_db
def test_conclusao_recusa_entregavel_que_nao_e_o_de_videos(client, aluno, entregavel_videos):
    """O registro e criado por fora da view de propósito: a guarda da regra 6b
    barraria a abertura e as duas ficariam indistinguiveis. O dano que esta guarda
    evita nao e o anexo torto — e `validacoes.pendencias(slides)` voltar vazia com
    um .mp4 e mais nada dentro: `_slides` conta arquivos, e video e arquivo. O
    roteiro se declararia satisfeito pelo artefato errado."""
    slides = entregavel_videos.curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    upload = UploadEmAndamento.objects.create(
        usuario=aluno, entregavel=slides, nome_original="aula.mp4", tamanho_total=len(MP4)
    )
    upload.acrescentar(MP4)
    client.force_login(aluno)

    resposta = conclui(client, str(upload.identificador))

    assert resposta.status_code == 400
    assert not Anexo.objects.exists()
    assert materiais_em_disco() == []
    assert validacoes.pendencias(slides), "o entregável de slides ficou satisfeito"


# Regra 15
@pytest.mark.django_db
def test_conclusao_reconfere_se_o_entregavel_ainda_esta_aberto(
    client, aluno, entregavel_videos, upload_completo
):
    """Um giga no upstream domestico leva perto de meia hora — tempo de sobra
    para o professor aprovar o entregavel enquanto os blocos sobem. Sem esta
    reconferencia o video entraria num entregavel ja congelado."""
    congela(entregavel_videos)
    client.force_login(aluno)

    resposta = conclui(client, str(upload_completo.identificador))

    assert resposta.status_code == 403
    assert not Anexo.objects.exists()
    assert not Arquivo.objects.exists()
    assert UploadEmAndamento.objects.filter(pk=upload_completo.pk).exists()


# Regra 16
@pytest.mark.django_db
def test_duracao_zerada_e_recusada_antes_de_copiar_os_bytes(client, aluno, upload_completo):
    """`Anexo.clean()` exige duracao para video. Se a conclusao so descobrisse
    isso na ultima linha, o Arquivo ja teria sido copiado para MEDIA_ROOT: a
    transacao desfaz a linha, nao o arquivo em disco — o mesmo orfao que o
    Plano 2 teve que consertar em `anexar`."""
    client.force_login(aluno)

    resposta = conclui(client, str(upload_completo.identificador), duracao_minutos=0)

    assert resposta.status_code == 400
    assert not Anexo.objects.exists()
    assert not Arquivo.objects.exists()
    assert materiais_em_disco() == []


# Regra 16b
@pytest.mark.django_db
def test_titulo_em_branco_e_recusado_antes_de_copiar_os_bytes(client, aluno, upload_completo):
    """Mesma armadilha da regra 16 pelo outro campo obrigatorio do Anexo. So que
    pior: `"   "` nao esta em `empty_values`, entao `Anexo.full_clean()` ACEITA —
    sem esta checagem o video entra com titulo em branco. Um `titulo=""` seria
    recusado no fim, e ainda assim tarde demais: o arquivo ja estaria em disco."""
    client.force_login(aluno)

    resposta = conclui(client, str(upload_completo.identificador), titulo="   ")

    assert resposta.status_code == 400
    assert not Anexo.objects.exists()
    assert not Arquivo.objects.exists()
    assert materiais_em_disco() == []


# Regra 16c
@pytest.mark.django_db
def test_titulo_longo_demais_e_recusado_antes_de_copiar_os_bytes(
    client, aluno, upload_completo, monkeypatch
):
    """`titulo` e `CharField(max_length=200)`. A pre-validacao conferia dois campos
    a mao (16 e 16b) e essa regra nao estava entre eles: os bytes iam para
    MEDIA_ROOT e so entao `Anexo.full_clean()` recusava. A transacao desfaz as
    linhas, nao o arquivo — e sem linha de `Arquivo` apontando para ele,
    `limpar_arquivos_orfaos` (que varre `Arquivo.objects`) nunca o encontraria.

    O espiao em `FieldFile.save` e o que separa esta guarda da rede da regra 16d:
    com a rede sozinha os bytes tambem sumiriam do disco, mas depois de terem sido
    copiados — 1 GB por tentativa, e o aluno tenta de novo."""
    copias = []
    original = FieldFile.save

    def espiao(self, name, content, save=True):
        copias.append(name)
        return original(self, name, content, save=save)

    monkeypatch.setattr(FieldFile, "save", espiao)
    client.force_login(aluno)

    resposta = conclui(client, str(upload_completo.identificador), titulo="x" * 201)

    assert resposta.status_code == 400
    assert not Anexo.objects.exists()
    assert not Arquivo.objects.exists()
    assert copias == [], "os bytes foram copiados antes da recusa"
    assert materiais_em_disco() == []


# Regra 16d
@pytest.mark.django_db
def test_falha_inesperada_depois_da_copia_nao_deixa_bytes_orfaos(
    upload_completo, monkeypatch
):
    """A pre-validacao da regra 16c cobre o que da para prever. Esta rede cobre o
    que nao da: um erro de banco entre a copia e o `Anexo`. Sem ela o arquivo fica
    em MEDIA_ROOT sem nenhuma linha apontando para ele, invisivel para
    `limpar_arquivos_orfaos` e sem alerta nenhum, porque do lado do cron nada
    falhou. E o mesmo `delete(save=False)` que `views/aluno.anexar` ja fazia."""

    def explode(self, *args, **kwargs):
        raise RuntimeError("banco caiu depois da cópia")

    monkeypatch.setattr(Arquivo, "save", explode)

    with pytest.raises(RuntimeError):
        services.concluir_upload(upload_completo, titulo="Aula 1", duracao_minutos=7)

    assert materiais_em_disco() == []


# --- Regras 17 e 18: o parcial e a transacao ------------------------------


# Regra 17
@pytest.mark.django_db
def test_conclusao_desfeita_nao_apaga_o_arquivo_parcial(upload_completo):
    """`caminho.unlink()` dentro do `atomic` e a inversao classica: se a
    transacao volta atras, a linha de UploadEmAndamento ressuscita apontando
    para um arquivo que ja nao existe, e o dono nao consegue nem retomar nem
    concluir. A remocao fisica so pode acontecer depois do commit."""
    caminho = upload_completo.caminho()
    # Guardado antes: `delete()` zera o pk da instancia em memoria, e o rollback
    # devolve a linha ao banco sem devolver o pk ao objeto. Reler
    # `upload_completo.pk` depois consultaria `pk=None` e daria "sumiu" mesmo com a
    # linha de volta no lugar.
    pk = upload_completo.pk

    with pytest.raises(RuntimeError):
        with transaction.atomic():
            services.concluir_upload(upload_completo, titulo="Aula 1", duracao_minutos=7)
            raise RuntimeError("algo falhou depois da conclusão")

    assert UploadEmAndamento.objects.filter(pk=pk).exists()
    assert caminho.exists()
    assert caminho.read_bytes() == MP4


# Regra 18
@pytest.mark.django_db
def test_conclusao_que_commita_apaga_o_parcial(upload_completo, django_capture_on_commit_callbacks):
    caminho = upload_completo.caminho()

    with django_capture_on_commit_callbacks(execute=True):
        services.concluir_upload(upload_completo, titulo="Aula 1", duracao_minutos=7)

    assert not caminho.exists()


# --- Regras 19 a 21: corpo malformado nao vira 500 ------------------------


# Regra 19
@pytest.mark.django_db
@pytest.mark.parametrize("corpo", [b"{nao sou json", b"", b"[1, 2, 3]"])
def test_corpo_que_nao_e_objeto_json_vira_400(client, aluno, entregavel_videos, corpo):
    client.force_login(aluno)

    resposta = client.post(
        reverse("upload_iniciar"), data=corpo, content_type="application/json"
    )

    assert resposta.status_code == 400
    assert not UploadEmAndamento.objects.exists()


# Regra 19 (a outra rota que le JSON)
@pytest.mark.django_db
def test_conclusao_com_json_invalido_vira_400(client, aluno, upload_completo):
    client.force_login(aluno)

    resposta = client.post(
        reverse("upload_concluir", args=[str(upload_completo.identificador)]),
        data=b"{nao sou json",
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert not Anexo.objects.exists()


# Regra 20
@pytest.mark.django_db
@pytest.mark.parametrize("faltando", ["entregavel", "nome", "tamanho"])
def test_abertura_sem_campo_obrigatorio_vira_400(client, aluno, entregavel_videos, faltando):
    completo = {"entregavel": entregavel_videos.pk, "nome": "aula.mp4", "tamanho": len(MP4)}
    del completo[faltando]
    client.force_login(aluno)

    resposta = client.post(
        reverse("upload_iniciar"), data=json.dumps(completo), content_type="application/json"
    )

    assert resposta.status_code == 400
    assert not UploadEmAndamento.objects.exists()


# Regra 20 (conclusao)
@pytest.mark.django_db
@pytest.mark.parametrize("faltando", ["titulo", "duracao_minutos"])
def test_conclusao_sem_campo_obrigatorio_vira_400(client, aluno, upload_completo, faltando):
    completo = {"titulo": "Aula 1", "duracao_minutos": 7}
    del completo[faltando]
    client.force_login(aluno)

    resposta = client.post(
        reverse("upload_concluir", args=[str(upload_completo.identificador)]),
        data=json.dumps(completo),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert not Anexo.objects.exists()


# Regra 21
@pytest.mark.django_db
def test_tamanho_que_nao_e_numero_vira_400(client, aluno, entregavel_videos):
    client.force_login(aluno)

    resposta = inicia(client, entregavel_videos, tamanho="muito grande")

    assert resposta.status_code == 400
    assert not UploadEmAndamento.objects.exists()


# Regra 21 (conclusao)
@pytest.mark.django_db
def test_duracao_que_nao_e_numero_vira_400(client, aluno, upload_completo):
    client.force_login(aluno)

    resposta = conclui(client, str(upload_completo.identificador), duracao_minutos="sete")

    assert resposta.status_code == 400
    assert not Anexo.objects.exists()


# Regra 21 (o pk do entregavel tambem vai para uma consulta)
@pytest.mark.django_db
def test_entregavel_que_nao_e_numero_vira_400(client, aluno, entregavel_videos):
    client.force_login(aluno)

    resposta = client.post(
        reverse("upload_iniciar"),
        data=json.dumps({"entregavel": "abc", "nome": "aula.mp4", "tamanho": len(MP4)}),
        content_type="application/json",
    )

    assert resposta.status_code == 400


# Regra 19b
@pytest.mark.django_db
def test_conclusao_com_lista_json_no_lugar_do_objeto_vira_400(client, aluno, upload_completo):
    """`[1, 2, 3]` nao prova a regra: nenhum nome de campo esta dentro, entao a
    checagem de chave obrigatoria ja recusa. Uma lista com os NOMES dentro passa
    por ela (`"titulo" in ["titulo", ...]` e verdadeiro) e chega ao
    `dados["titulo"]`, que levanta TypeError — 500. Quem a barra e a exigencia de
    que o corpo decodificado seja um objeto JSON."""
    client.force_login(aluno)

    resposta = client.post(
        reverse("upload_concluir", args=[str(upload_completo.identificador)]),
        data=b'["titulo", "duracao_minutos"]',
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert not Anexo.objects.exists()


# Regra 21b
@pytest.mark.django_db
def test_nome_que_nao_e_texto_vira_400(client, aluno, entregavel_videos):
    """O irmao textual da regra 21. `nome` vai direto para `Path(...)`, que
    levanta TypeError diante de uma lista — 500 por corpo malformado do cliente."""
    client.force_login(aluno)

    resposta = client.post(
        reverse("upload_iniciar"),
        data=json.dumps({"entregavel": entregavel_videos.pk, "nome": ["aula.mp4"],
                         "tamanho": len(MP4)}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert not UploadEmAndamento.objects.exists()


# --- Regras 22 e 23: metodo e portao de login -----------------------------


# Regra 22
@pytest.mark.django_db
@pytest.mark.parametrize(
    "rota,metodo", [("upload_iniciar", "get"), ("upload_bloco", "get"),
                    ("upload_estado", "post"), ("upload_concluir", "get")]
)
def test_metodo_errado_e_rejeitado(client, aluno, upload_completo, rota, metodo):
    client.force_login(aluno)
    args = [] if rota == "upload_iniciar" else [str(upload_completo.identificador)]

    resposta = getattr(client, metodo)(reverse(rota, args=args))

    assert resposta.status_code == 405
    assert not Anexo.objects.exists()
    assert UploadEmAndamento.objects.get().tamanho_recebido == len(MP4)


# Regra 23
@pytest.mark.django_db
@pytest.mark.parametrize(
    "rota", ["upload_iniciar", "upload_bloco", "upload_estado", "upload_concluir"]
)
def test_visitante_anonimo_vai_para_o_login(client, rota):
    """Sem @login_required *antes* de tudo, `_meu_upload` filtraria por
    `usuario=AnonymousUser` (erro de banco, 500) e as rotas de POST
    responderiam 405 — nenhuma delas manda a pessoa fazer login."""
    args = [] if rota == "upload_iniciar" else [str(uuid.uuid4())]

    resposta = client.get(reverse(rota, args=args))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))


# --- Regra 24: 1 GB nunca inteiro na memoria ------------------------------


class _LeitorEspiao(io.BufferedReader):
    """Anota o tamanho pedido em cada read() e repassa para o arquivo real."""

    def __init__(self, bruto, registro):
        super().__init__(bruto)
        self._registro = registro

    def read(self, tamanho=-1):
        self._registro.append(tamanho)
        return super().read(tamanho)


@pytest.mark.django_db
def test_conclusao_nunca_le_o_arquivo_inteiro_de_uma_vez(upload_completo, monkeypatch):
    """Spec 8: 1 GB nao pode sentar inteiro na memoria de um worker. Um
    `parcial.read()` sem argumento passaria em todos os outros testes deste
    arquivo — os arquivos de teste tem 80 bytes. Este espiona os tamanhos
    pedidos: nenhum read() sem limite, e nenhum acima de 1 MB."""
    leituras = []
    monkeypatch.setattr(
        services,
        "open",
        lambda caminho, *a, **k: _LeitorEspiao(io.FileIO(str(caminho), "r"), leituras),
        raising=False,
    )

    services.concluir_upload(upload_completo, titulo="Aula 1", duracao_minutos=7)

    assert leituras, "a conclusão não leu o arquivo pelo `open` do módulo"
    assert all(0 < pedido <= MEGA for pedido in leituras), leituras
