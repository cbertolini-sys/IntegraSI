"""O texto que sai do Quill continua quebrando linha.

`getSemanticHTML()` - a propria serializacao que `editor.js` usa para ler o que
foi digitado - troca TODO espaco por `&nbsp;`, sem condicao nenhuma: nao so em
sequencias de espaco repetido, qualquer espaco. Um paragrafo inteiro de prosa
vira, para o navegador, uma unica "palavra" sem ponto de quebra. Quando esse
texto e mostrado numa caixa mais estreita que a linha inteira (a ficha do curso,
o comentario de revisao, o motivo de despublicacao), ele atravessa a caixa e
some atras do card vizinho, em vez de dobrar a linha.

Achado numa revisao de verdade: um aluno submeteu o Plano de Ensino, o professor
abriu para revisar, e o texto da ementa saiu ilegivel, com a caixa "Tudo certo"
da lateral por cima da frase.

Duas guardas, porque o defeito tem duas metades:

1. Dai em diante (`normalizarEspacos`, testada sob node em
   `tests/js/testa_editor.js`): novo texto salvo pelo editor nao grava mais nbsp
   nenhum, entao a proxima geracao de conteudo nasce sem o problema.
2. O que ja esta gravado (`.texto-quill` no CSS, testada aqui): as secoes e
   comentarios que ja existem no banco, escritos ANTES desta correcao, continuam
   com `&nbsp;` guardado. Sem uma regra de quebra na tela, eles ficam ilegiveis
   para sempre, porque ninguem vai reescrever o que ja esta salvo so por causa
   disto. `overflow-wrap: anywhere` forca a quebra mesmo dentro de uma sequencia
   que o navegador, por natureza, trataria como uma palavra so.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.conf import settings

RAIZ = Path(settings.BASE_DIR)
HARNESS = RAIZ / "tests" / "js" / "testa_editor.js"
CSS = (RAIZ / "static" / "css" / "integrasi.css").read_text(encoding="utf-8")
EDITOR_JS = (RAIZ / "static" / "js" / "editor.js").read_text(encoding="utf-8")

CENARIOS = [
    "troca_todo_nbsp_por_espaco_normal",
    "duas_sequencias_de_nbsp_nao_se_confundem",
    "html_sem_nbsp_nenhum_sai_igual",
    "nao_mexe_em_outras_entidades",
]

sem_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node nao esta instalado; os cenarios do editor.js nao rodam",
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
            f"o harness do editor.js nao rodou (codigo {processo.returncode}):\n"
            f"{processo.stderr}\n{processo.stdout}"
        )
    return json.loads(processo.stdout)


@sem_node
@pytest.mark.parametrize("nome", CENARIOS)
def test_cenario_do_navegador(resultado_dos_cenarios, nome):
    assert nome in resultado_dos_cenarios, "cenário sumiu de testa_editor.js"
    assert resultado_dos_cenarios[nome]["ok"], resultado_dos_cenarios[nome]["erro"]


@sem_node
def test_a_lista_de_cenarios_daqui_cobre_o_harness_inteiro(resultado_dos_cenarios):
    """Cenário acrescentado ao .js e esquecido aqui nunca chegaria a rodar."""
    assert sorted(resultado_dos_cenarios) == sorted(CENARIOS)


def test_o_ponto_de_chamada_usa_a_funcao_pura():
    """A funcao pura provada sob node so vale se o editor de verdade a chamar.

    Uma regra pode estar provada de um lado da fronteira de funcao e solta do
    outro: `normalizarEspacos` podia existir, passar nos quatro cenarios acima,
    e o `text-change` continuar montando `campo.value` a partir do
    `getSemanticHTML()` cru, sem passar por ela. A suite sob node ficaria verde
    do mesmo jeito, e o defeito na tela continuaria intacto.
    """
    trecho = EDITOR_JS[EDITOR_JS.index("'text-change'") :]
    trecho = trecho[: trecho.index(");", trecho.index("});")) + 3]
    assert "normalizarEspacos(editor.getSemanticHTML())" in trecho, (
        "o normalizador existe mas o text-change não passa por ele:\n" + trecho
    )


def test_o_css_forca_quebra_onde_o_quill_escreveu():
    """A guarda que cobre o que ja esta no banco, gravado antes da correcao."""
    assert ".texto-quill {" in CSS, "a classe .texto-quill não existe no CSS"
    inicio = CSS.index(".texto-quill {")
    regra = CSS[inicio : CSS.index("}", inicio)]
    assert "overflow-wrap: anywhere" in regra, (
        "a classe existe mas não força a quebra: " + regra
    )


# --- Os seis pontos onde texto do Quill chega a tela --------------------------

# Um por linha, e nao um grep generico: a lista existe para que ESTE teste, e nao
# uma seguranca implicita ("component compartilhado"), garanta que nenhum dos
# seis ficou de fora quando um setimo aparecer.
PONTOS_DE_RENDERIZACAO = [
    ("cursos/_secao.html", "secao.conteudo"),
    ("cursos/revisar.html", "secao.conteudo"),
    ("cursos/analisar_curso.html", "secao.conteudo"),
    ("cursos/entregavel.html", "ultima_revisao.comentario"),
    ("cursos/_historico.html", "revisao.comentario"),
    ("cursos/_historico_do_curso.html", "transicao.observacao"),
]


@pytest.mark.parametrize("caminho,variavel", PONTOS_DE_RENDERIZACAO)
def test_todo_ponto_que_mostra_texto_do_quill_tem_a_classe(caminho, variavel):
    """Os seis campos por tras destes templates passam pelo Quill (tem
    `data-editor` na tela onde sao escritos): `Secao.conteudo` e
    `Revisao.comentario`/`LogTransicaoCurso.observacao`, escritos nos comentarios
    de decisao e de despublicacao de `analisar_curso.html` e `revisar.html`.
    Todos os seis podem carregar `&nbsp;` de conteudo salvo antes da correcao.
    """
    texto = (RAIZ / "templates" / caminho).read_text(encoding="utf-8")
    padrao = re.compile(
        r'<div\b[^>]*class="([^"]*)"[^>]*>\s*\{\{\s*' + re.escape(variavel) + r"\s*\|safe\s*\}\}"
    )
    achado = padrao.search(texto)
    assert achado, f"{caminho}: não achei a div que renderiza {{{{ {variavel}|safe }}}}"
    assert "texto-quill" in achado.group(1).split(), (
        f"{caminho}: a div de {variavel} não tem a classe texto-quill "
        f"(classes atuais: {achado.group(1)!r})"
    )
