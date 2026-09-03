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


# --- Segunda onda: overflow, marca e respiro ---------------------------------


def test_onde_email_e_impresso_ha_onde_quebrar():
    """E-mail nao tem espaco: sem ponto de quebra, um endereco longo empurra o
    container e leva a pagina a rolar de lado no celular.

    O risco cresceu quando `como_pessoa` passou a imprimir o endereco no lugar do
    nome de quem ainda nao completou o cadastro: onde antes so havia nomes (que
    quebram em espacos), agora pode haver enderecos.
    """
    for seletor in (
        ".etiquetas li",
        ".registro h3",
        ".registro .detalhe span",
        ".dados-lista dd",
        ".cabecalho-pagina .sub",
    ):
        assert seletor in CSS, f"{seletor} saiu da regra de quebra"
    bloco = re.search(
        r"\.etiquetas li,(.*?)\{(.*?)\}", CSS, re.S
    )
    assert bloco and "overflow-wrap: anywhere" in bloco.group(2)
    # `min-width: 0` junto: sem ele o item de flex/grid nao encolhe abaixo do
    # conteudo, e quebrar o texto nao impede o container de ser empurrado.
    assert "min-width: 0" in bloco.group(2)


def test_o_nome_na_barra_trunca_em_vez_de_empurrar():
    """A barra e uma linha so: ali a saida e reticencia, nao quebra. O valor
    inteiro fica no `title` e na tela do perfil."""
    corpo = regra(".menu-pessoa .quem strong")
    assert "text-overflow: ellipsis" in corpo
    assert "overflow: hidden" in corpo
    base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    assert "<strong title=" in base, "o nome truncado perdeu o title"


def test_a_marca_encolhe_proporcionalmente():
    """`height` fixo com o `max-width: 100%` global ACHATA a marca: a largura cede
    e a altura nao. `max-height` com `height: auto` deixa as duas cederem juntas.
    """
    corpo = regra(".marca img")
    assert "max-height" in corpo
    assert "height: auto" in corpo
    assert re.search(r"(?<!max-)height:\s*2\.625rem", corpo) is None, (
        "a altura voltou a ser fixa, e a marca volta a achatar"
    )


def test_a_marca_cede_no_celular():
    """A 2,625rem a marca mede 202px, e num aparelho de 320px o `.faixa` deixa
    272px: ela mais o escudo tomavam a barra inteira e o menu ia para a segunda
    linha, num cabecalho `sticky`."""
    assert "@media (max-width: 30rem)" in CSS
    inicio = CSS.index("@media (max-width: 30rem)", CSS.index(".instituicao span"))
    bloco = CSS[inicio : CSS.index("\n}\n", CSS.index(".barra .faixa", inicio))]
    assert ".marca img" in bloco and "max-height: 1.875rem" in bloco


def test_a_busca_tem_a_guarda_dos_outros_grids():
    """Era o unico grid fluido da folha sem `min(100%, ...)`: sem ela a coluna
    nao encolhe abaixo do valor fixo e forca rolagem lateral."""
    corpo = regra(".busca form")
    assert "minmax(min(100%, 12.5rem), 1fr)" in corpo


def test_todo_grid_fluido_tem_a_guarda():
    """A regra da casa, agora cobrada: `repeat(auto-fit|auto-fill, minmax(X, 1fr))`
    sem `min(100%, X)` e o padrao que forca rolagem lateral em tela estreita.

    Prende a REGRA, e nao o caso da busca: o proximo grid escrito sem a guarda
    reprova aqui, que e o que faltava quando este defeito nasceu.
    """
    sem_guarda = [
        achado.group(0)
        for achado in re.finditer(
            r"repeat\(auto-(?:fit|fill),\s*minmax\((?!min\()[^)]*\)", CSS
        )
    ]
    assert sem_guarda == [], "grid fluido sem min(100%, ...):\n" + "\n".join(sem_guarda)


def test_o_respiro_lateral_cede_no_celular():
    """96px de padding acumulado num viewport de 375px sao 26% da tela gastos
    antes de qualquer conteudo."""
    inicio = CSS.index("@media (max-width: 30rem)")
    bloco = CSS[inicio : CSS.index("/* ---------- barra do topo", inicio)]
    assert "padding-inline: 1rem" in bloco
    assert ".bloco," in bloco and "padding: 1.125rem" in bloco


# --- Terceira onda: gatilho de ajuda, palavras-chave e breakpoints -----------


def test_o_gatilho_de_ajuda_ganha_alvo_no_toque():
    """17 por 17 pixels e o menor alvo dos formularios, e ele aparece ao lado de
    todo campo. O desenho continua com 17px: um gatilho maior ao lado de cada
    rotulo e o que o `all: unset` da regra existe para evitar."""
    inicio = CSS.index(".ajuda-campo::after")
    bloco = CSS[CSS.rindex("@media (pointer: coarse)", 0, inicio) : CSS.index("\n}", CSS.index("height:", inicio))]
    assert "height: 2.75rem" in bloco
    # O desenho nao mudou junto.
    assert "width: 1.0625rem" in regra(".ajuda-campo")


def test_o_alvo_do_gatilho_nao_alcanca_o_rotulo():
    """Clicar no rotulo tem funcao propria: foca o campo. Um alvo de 44 de largura
    se estenderia 13,5px para cada lado e comeria a ultima letra do rotulo, que
    fica a 12px dali (`gap` de 0,375rem mais `margin-left` de 0,375rem).

    A conta e feita aqui para que mudar qualquer um dos tres numeros sem rever os
    outros reprove: e a mesma ideia do teste que amarra o vao dos pontos a largura
    do alvo deles.
    """
    largura_gatilho = 1.0625
    vao = float(re.search(r"\.rotulo-campo\s*\{[^}]*gap:\s*([\d.]+)rem", CSS, re.S).group(1))
    margem = float(re.search(r"\.ajuda-campo\s*\{.*?margin-left:\s*([\d.]+)rem", CSS, re.S).group(1))
    alvo = float(
        re.search(r"\.ajuda-campo::after\s*\{[^}]*width:\s*([\d.]+)rem", CSS, re.S).group(1)
    )
    folga = vao + margem
    avanco = (alvo - largura_gatilho) / 2
    assert avanco < folga, (
        f"o alvo avança {avanco}rem para a esquerda e o rótulo está a {folga}rem: "
        "clicar no fim do rótulo abriria o balão em vez de focar o campo"
    )


def test_as_caixas_de_palavra_chave_nao_espremem_no_celular():
    """Cinco colunas ja em 480px davam ~55px uteis a cada campo. Duas ali, cinco
    a partir do tablet."""
    inicio = CSS.index("Duas colunas no celular grande")
    bloco = CSS[inicio : CSS.index("\n}\n", CSS.index(".caixas-palavras", inicio))]
    assert "repeat(2, minmax(0, 1fr))" in bloco
    # E as cinco continuam existindo, mais acima na escala.
    assert "@media (min-width: 48rem)" in CSS
    largas = CSS[CSS.index("As cinco numa linha so a partir do tablet") :]
    assert "repeat(5, minmax(0, 1fr))" in largas[:400]


def test_os_breakpoints_estao_declarados():
    """Seis valores sem sistema era o achado; a lista nao os unifica de uma vez,
    mas diz qual escolher no proximo layout."""
    assert "Breakpoints do projeto" in CSS
    for ponto in ("30rem (480px)", "48rem (768px)", "62rem (992px)"):
        assert ponto in CSS, ponto


def test_nenhum_breakpoint_novo_entrou_fora_da_lista():
    """A lista so vale se for cobrada. Os tres declarados mais os tres herdados
    (44, 56 e 58rem, que a propria lista registra como pendentes) sao os unicos
    valores de largura que a folha pode usar.
    """
    larguras = set(re.findall(r"@media \((?:min|max)-width:\s*([\d.]+)rem\)", CSS))
    assert larguras <= {"30", "44", "48", "56", "58", "62"}, (
        f"breakpoint fora da lista: {sorted(larguras - {'30', '44', '48', '56', '58', '62'})}"
    )
