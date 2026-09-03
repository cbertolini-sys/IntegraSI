"""A regra de escrita do projeto, aplicada ao repositório inteiro.

Nada de travessão. A regra está no README.md e na CLAUDE.md; aqui ela deixa de
depender de quem lembra e passa a reprovar.

Este arquivo não escreve o símbolo literalmente em lugar nenhum: ele é montado a
partir do código Unicode. Sem isso, o próprio teste precisaria estar na lista de
exceções, e uma regra que não vale para quem a aplica é uma regra pela metade.
"""

import re
import subprocess
from pathlib import Path

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)

TRAVESSAO = chr(0x2014)
# Montada por partes pelo mesmo motivo do caractere: escrever a entidade inteira
# aqui faria este arquivo violar a regra que ele existe para impor.
ENTIDADE = "&" + "mdash;"

# Os dois documentos que DEFINEM a regra precisam mostrar o símbolo para explicá-lo.
# É a única exceção, e ela não é livre: `test_a_excecao_continua_justificada`
# reprova se um deles deixar de falar do assunto, para que a entrada não vire
# permissão esquecida.
PODEM_CITAR = {"README.md", "CLAUDE.md"}


def arquivos_versionados():
    saida = subprocess.run(
        ["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, text=True, check=True
    ).stdout
    return [c for c in saida.split("\0") if c]


def texto_de(caminho):
    """Devolve o conteúdo, ou None se o arquivo não for texto.

    Fonte, imagem e PDF entram no `git ls-files` como qualquer outro; o erro de
    decodificação é o que os separa, sem precisar manter uma lista de extensões
    que envelheceria a cada arquivo novo.
    """
    try:
        return (RAIZ / caminho).read_text(encoding="utf-8")
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        return None


def ocorrencias(procurado):
    achados = []
    for caminho in arquivos_versionados():
        if caminho in PODEM_CITAR:
            continue
        conteudo = texto_de(caminho)
        if conteudo is None or procurado not in conteudo:
            continue
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            if procurado in linha:
                achados.append(f"{caminho}:{numero}: {linha.strip()[:100]}")
    return achados


def test_o_repositorio_nao_usa_travessao():
    """O caractere, em qualquer arquivo de texto versionado.

    Se este teste reprovar num arquivo que você acabou de trazer de fora, a
    correção é reescrever a frase, e não acrescentar o arquivo a `PODEM_CITAR`.
    Ver README.md, seção "Estilo de escrita", para qual pontuação usar em cada caso.
    """
    achados = ocorrencias(TRAVESSAO)
    assert not achados, "travessão encontrado em:\n" + "\n".join(achados)


def test_o_repositorio_nao_usa_a_entidade_do_travessao():
    """A entidade HTML renderiza o mesmo símbolo.

    Teste separado do anterior de propósito: são duas formas de escrever a mesma
    coisa, e um teste só que checasse as duas juntas continuaria verde com
    metade da regra apagada.
    """
    achados = ocorrencias(ENTIDADE)
    assert not achados, "entidade de travessão encontrada em:\n" + "\n".join(achados)


def test_a_excecao_continua_justificada():
    """Os dois arquivos isentos precisam continuar sendo os que explicam a regra.

    Sem isto, `PODEM_CITAR` viraria uma permissão permanente: alguém apagaria a
    seção de estilo do README e a isenção seguiria de pé, deixando dois arquivos
    livres para usar o símbolo sem que nada acusasse.
    """
    for nome in PODEM_CITAR:
        conteudo = texto_de(nome)
        assert conteudo is not None, f"{nome} sumiu"
        assert TRAVESSAO in conteudo, (
            f"{nome} está isento da regra por explicá-la, mas não mostra mais o "
            "símbolo. Tire-o de PODEM_CITAR ou devolva a explicação."
        )
        assert "travessão" in conteudo.lower(), f"{nome} não fala mais da regra"


def test_a_varredura_alcanca_o_repositorio_todo():
    """Prova que a busca não está vazia por engano.

    Um `git ls-files` que devolvesse nada deixaria os testes acima verdes para
    sempre, e o defeito seria invisível: nenhuma ocorrência é exatamente o que
    se espera ver quando tudo está certo.
    """
    arquivos = arquivos_versionados()
    assert len(arquivos) > 100, f"esperava o repositório inteiro, vi {len(arquivos)}"
    legiveis = [c for c in arquivos if texto_de(c) is not None]
    assert len(legiveis) > 100, "quase nada foi lido como texto"


# --- O padrao dos botoes ------------------------------------------------------

MODIFICADORES = ("botao-linha", "botao-largo")


def classes_de_botao():
    """Toda combinacao de classe que contem "botao", com o arquivo onde aparece."""
    achados = []
    for caminho in arquivos_versionados():
        if not caminho.startswith("templates/") or not caminho.endswith(".html"):
            continue
        conteudo = texto_de(caminho)
        if conteudo is None:
            continue
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            for atributo in re.findall(r'class="([^"]*)"', linha):
                classes = atributo.split()
                if any(c.startswith("botao") for c in classes):
                    achados.append((caminho, numero, classes))
    return achados


def test_todo_botao_traz_a_classe_base():
    """Um modificador sozinho nao e botao.

    A base do CSS era `.botao, button`, um seletor de ELEMENTO: `botao-linha` num
    <button> herdava tudo, mas num <a> nao herdava nada e virava link pelado. O
    CSS foi corrigido para nao depender mais do elemento, e este teste mantem a
    marcacao num padrao so, para que a proxima tela nao reinvente a combinacao.
    """
    fora = [
        f"{caminho}:{numero}: {' '.join(classes)}"
        for caminho, numero, classes in classes_de_botao()
        if "botao" not in classes
    ]
    assert not fora, "modificador de botão sem a classe base em:\n" + "\n".join(fora)


def test_nao_ha_classe_de_botao_inventada():
    """So existem tres: a base e dois modificadores. Uma quarta classe seria um
    botao com regra propria, que e como o padrao se perde."""
    conhecidas = {"botao", *MODIFICADORES}
    inventadas = sorted(
        {
            c
            for _, _, classes in classes_de_botao()
            for c in classes
            if c.startswith("botao") and c not in conhecidas
        }
    )
    assert inventadas == [], f"classes de botão fora do padrão: {inventadas}"


def test_a_varredura_de_botoes_acha_alguma_coisa():
    """Um seletor errado devolveria lista vazia e os dois testes acima ficariam
    verdes para sempre."""
    assert len(classes_de_botao()) > 20


# --- Nada de `style` inline nos templates ------------------------------------


def test_nenhum_template_usa_style_inline():
    """Decisão de layout mora na folha de estilo, não no HTML.

    Onze `style` inline foram limpos de uma vez: quatro cores que furavam o
    sistema de acentos que já existia, quatro margens ad hoc e três arranjos de
    botão. O problema não é estético: `margin-top` solto no HTML é decisão
    escondida onde ninguém procura quando o espaçamento sai errado, e uma cor
    fixa ignora o tema.

    Se este teste reprovar num template novo, a correção é criar a classe, não
    acrescentar o arquivo a uma lista de exceções.
    """
    achados = []
    for caminho in arquivos_versionados():
        if not caminho.startswith("templates/") or not caminho.endswith(".html"):
            continue
        conteudo = texto_de(caminho)
        if conteudo is None:
            continue
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            if re.search(r'\sstyle="', linha):
                achados.append(f"{caminho}:{numero}: {linha.strip()[:90]}")
    assert not achados, "style inline em:\n" + "\n".join(achados)


def test_a_varredura_de_style_alcanca_os_templates():
    """Um seletor errado devolveria lista vazia e o teste acima ficaria verde para
    sempre. Confere que a varredura enxerga os templates de verdade."""
    html = [
        c for c in arquivos_versionados()
        if c.startswith("templates/") and c.endswith(".html") and texto_de(c)
    ]
    assert len(html) > 15


# --- Comentario de template que vira texto na tela ----------------------------


def comentarios_de_cerquilha_abertos():
    """Linhas com `{#` que nao fecham na propria linha.

    A sintaxe de cerquilha e de UMA linha so: o lexer do Django casa `{#.*?#}`
    sem DOTALL, entao um comentario de duas linhas nao e reconhecido como
    comentario e sai impresso na pagina, com codigo e tudo.
    """
    achados = []
    for caminho in arquivos_versionados():
        if not caminho.startswith("templates/") or not caminho.endswith(".html"):
            continue
        conteudo = texto_de(caminho)
        if conteudo is None:
            continue
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            if "{#" in linha and "#}" not in linha:
                achados.append(f"{caminho}:{numero}: {linha.strip()[:80]}")
    return achados


def test_nenhum_comentario_de_cerquilha_atravessa_a_linha():
    """Cinco comentarios assim estavam imprimindo texto de codigo em quatro telas,
    entre elas as de revisao do professor e da coordenacao. O aviso ja estava
    escrito em base.html, de uma vez anterior, e mesmo assim voltou.

    Se este teste reprovar, troque o comentario por `{% comment %}`, que fecha em
    qualquer numero de linhas. Nao quebre a frase em varios `{# #}` de uma linha.
    """
    achados = comentarios_de_cerquilha_abertos()
    assert not achados, (
        "comentário de cerquilha de mais de uma linha (sai renderizado como "
        "texto na página) em:\n" + "\n".join(achados)
    )


def test_a_varredura_de_cerquilha_enxerga_comentario_de_uma_linha():
    """Sem isto, um seletor errado devolveria lista vazia e o teste acima ficaria
    verde para sempre. Confere que ha comentarios de cerquilha nos templates e que
    a varredura nao acusa os que estao certos."""
    de_uma_linha = 0
    for caminho in arquivos_versionados():
        if not caminho.startswith("templates/") or not caminho.endswith(".html"):
            continue
        conteudo = texto_de(caminho) or ""
        de_uma_linha += sum(
            1 for linha in conteudo.splitlines() if "{#" in linha and "#}" in linha
        )
    assert de_uma_linha > 0, "a varredura não achou nenhum comentário de cerquilha"


# --- Regra de CSS que anula um `hidden` do template ---------------------------


def alvos_marcados_hidden():
    """Seletores dos elementos que algum template marca com o atributo `hidden`.

    Elemento com classe entra pela classe; sem classe, pela tag. `aria-hidden`
    fica de fora: exige um hífen antes de "hidden", e o `\\s` do padrão não casa.
    """
    alvos = set()
    for caminho in arquivos_versionados():
        if not caminho.startswith("templates/") or not caminho.endswith(".html"):
            continue
        conteudo = texto_de(caminho)
        if conteudo is None:
            continue
        for abertura in re.finditer(r"<(\w+)([^>]*)\shidden(?=[\s/>])", conteudo):
            tag, atributos = abertura.group(1), abertura.group(2)
            classes = re.search(r'class="([^"]*)"', atributos)
            if classes:
                alvos.update("." + c for c in classes.group(1).split())
            else:
                alvos.add(tag)
    return alvos


def regras_que_definem_display():
    """(seletor, corpo) de cada regra da folha de estilo que define `display`."""
    css = texto_de("static/css/integrasi.css") or ""
    # Sem chaves aninhadas nesta folha (nada de @media com regra interna que
    # importe aqui), entao dividir por "}" e suficiente e nao precisa de parser.
    regras = []
    for pedaco in css.split("}"):
        if "{" not in pedaco:
            continue
        seletor, corpo = pedaco.rsplit("{", 1)
        if re.search(r"(^|;|\s)display\s*:", corpo):
            regras.append((seletor.split("*/")[-1].strip(), corpo))
    return regras


def test_nenhuma_regra_de_css_anula_um_hidden_do_template():
    """`hidden` é uma decisão de HTML que o CSS não pode desfazer sem querer.

    O atributo funciona por `[hidden] { display: none }` na folha do navegador,
    que tem especificidade 0-1-0. Qualquer regra nossa um pouco mais específica
    ganha dela: `[data-upload-video] progress { display: block }` fez a barra de
    progresso aparecer sempre, com o `hidden` no HTML e a suíte inteira verde.

    Se este teste reprovar, o conserto é não definir `display` nesse elemento
    (dar a ele um invólucro, ou usar outra propriedade). Voltar a esconder por
    classe em vez de `hidden` também resolve, mas aí o `hidden` some do template
    e o JavaScript precisa saber o nome da classe.
    """
    alvos = alvos_marcados_hidden()
    achados = []
    for seletor, corpo in regras_que_definem_display():
        for parte in seletor.split(","):
            # A última porção do seletor é o elemento que a regra pinta; o resto
            # é contexto. `::-webkit-progress-value` e afins não contam.
            final = parte.strip().split()[-1].split("::")[0].split(":")[0] if parte.strip() else ""
            if final and final in alvos:
                achados.append(f"{parte.strip()} {{{corpo.strip()[:60]}}}")
    assert not achados, (
        "regra de CSS define `display` num elemento que o template marca "
        "`hidden`, o que anula o atributo:\n" + "\n".join(achados)
    )


def test_a_varredura_de_hidden_acha_os_elementos_e_as_regras():
    """Duas listas vazias deixariam o teste acima verde para sempre."""
    assert alvos_marcados_hidden(), "nenhum elemento `hidden` encontrado"
    assert len(regras_que_definem_display()) > 20


def test_nenhum_button_fica_sem_classe():
    """`<button>` sem classe herda o desenho de botao de acao por acidente.

    A base do CSS e `.botao, .botao-linha, .botao-largo, button`: o seletor de
    elemento pinta qualquer botao, entao um `<button>` sem classe PARECE certo e a
    diferenca so aparece quando `.botao` ganha um estado novo. Cinco estavam
    assim, entre eles `Anexar` e `Enviar vídeo`.

    Botao que nao e de acao (o gatilho de ajuda, as setas e os pontos do
    carrossel) tem classe propria e `all: unset`; o que este teste proibe e a
    ausencia de classe, nao a classe diferente.
    """
    achados = []
    for caminho in arquivos_versionados():
        if not caminho.startswith("templates/") or not caminho.endswith(".html"):
            continue
        conteudo = texto_de(caminho)
        if conteudo is None:
            continue
        for abertura in re.finditer(r"<button[^>]*>", conteudo):
            if "class=" not in abertura.group(0):
                linha = conteudo[: abertura.start()].count("\n") + 1
                achados.append(f"{caminho}:{linha}: {abertura.group(0)[:70]}")
    assert not achados, "botão sem classe em:\n" + "\n".join(achados)


# --- O termo de quem produz o material ---------------------------------------

# As classes CSS do fluxograma da pagina Sobre (`fluxo estudante`, `fluxograma
# estudante`). Sao gancho de estilo, nao texto: o rotulo que a pessoa le naquele
# fluxo ja diz "Aluno de Sistemas de Informação". Trocar o gancho mexeria em duas
# regras de CSS e num teste para nao mudar nada na tela - a mesma razao pela qual
# valor gravado nao muda por passada de texto (CLAUDE.md).
GANCHOS_DE_ESTILO = ("fluxo estudante", "fluxograma estudante")


def test_a_interface_diz_aluno_e_nao_estudante():
    """Um termo so para quem produz o material.

    O rotulo de `Usuario.PAPEIS` imprime "Aluno" no painel, na gaveta do
    cabecalho e no perfil, e por um tempo as telas de equipe e catalogo diziam
    "estudante" - dois nomes para a mesma pessoa, em telas vizinhas. A escolha e
    "aluno", e este teste a mantem.
    """
    fora = []
    for caminho in RAIZ.glob("templates/**/*.html"):
        for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
            if "estudante" not in linha.lower():
                continue
            if any(gancho in linha for gancho in GANCHOS_DE_ESTILO):
                continue
            fora.append(f"{caminho.relative_to(RAIZ)}:{numero}: {linha.strip()[:70]}")
    assert fora == [], "a interface voltou a dizer \"estudante\":\n" + "\n".join(fora)
