"""Um envio por clique, com `static/js/envio.js` executado de verdade.

Trinta e cinco botoes de envio no sistema e um unico indicador de progresso: nas
acoes lentas nada muda na tela entre o clique e a resposta, e o proximo
movimento previsivel e clicar de novo. Em "submeter a coordenacao" isso e duas
notificacoes para a mesma transicao; no upload, dois arquivos.

Nenhum teste de view alcanca esta regra: ela e sobre o pedido que o navegador
NAO manda. Os cenarios rodam sob node, no mesmo arranjo de
`apps/cursos/tests/test_upload_js.py`.

As regras, todas do lado do navegador:

1. O primeiro envio passa.
2. O segundo e barrado.
3. O botao apertado NUNCA recebe `disabled`: o corpo do POST e montado depois do
   evento `submit`, e o par nome/valor de um botao desabilitado nao entra nele.
4. Ele recebe `aria-disabled`, que avisa sem apagar o dado.
5. De quatro botoes no mesmo formulario, o marcado e o que foi apertado.
6. Validacao do navegador libera o formulario (ela barra o envio sem disparar
   outro `submit`, e sem isto o formulario travaria para sempre).
7. Voltar pelo historico libera.
8. Resposta do HTMX libera.
9. O formulario de upload de video fica de fora: `upload.js` cuida dele.
10. O ouvinte e preso na fase de CAPTURA. Em bolha, todo manipulador do proprio
    formulario roda antes dele - inclusive o do HTMX, que ja teria disparado o
    pedido. Achado num navegador de verdade, com os nove primeiros verdes.
11. O envio barrado corta a propagacao. `preventDefault` sozinho cancela so a
    acao padrao do navegador; os outros ouvintes rodam do mesmo jeito.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

RAIZ = Path(settings.BASE_DIR)
HARNESS = RAIZ / "tests" / "js" / "testa_envio.js"

# A lista vive aqui, e nao e lida do proprio resultado: um cenario renomeado ou
# apagado no .js tem que aparecer como teste falhando, e nao como teste que
# silenciosamente deixou de existir.
CENARIOS = [
    "o_primeiro_envio_passa",
    "o_segundo_envio_e_barrado",
    "o_botao_apertado_nunca_recebe_disabled",
    "o_botao_apertado_e_marcado_para_a_tecnologia_assistiva",
    "de_quatro_botoes_o_marcado_e_o_que_foi_apertado",
    "validacao_do_navegador_libera_o_formulario",
    "voltar_pelo_historico_libera_o_formulario",
    "resposta_do_htmx_libera_o_formulario",
    "o_upload_de_video_nao_e_bloqueado",
    "o_ouvinte_de_submit_e_preso_na_fase_de_captura",
    "o_envio_barrado_tambem_corta_a_propagacao",
]

sem_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node nao esta instalado; os cenarios do envio.js nao rodam",
)


@pytest.fixture(scope="session")
def resultado_dos_cenarios():
    processo = subprocess.run(
        [shutil.which("node") or "node", str(HARNESS)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if processo.returncode != 0:
        pytest.fail(
            f"o harness do envio.js nao rodou (codigo {processo.returncode}):\n"
            f"{processo.stderr}\n{processo.stdout}"
        )
    return json.loads(processo.stdout)


@sem_node
@pytest.mark.parametrize("nome", CENARIOS)
def test_cenario_do_navegador(resultado_dos_cenarios, nome):
    assert nome in resultado_dos_cenarios, "cenário sumiu de testa_envio.js"
    assert resultado_dos_cenarios[nome]["ok"], resultado_dos_cenarios[nome]["erro"]


@sem_node
def test_a_lista_de_cenarios_daqui_cobre_o_harness_inteiro(resultado_dos_cenarios):
    """Cenário acrescentado ao .js e esquecido aqui nunca chegaria a rodar."""
    assert sorted(resultado_dos_cenarios) == sorted(CENARIOS)


def test_o_envio_js_e_carregado_em_toda_tela():
    """O arquivo so vale se estiver no `base.html`: um `envio.js` perfeito e nao
    carregado deixaria os nove cenários verdes e o sistema sem proteção
    nenhuma."""
    base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    assert "js/envio.js" in base, "envio.js não é carregado em lugar nenhum"


def test_o_botao_ocupado_muda_de_aparencia():
    """`aria-disabled` avisa quem usa leitor de tela; sem regra de CSS, quem
    enxerga continua sem sinal nenhum de que o clique foi recebido - que é o
    defeito que esta tarefa existe para corrigir."""
    css = (RAIZ / "static" / "css" / "integrasi.css").read_text(encoding="utf-8")
    assert 'button[aria-disabled="true"]' in css, "o botão ocupado não muda na tela"
