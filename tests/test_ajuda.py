"""Os tooltips de ajuda dos campos.

A explicacao mora no `help_text` do formulario, em Python, e nao no template: e la
que ela fica junto da definicao do campo e onde este arquivo consegue exigir que
todo campo tenha uma. E o que faz "formulario novo ganha tooltip" ser uma regra
cobrada, e nao uma lembranca.
"""

import importlib
import re
from pathlib import Path

import pytest
from django import forms
from django.apps import apps as registro_de_apps
from django.conf import settings

RAIZ = Path(settings.BASE_DIR)

# Formularios do Django Admin de contas: o Admin desenha a ajuda do jeito dele, e
# esta tela nao carrega o nosso JS. Ficam de fora da exigencia, e a lista e curta
# de proposito - crescer aqui e sinal de que alguem esta fugindo da regra.
FORA = {"UsuarioChangeForm", "UsuarioCreationForm", "CamposComPontuacaoMixin"}


def formularios():
    """Todo formulario declarado nos apps do projeto."""
    achados = []
    for app in registro_de_apps.get_app_configs():
        if not app.name.startswith("apps."):
            continue
        try:
            modulo = importlib.import_module(f"{app.name}.forms")
        except ModuleNotFoundError:
            continue
        for nome in dir(modulo):
            objeto = getattr(modulo, nome)
            if (
                isinstance(objeto, type)
                and issubclass(objeto, forms.BaseForm)
                and objeto.__module__ == modulo.__name__
                and nome not in FORA
            ):
                achados.append((f"{app.label}.{nome}", objeto))
    return achados


def test_todo_campo_visivel_explica_como_preencher():
    """Campo sem ajuda e campo que a equipe adivinha.

    Campo escondido fica de fora: o `confirmacao` do formulario publico e uma
    armadilha para robo, e um balao sobre ele seria instrucao para ninguem.
    """
    mudos = []
    for nome, Formulario in formularios():
        for campo, definicao in Formulario().fields.items():
            if isinstance(definicao.widget, forms.HiddenInput):
                continue
            if not definicao.help_text:
                mudos.append(f"{nome}.{campo}")
    assert mudos == [], "campos sem explicação:\n" + "\n".join(mudos)


def test_a_varredura_de_formularios_acha_alguma_coisa():
    """Um import errado devolveria lista vazia e o teste acima ficaria verde para
    sempre, com o projeto inteiro sem ajuda nenhuma."""
    nomes = {nome for nome, _ in formularios()}
    assert len(nomes) >= 5
    assert any("FichaCursoForm" in n for n in nomes)


def test_a_ajuda_cabe_num_balao():
    """Texto longo demais vira parede de texto sobre o campo. O limite e generoso;
    quem precisar de mais que isso esta escrevendo documentacao, nao ajuda."""
    compridos = [
        f"{nome}.{campo} ({len(d.help_text)} caracteres)"
        for nome, Formulario in formularios()
        for campo, d in Formulario().fields.items()
        if d.help_text and len(str(d.help_text)) > 220
    ]
    assert compridos == [], "ajuda longa demais:\n" + "\n".join(compridos)


def test_tippy_e_popper_estao_no_repositorio():
    """O projeto vendoriza tudo e nao carrega CDN: sem rede, ou com o CDN fora do
    ar, a tela precisa continuar funcionando."""
    for arquivo in ("static/js/tippy.min.js", "static/js/popper.min.js", "static/css/tippy.css"):
        caminho = RAIZ / arquivo
        assert caminho.exists(), arquivo
        assert caminho.stat().st_size > 1000, arquivo


def test_nenhum_template_carrega_biblioteca_de_fora():
    """A regra vale para o repositorio todo, e nao so para o Tippy."""
    fora = []
    for caminho in RAIZ.glob("templates/**/*.html"):
        texto = caminho.read_text(encoding="utf-8")
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if re.search(r'(src|href)="https?://(?!www\.ufsm\.br)', linha):
                fora.append(f"{caminho.relative_to(RAIZ)}:{numero}")
    assert fora == [], "biblioteca carregada de fora em:\n" + "\n".join(fora)


# --- O editor e o sanitizador precisam concordar ------------------------------

# Formatos do Quill cujas tags ou atributos `Secao.save()` apaga. Oferecer um
# deles na barra faria a pessoa formatar, salvar, e ver a formatacao sumir sem
# explicacao nenhuma - o pior tipo de defeito, porque parece que o sistema perdeu
# o trabalho dela.
FORMATOS_QUE_O_SANITIZADOR_APAGA = (
    "image", "video", "color", "background", "align",
    "code-block", "script", "size", "font", "table", "formula", "indent",
)


def test_a_barra_do_editor_so_oferece_o_que_sobrevive_ao_salvar():
    """A lista de tags permitidas e a barra do editor sao dois arquivos, um em
    Python e outro em JavaScript, e nada no sistema os liga. Este teste liga."""
    editor = (RAIZ / "static" / "js" / "editor.js").read_text(encoding="utf-8")
    inicio = editor.index("var BARRA")
    barra = editor[inicio:editor.index("];", inicio)]
    oferecidos = [f for f in FORMATOS_QUE_O_SANITIZADOR_APAGA if f"'{f}'" in barra or f"{f}:" in barra]
    assert oferecidos == [], (
        "a barra oferece formatos que o sanitizador apaga: " + ", ".join(oferecidos)
    )


def test_o_que_a_barra_oferece_sobrevive_ao_nh3():
    """Ponta a ponta com o sanitizador de verdade, e nao com uma lista de tags
    copiada: negrito, italico, listas, citacao, link e titulo precisam chegar
    inteiros ao banco."""
    import nh3

    from apps.cursos.models.producao import TAGS_PERMITIDAS

    html = (
        "<h2>Título</h2><h3>Subtítulo</h3><p><strong>negrito</strong> "
        "<em>itálico</em> <u>sublinhado</u></p>"
        "<ol><li>um</li></ol><ul><li>dois</li></ul>"
        "<blockquote>citação</blockquote>"
        '<p><a href="https://ufsm.br">link</a></p>'
    )
    limpo = nh3.clean(html, tags=TAGS_PERMITIDAS)
    for marca in ("<h2>", "<h3>", "<strong>", "<em>", "<u>", "<ol>", "<ul>", "<li>",
                  "<blockquote>", "<a "):
        assert marca in limpo, f"{marca} não sobreviveu ao sanitizador"


def test_o_editor_nao_rouba_o_foco_ao_abrir_a_pagina():
    """Abrir um entregável não pode jogar o cursor dentro de um campo.

    `dangerouslyPasteHTML` faz `setContents` e, logo depois, `setSelection(0)` -
    está escrito assim no próprio bundle vendorizado. `setSelection` foca o
    editor, então a página abria com o cursor na descrição (e, no Plano de Ensino,
    na última das sete seções, depois de rolar até ela).

    `setContents` sozinho não mexe na seleção, e é o que o editor.js usa. Este
    teste é estático porque `editor.js` precisa de DOM para rodar: o harness de
    node que existe é do `upload.js`, que não depende de nenhum.
    """
    fonte = (RAIZ / "static" / "js" / "editor.js").read_text(encoding="utf-8")
    # Sem as linhas de comentario: a regra e sobre o codigo, e o comentario que
    # explica a decisao precisa poder citar a API pelo nome. A primeira versao
    # deste teste reprovava por causa do proprio comentario que ele motivou.
    codigo = "\n".join(
        linha for linha in fonte.splitlines() if not linha.strip().startswith("//")
    )
    assert "dangerouslyPasteHTML" not in codigo, (
        "esta API foca o editor; use setContents com o delta de clipboard.convert"
    )
    assert "setContents" in codigo


def test_a_razao_de_evitar_o_dangerously_paste_continua_valendo():
    """Prende o PORQUÊ, e não só o quê.

    Sem isto, o teste acima vira regra sem motivo no dia em que uma versão nova do
    Quill parar de mexer na seleção: ninguém saberia que dá para voltar atrás, e a
    proibição sobreviveria à razão dela.
    """
    bundle = (RAIZ / "static" / "js" / "quill.min.js").read_text(encoding="utf-8")
    inicio = bundle.index("dangerouslyPasteHTML")
    assert "setSelection" in bundle[inicio : inicio + 400], (
        "o Quill vendorizado mudou e talvez não foque mais; reveja "
        "test_o_editor_nao_rouba_o_foco_ao_abrir_a_pagina"
    )


def test_nenhum_campo_obrigatorio_se_diz_opcional():
    """A ajuda nao pode contradizer o asterisco.

    A descricao dizia "Opcional." e ganhou o asterisco de obrigatorio na mesma
    tela: a pessoa lia as duas coisas, uma ao lado da outra, e nenhuma das duas
    ficava confiavel. Achado olhando a tela renderizada, com a suite verde.
    """
    mentirosos = []
    for nome, Formulario in formularios():
        formulario = Formulario()
        for campo, definicao in formulario.fields.items():
            if definicao.required and "opcional" in str(definicao.help_text).lower():
                mentirosos.append(f"{nome}.{campo}")
    assert mentirosos == [], (
        "campo obrigatório cuja ajuda diz que é opcional:\n" + "\n".join(mentirosos)
    )
