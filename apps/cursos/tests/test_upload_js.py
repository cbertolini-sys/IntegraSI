"""O JavaScript do upload retomavel, executado de verdade (Plano 4, Task 3).

`static/js/upload.js` e o unico ponto do sistema com JS proprio, e e onde mora o
risco desta tarefa: nenhum teste de view alcanca o laco de retomada, o cabecalho
CSRF ou a leitura do `sessionStorage`. Playwright e um servidor de verdade seriam
desproporcionais para 200 linhas - mas rodar essas 200 linhas sob node, com
`fetch`, `sessionStorage` e `setTimeout` de mentira, custa 100 ms e prende o que
importa.

Os cenarios estao em `apps/cursos/tests/js/testa_upload.js`, um por regra. Este
arquivo so os executa e transforma cada um num teste do pytest, para que a
campanha de delecao de guardas veja qual regra cada mutacao mata.

As regras, todas do lado do navegador:

 1. O arquivo e fatiado no tamanho que o formulario informa (dois cenarios, com
    tamanhos diferentes: um so nao distingue "leu o dado" de "acertou por acaso").
 2. Todo POST leva o `X-CSRFToken` deste formulario - nao o primeiro token do
    documento.
 3. As quatro URLs saem do formulario, com a marca do UUID trocada.
 4. Uma queda de conexao no meio nao perde o upload.
 5. DUAS quedas tambem nao. E o ponto inteiro da tarefa.
 6. Cada tentativa pergunta ao servidor onde parou, em vez de confiar no
    deslocamento local.
 7. A espera entre tentativas cresce.
 8. O numero de tentativas e limitado, e a desistencia explica o que houve.
 9. Recusa do servidor (4xx) e definitiva: nao entra no laco de retomada.
10. O identificador guardado na sessao e LIDO de volta - recarregar a pagina
    retoma em vez de orfanar os bytes que ja subiram.
11. Guardado que o servidor esqueceu (404) e descartado.
12. Guardado de arquivo de outro tamanho tambem.
13. Queda de REDE ao conferir o guardado NAO descarta nada.
14. A chave sai da memoria quando o video entra.
14b. E a tela recarrega, para o anexo novo aparecer na lista de materiais.
15. Sem arquivo escolhido, nada e enviado.
16. O deslocamento do proximo bloco vem do `recebido` do servidor.
17. A barra de progresso acompanha o envio.
18. Servidor que aceita bloco sem avancar nao vira laco infinito.
19. A conclusao leva titulo e duracao do formulario.
20. O `submit` do formulario de video e interceptado: sem isso o formulario
    faria um POST comum para a propria pagina e NADA do upload.js rodaria,
    com a suite inteira verde.
20b. E o `submit` dos outros formularios da tela passa direto.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "testa_upload.js"

# A lista vive aqui, e nao e lida do proprio resultado: um cenario renomeado ou
# apagado no .js tem que aparecer como teste falhando, e nao como teste que
# silenciosamente deixou de existir.
CENARIOS = [
    "fatia_no_tamanho_que_o_formulario_manda",
    "outro_tamanho_de_bloco_muda_o_fatiamento",
    "manda_o_csrf_deste_formulario_em_todo_post",
    "usa_as_urls_que_o_formulario_entrega",
    "uma_queda_no_meio_nao_perde_o_upload",
    "duas_quedas_no_meio_nao_perdem_o_upload",
    "pergunta_ao_servidor_onde_parou_a_cada_tentativa",
    "espera_mais_a_cada_tentativa",
    "desiste_depois_do_limite_de_tentativas",
    "recusa_do_servidor_nao_e_retentada",
    "retoma_o_upload_guardado_depois_de_recarregar_a_pagina",
    "identificador_guardado_que_o_servidor_esqueceu_e_descartado",
    "guardado_de_arquivo_de_outro_tamanho_e_descartado",
    "queda_de_rede_ao_conferir_o_guardado_nao_descarta_o_que_ja_subiu",
    "chave_some_da_memoria_quando_o_video_entra",
    "recarrega_a_tela_quando_o_video_entra",
    "sem_arquivo_nao_fala_com_o_servidor",
    "o_deslocamento_do_proximo_bloco_vem_do_servidor",
    "a_barra_de_progresso_acompanha_o_envio",
    "servidor_que_nao_avanca_nao_vira_laco_infinito",
    "conclui_com_titulo_e_duracao_do_formulario",
    "o_submit_do_formulario_de_video_e_interceptado",
    "submit_de_outro_formulario_nao_e_interceptado",
]

sem_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node nao esta instalado; os cenarios do upload.js nao rodam",
)


@pytest.fixture(scope="session")
def resultado_dos_cenarios():
    """Roda o harness uma vez por sessao e devolve {cenario: (ok, erro)}."""
    processo = subprocess.run(
        [shutil.which("node") or "node", str(HARNESS)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if processo.returncode != 0:
        pytest.fail(
            f"o harness do upload.js nao rodou (codigo {processo.returncode}):\n"
            f"{processo.stderr}\n{processo.stdout}"
        )
    return json.loads(processo.stdout)


@sem_node
@pytest.mark.parametrize("nome", CENARIOS)
def test_cenario_do_navegador(resultado_dos_cenarios, nome):
    assert nome in resultado_dos_cenarios, "cenário sumiu de testa_upload.js"
    assert resultado_dos_cenarios[nome]["ok"], resultado_dos_cenarios[nome]["erro"]


@sem_node
def test_a_lista_de_cenarios_daqui_cobre_o_harness_inteiro(resultado_dos_cenarios):
    """Cenário acrescentado ao .js e esquecido aqui nunca chegaria a rodar."""
    assert sorted(resultado_dos_cenarios) == sorted(CENARIOS)
