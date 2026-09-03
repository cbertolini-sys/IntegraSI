"""Alvos de toque e navegação por dedo.

A base de botões define `min-height: 2.75rem`, que são os 44px recomendados para
alvo de toque, e a paginação e os botões de ação herdam isso. Três componentes da
vitrine pública escreviam `min-height: 0` para sair da regra, e o resultado era a
tela mais visitada do sistema sendo a de alvos menores.

Testes de folha de estilo, e não de navegador: são os valores declarados que este
arquivo prende, do mesmo jeito que `test_estilo.py` já lê o CSS para provar que
nenhuma regra anula um `hidden` de template. O que um navegador confirmaria (o
alvo realmente clicável) nenhum teste daqui alcança.
"""

import re
from pathlib import Path

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)
CSS = (RAIZ / "static" / "css" / "integrasi.css").read_text(encoding="utf-8")
VITRINE = (RAIZ / "static" / "js" / "vitrine.js").read_text(encoding="utf-8")


def regra(seletor):
    """As declaracoes da primeira regra com este seletor exato, sem comentario.

    Sem tirar o comentario, um teste que procura `min-height: 0` casa com a
    propria frase que explica por que aquele valor SAIU dali. Foi o que a
    primeira versao deste arquivo fez, e e o mesmo padrao que ja tinha reprovado
    o `<button>` citado dentro de um comentario de template.
    """
    achado = re.search(
        rf"(?:^|\n)\s*{re.escape(seletor)}\s*\{{(.*?)\}}", CSS, re.S
    )
    assert achado, f"regra não encontrada: {seletor}"
    return re.sub(r"/\*.*?\*/", "", achado.group(1), flags=re.S)


def test_o_botao_do_catalogo_respeita_o_piso_de_toque():
    """`.ver-mais` e o caminho principal do catalogo publico: e o botao "Ver
    detalhes" de cada curso na vitrine. Escrevia `min-height: 0` e ficava com
    cerca de 35px de altura."""
    corpo = regra(".ver-mais")
    assert "min-height: 2.75rem" in corpo
    assert "min-height: 0" not in corpo


def test_o_ponto_da_vitrine_ganha_alvo_maior_no_toque():
    """No dedo, o ponto de 8px era o unico controle da vitrine abaixo de 992px.

    O alvo cresce por `::before`, e nao pelo tamanho do proprio ponto: o desenho
    de tracinho do ativo faz parte da identidade do heroi.
    """
    assert "@media (pointer: coarse)" in CSS
    inicio = CSS.index("@media (pointer: coarse)")
    bloco = CSS[inicio : CSS.index("\n}", CSS.index(".ponto::before", inicio))]
    assert ".ponto::before" in bloco
    assert "height: 2.75rem" in bloco


def test_os_alvos_dos_pontos_nao_se_sobrepoem():
    """Alvo maior que o espacamento faz dois pontos disputarem o mesmo toque, e
    quem ganha e a ordem de pintura - pior que um alvo pequeno e previsivel.

    `calc(100% + 1rem)` amarra a largura do alvo ao vao entre os pontos: os dois
    saem do mesmo `1rem`, entao eles encostam sem invadir um ao outro. Mudar o
    `gap` sem mudar o alvo (ou o contrario) quebra este teste.
    """
    inicio = CSS.index("@media (pointer: coarse)")
    bloco = CSS[inicio : CSS.index("\n}", CSS.index(".ponto::before", inicio))]
    vao = re.search(r"\.pontos\s*\{[^}]*gap:\s*([\d.]+)rem", bloco)
    alvo = re.search(r"width:\s*calc\(100% \+ ([\d.]+)rem\)", bloco)
    assert vao and alvo, "gap dos pontos ou largura do alvo não encontrados"
    assert vao.group(1) == alvo.group(1), (
        f"o vão é {vao.group(1)}rem e o alvo soma {alvo.group(1)}rem: "
        "os alvos passam a se sobrepor ou a deixar buraco entre eles"
    )


def test_o_carrossel_para_ao_toque():
    """`mouseenter` nao dispara no dedo: o carrossel seguia avancando a cada seis
    segundos enquanto a pessoa lia, e voltar exigia acertar um ponto."""
    assert "'pointerdown', parar" in VITRINE


def test_o_carrossel_troca_de_slide_ao_arrastar():
    """O gesto que a pessoa tenta primeiro, e o unico caminho de tamanho decente
    no celular: as setas ficam escondidas abaixo de 992px."""
    assert "pointerup" in VITRINE
    assert "DESLOCAMENTO_MINIMO" in VITRINE


def test_o_arrasto_ignora_gesto_vertical():
    """Sem conferir o eixo, rolar a pagina com o dedo comecando em cima do
    cartao trocaria o slide no meio da leitura."""
    assert "Math.abs(dx) <= Math.abs(dy)" in VITRINE


def test_o_palco_libera_a_rolagem_vertical():
    """`touch-action: pan-y`: sem isto o navegador segura o gesto para decidir o
    que fazer com ele, e a troca sai atrasada - ou a pagina para de rolar em
    cima do carrossel, que e pior."""
    assert "touch-action: pan-y" in regra(".vitrine-palco")
