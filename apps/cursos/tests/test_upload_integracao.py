"""Upload retomavel no navegador (Plano 4, Task 3) — o lado que roda em Python.

O JavaScript em si esta preso em `test_upload_js.py`, que o executa sob node com
`fetch` e `sessionStorage` de mentira. Aqui ficam duas coisas que o navegador NAO
consegue provar: o contrato do servidor com blocos do tamanho de verdade, e o
formulario que o template entrega ao JS.

As regras que este arquivo prende:

 1. O formulario de video aparece no entregavel de VIDEOS quando a producao esta
    aberta.
 2. Nao aparece nos outros quatro entregaveis: o upload em blocos e da rota de
    video, e concluir cria um Anexo de tipo VIDEO — em CARDS ou SLIDES o formulario
    prometeria algo que a abertura e a conclusao recusam. Quem prende essa recusa
    sao as regras 6b e 14b de `test_upload_views.py`; este teste so afirma que a
    tela nao a oferece. Ate a revisao de branco a frase acima era falsa: nada no
    Python conferia o tipo do entregavel, e um POST direto punha um .mp4 dentro do
    entregavel de Slides.
 3. Nao aparece com o entregavel congelado, pelo mesmo motivo que o formulario de
    anexar tambem some: a conclusao reconfere `pode_editar_producao` e recusaria.
 4. As quatro URLs saem de `urls.py` pelo `{% url %}`, e nao escritas a mao no JS.
 5. O tamanho do bloco sai do Python (`arquivos.TAMANHO_BLOCO`), e nao de uma
    segunda copia dentro do JS.
 6. Um bloco inteiro cabe em `DATA_UPLOAD_MAX_MEMORY_SIZE`: acima disso o Django
    recusa o corpo antes da view, e nenhum teste de view veria o problema.
 7. A faixa de duracao oferecida no formulario e a que `validacoes` cobra; nada de
    numero inventado no HTML.
 7b. O `maxlength` do titulo sai do proprio campo do Anexo, pelo mesmo motivo. Sem
    ele o aluno so descobria o limite depois de meia hora de upload, e o servidor
    devolvia um 400 opaco — a UX do vazamento que a revisao de branco achou.
 8. iniciar -> bloco -> bloco -> concluir funciona com blocos do tamanho que o JS
    envia de verdade.
 9. Depois de uma queda no meio, `upload_estado` diz onde parou e os blocos que
    faltam completam o arquivo.
"""

import json

import pytest
from django.conf import settings
from django.urls import reverse

from apps.cursos import services, validacoes
from apps.cursos.arquivos import TAMANHO_BLOCO
from apps.cursos.choices import StatusEntregavel, TipoEntregavel
from apps.cursos.models import Anexo
from apps.cursos.views.upload import UUID_MODELO

# Um arquivo com dois blocos cheios e um terceiro de sobra: e o unico tamanho que
# exercita ao mesmo tempo o bloco cheio, o bloco parcial do fim e a aritmetica de
# deslocamento entre eles.
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * (TAMANHO_BLOCO * 2)


@pytest.fixture
def curso_com_equipe(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso


@pytest.fixture
def entregavel_videos(curso_com_equipe):
    return curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.VIDEOS)


def inicia(client, entregavel, nome="aula.mp4", tamanho=len(MP4)):
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


def tela(client, entregavel):
    return client.get(reverse("entregavel", args=[entregavel.pk])).content.decode()


# --- Regras 1 a 3: quando o formulario aparece -----------------------------


# Regra 1
@pytest.mark.django_db
def test_entregavel_de_videos_aberto_mostra_o_formulario_de_upload(
    client, aluno, entregavel_videos
):
    client.force_login(aluno)
    conteudo = tela(client, entregavel_videos)
    assert "data-upload-video" in conteudo
    assert "js/upload.js" in conteudo


# Regra 2
@pytest.mark.django_db
@pytest.mark.parametrize(
    "tipo",
    [
        TipoEntregavel.PLANO_ENSINO,
        TipoEntregavel.CARDS,
        TipoEntregavel.CADERNO,
        TipoEntregavel.SLIDES,
    ],
)
def test_outros_entregaveis_nao_mostram_o_formulario_de_upload(
    client, aluno, curso_com_equipe, tipo
):
    outro = curso_com_equipe.entregaveis.get(tipo=tipo)
    client.force_login(aluno)
    conteudo = tela(client, outro)
    # A tela continua editavel — o formulario de anexar esta la. So o de video nao.
    assert "Anexar" in conteudo
    assert "data-upload-video" not in conteudo


# Regra 3
@pytest.mark.django_db
def test_entregavel_de_videos_congelado_nao_mostra_o_formulario_de_upload(
    client, aluno, entregavel_videos
):
    entregavel_videos.status = StatusEntregavel.EM_REVISAO
    entregavel_videos.save(update_fields=["status", "atualizado_em"])
    client.force_login(aluno)
    conteudo = tela(client, entregavel_videos)
    assert "data-upload-video" not in conteudo


# --- Regras 4, 5 e 7: o que o formulario carrega para o JS -----------------


# Regra 4
@pytest.mark.django_db
def test_formulario_carrega_as_quatro_rotas_revertidas_pelo_django(
    client, aluno, entregavel_videos
):
    """As URLs vem do `urls.py`, nao escritas a mao no JS.

    As tres rotas com identificador sao revertidas com um UUID de enfeite que o JS
    troca pelo identificador de verdade. Sem isto o JS montaria
    `/uploads/${id}/bloco/` na mao e uma mudanca em `urls.py` quebraria o navegador
    com a suite inteira verde.
    """
    client.force_login(aluno)
    conteudo = tela(client, entregavel_videos)
    assert f'data-url-iniciar="{reverse("upload_iniciar")}"' in conteudo
    assert f'data-uuid-modelo="{UUID_MODELO}"' in conteudo
    for rota, atributo in [
        ("upload_bloco", "data-url-bloco"),
        ("upload_estado", "data-url-estado"),
        ("upload_concluir", "data-url-concluir"),
    ]:
        esperada = reverse(rota, args=[UUID_MODELO])
        assert f'{atributo}="{esperada}"' in conteudo
        assert UUID_MODELO in esperada


# Regra 5
@pytest.mark.django_db
def test_formulario_carrega_o_tamanho_do_bloco_definido_no_python(
    client, aluno, entregavel_videos
):
    client.force_login(aluno)
    assert f'data-tamanho-bloco="{TAMANHO_BLOCO}"' in tela(client, entregavel_videos)


# Regra 6
def test_um_bloco_inteiro_cabe_no_teto_do_corpo_da_requisicao():
    """`HttpRequest.body` recusa corpo acima de `DATA_UPLOAD_MAX_MEMORY_SIZE` antes
    de a view rodar. Se o bloco crescesse alem do teto, todo upload de video
    morreria em producao e nenhum teste de view veria — eles nao passam pelo
    middleware que le o corpo com o tamanho de verdade.

    A relacao entre os dois numeros e a regra; o comentario em `settings.py` sozinho
    nao e mecanismo nenhum.
    """
    assert TAMANHO_BLOCO <= settings.DATA_UPLOAD_MAX_MEMORY_SIZE


# Regra 7
@pytest.mark.django_db
def test_formulario_oferece_a_faixa_de_duracao_que_as_validacoes_cobram(
    client, aluno, entregavel_videos
):
    client.force_login(aluno)
    conteudo = tela(client, entregavel_videos)
    assert f'min="{validacoes.DURACAO_MINIMA}"' in conteudo
    assert f'max="{validacoes.DURACAO_MAXIMA}"' in conteudo


# Regra 7b
@pytest.mark.django_db
def test_formulario_limita_o_titulo_ao_que_o_anexo_aceita(client, aluno, entregavel_videos):
    """O numero sai de `Anexo._meta`, nao de um `200` escrito no HTML: escrito a
    mao, ele divergiria do model no dia em que o campo mudasse, e a divergencia
    reapareceria como um 400 no fim de um upload de 1 GB."""
    client.force_login(aluno)
    limite = Anexo._meta.get_field("titulo").max_length

    assert f'maxlength="{limite}"' in tela(client, entregavel_videos)


# --- Regras 8 e 9: o contrato do servidor com blocos de verdade ------------


# Regra 8
@pytest.mark.django_db
def test_upload_em_tres_blocos_do_tamanho_do_js(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]

    for inicio in range(0, len(MP4), TAMANHO_BLOCO):
        resposta = envia(client, identificador, MP4[inicio : inicio + TAMANHO_BLOCO])
        assert resposta.status_code == 200

    assert conclui(client, identificador).status_code == 200
    assert Anexo.objects.get().arquivo.tamanho == len(MP4)


# Regra 9
@pytest.mark.django_db
def test_retomada_apos_queda_no_meio(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]

    envia(client, identificador, MP4[:TAMANHO_BLOCO])
    # A conexao cai. O navegador volta, pergunta onde parou e continua dali.
    recebido = client.get(reverse("upload_estado", args=[identificador])).json()["recebido"]
    assert recebido == TAMANHO_BLOCO

    for inicio in range(recebido, len(MP4), TAMANHO_BLOCO):
        assert envia(client, identificador, MP4[inicio : inicio + TAMANHO_BLOCO]).status_code == 200

    assert conclui(client, identificador).status_code == 200
    assert Anexo.objects.get().arquivo.tamanho == len(MP4)
