"""Os tooltips de ajuda dos campos.

A explicacao mora no `help_text` do formulario, em Python, e nao no template: e la
que ela fica junto da definicao do campo e onde este arquivo consegue exigir que
todo campo tenha uma. E o que faz "formulario novo ganha tooltip" ser uma regra
cobrada, e nao uma lembranca.
"""

import importlib
import re
from pathlib import Path

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


# --- Campo escrito a mao em template, fora da varredura de formularios --------

# A varredura de `formularios()` so alcanca `apps.*.forms`: um <input>/<select>/
# <textarea> escrito direto no template, sem form.py nenhum por tras, nunca passa
# por ela. Cada entrada aqui tem um motivo de verdade, e nao "ainda nao migrado" -
# um motivo assim envelheceria mal e ninguem saberia se ainda vale.
ISENTOS_DO_TEMPLATE = {
    # A primeira tela que qualquer pessoa ve, antes de qualquer outra ajuda do
    # sistema fazer sentido. E-mail e senha de login sao os dois campos mais
    # universalmente entendidos da web; um balao aqui seria ruido no momento em
    # que a pessoa menos precisa dele.
    ("registration/login.html", "username"),
    ("registration/login.html", "password"),
    # Barra de busca do catalogo publico: cinco campos compactos numa linha so
    # (a busca livre, com `placeholder` dizendo o que digitar, e quatro filtros,
    # cada um com "Qualquer <coisa>" como primeira opcao - a propria lista de
    # opcoes explica o campo). E um padrao de busca facetada, nao um formulario
    # de dados, e nao tem o espaco vertical de `.campo` para um botao de ajuda
    # sem quebrar o layout de uma linha so.
    ("catalogo/lista.html", "q"),
    ("catalogo/lista.html", "etapa"),
    ("catalogo/lista.html", "tema"),
    ("catalogo/lista.html", "formato"),
    ("catalogo/lista.html", "referencial"),
}

# Campo escrito a mao cujo POST passa por um form.py que o template nao
# renderiza direto - o Quill precisa do <textarea> de verdade por baixo, entao
# `_secao.html` escreve a tag a mao, mas `salvar_secao` valida com
# `SecaoForm(request.POST, instance=secao)`, que ja tem help_text (visto no
# teste de cima). Lista explicita, e nao um match automatico por nome de campo:
# um match automatico ja criou um falso negativo aqui (SolicitacaoForm.nome e
# SolicitacaoForm.email, de uma tela sem nenhuma relacao, escondiam a falta de
# ajuda de cursos/equipe.html na primeira versao deste teste).
COBERTO_POR_FORM_QUE_O_TEMPLATE_NAO_RENDERIZA = {
    ("cursos/_secao.html", "conteudo"),
}

_CAMPO_SEM_AJUDA = re.compile(
    r'<(?:input|select|textarea)\b(?![^>]*type="hidden")[^>]*\bname="([a-z_]+)"'
)


def test_todo_campo_escrito_a_mao_tambem_tem_balao():
    """A mesma exigencia do teste acima, para quem nao passa pela varredura de
    formularios.py: um <input>/<select>/<textarea> escrito direto no template.

    So reprova campo que nao tem ajuda NENHUMA: nem um gatilho companheiro no
    mesmo <form>, nem estar na lista explicita de campos que um form.py ja cobre.
    Os caminhos todos contam porque todos colocam explicacao na tela; e a tela,
    nao o mecanismo, que este arquivo protege.

    O gatilho companheiro conta de duas formas: escrito a mao (`data-ajuda=`) ou
    incluido pelo `_gatilho_ajuda.html`. Sem a segunda, este teste reprovaria
    exatamente a correcao que tirou a ajuda de dentro do `data-ajuda` solto e a
    ligou por `aria-describedby` - punindo a melhoria por ela ter mudado o
    mecanismo que o teste media, e nao a tela que ele protege.
    """
    sem_ajuda = []
    for caminho in RAIZ.glob("templates/**/*.html"):
        relativo = str(caminho.relative_to(RAIZ / "templates"))
        texto = caminho.read_text(encoding="utf-8")
        for bloco in re.findall(r"<form\b.*?</form>", texto, re.S):
            tem_ajuda_no_bloco = (
                "data-ajuda=" in bloco or "_gatilho_ajuda.html" in bloco
            )
            for campo in _CAMPO_SEM_AJUDA.findall(bloco):
                if (relativo, campo) in ISENTOS_DO_TEMPLATE:
                    continue
                if (relativo, campo) in COBERTO_POR_FORM_QUE_O_TEMPLATE_NAO_RENDERIZA:
                    continue
                if not tem_ajuda_no_bloco:
                    sem_ajuda.append(f"{relativo}:{campo}")
    assert sem_ajuda == [], "campo escrito a mao sem ajuda:\n" + "\n".join(sem_ajuda)


def test_a_varredura_de_campo_a_mao_acha_alguma_coisa():
    """Um seletor errado devolveria zero blocos e o teste acima ficaria verde
    para sempre, com o repositorio inteiro sem `<form>` nenhum encontrado."""
    total = sum(
        len(re.findall(r"<form\b.*?</form>", caminho.read_text(encoding="utf-8"), re.S))
        for caminho in RAIZ.glob("templates/**/*.html")
    )
    assert total >= 10


def test_a_lista_de_isentos_continua_justificada():
    """Os sete campos isentos precisam continuar sendo os que os comentarios
    acima explicam - uma oitava entrada nova sem revisar este teste seria a lista
    crescendo em silencio pelo caminho mais facil."""
    assert ISENTOS_DO_TEMPLATE == {
        ("registration/login.html", "username"),
        ("registration/login.html", "password"),
        ("catalogo/lista.html", "q"),
        ("catalogo/lista.html", "etapa"),
        ("catalogo/lista.html", "tema"),
        ("catalogo/lista.html", "formato"),
        ("catalogo/lista.html", "referencial"),
    }
    assert COBERTO_POR_FORM_QUE_O_TEMPLATE_NAO_RENDERIZA == {
        ("cursos/_secao.html", "conteudo"),
    }


# --- O gatilho de ajuda precisa alcancar quem nao usa mouse -------------------

# `cursos/_campo.html` e o unico gatilho que NAO carrega o proprio
# `aria-describedby`, e por um motivo de verdade: ali existe um campo de
# formulario, e o Django escreve `aria-describedby="<id>_helptext"` NO CAMPO
# sempre que ha help_text. O `span.helptext.visualmente-oculto` do template e o
# alvo dessa referencia, e o comentario no proprio arquivo explica isso. Um
# regex sobre o template nao enxerga atributo que so nasce ao renderizar, entao
# a isencao precisa ser explicita - e uma so.
GATILHO_QUE_O_DJANGO_JA_DESCREVE = {"cursos/_campo.html"}

_GATILHO = re.compile(r"<button\b[^>]*\bdata-ajuda=[^>]*>", re.S)
_DESCREVE = re.compile(r'aria-describedby="([^"]+)"')
_IDS = re.compile(r'\bid="([^"]+)"')


def test_todo_gatilho_de_ajuda_aponta_para_um_texto_que_existe():
    """A explicacao precisa existir como elemento, e nao so como `data-ajuda`.

    Um atributo `data-*` nao entra na arvore de acessibilidade: leitor de tela
    nenhum o expoe. Com `tabindex="-1"` junto, como estava em seis gatilhos
    escritos a mao, a ajuda sobrava apenas para quem usa mouse e enxerga - entre
    elas a das telas de decisao do professor e da coordenacao, que explicam o que
    fica registrado no historico.

    O `aria-label` que esses botoes ja tinham nao resolve: ele nomeia o BOTAO
    ("O que escrever no comentario"), e nao diz o que o balao diria.
    """
    soltos = []
    for caminho in sorted(RAIZ.glob("templates/**/*.html")):
        relativo = str(caminho.relative_to(RAIZ / "templates"))
        if relativo in GATILHO_QUE_O_DJANGO_JA_DESCREVE:
            continue
        texto = caminho.read_text(encoding="utf-8")
        ids = set(_IDS.findall(texto))
        for gatilho in _GATILHO.findall(texto):
            alvo = _DESCREVE.search(gatilho)
            if not alvo:
                soltos.append(f"{relativo}: gatilho sem aria-describedby")
            elif alvo.group(1) not in ids:
                soltos.append(f"{relativo}: aria-describedby={alvo.group(1)} não existe")
    assert soltos == [], (
        "ajuda que não chega a leitor de tela nem a teclado:\n" + "\n".join(soltos)
    )


def test_a_varredura_de_gatilhos_acha_alguma_coisa():
    """Um regex errado devolveria lista vazia e o teste acima ficaria verde para
    sempre, com o repositorio inteiro voltando ao `data-ajuda` solto."""
    achados = {
        str(caminho.relative_to(RAIZ / "templates"))
        for caminho in RAIZ.glob("templates/**/*.html")
        if _GATILHO.search(caminho.read_text(encoding="utf-8"))
    }
    assert "cursos/_campo.html" in achados, "o gatilho do campo sumiu da varredura"
    assert "_gatilho_ajuda.html" in achados, "o gatilho fora de formulário sumiu"


def test_todo_include_do_gatilho_passa_texto_id_e_rotulo():
    """O parcial monta o `span` a partir de `texto` e o liga pelo `id`.

    Um include sem `texto` desenha span vazio e o `aria-describedby` passa a
    apontar para o nada, que e o mesmo defeito de antes com outra roupa. Sem
    `id`, dois gatilhos na mesma tela colidiriam no mesmo alvo (acontece em
    `analisar_curso.html` e em `curso.html`, que tem dois cada).
    """
    incompletos = []
    for caminho in sorted(RAIZ.glob("templates/**/*.html")):
        relativo = str(caminho.relative_to(RAIZ / "templates"))
        texto = caminho.read_text(encoding="utf-8")
        for include in re.findall(
            r'{%\s*include\s+"_gatilho_ajuda\.html".*?%}', texto, re.S
        ):
            faltando = [a for a in ("texto=", "id=", "rotulo=") if a not in include]
            if faltando:
                incompletos.append(f"{relativo}: falta {', '.join(faltando)}")
    assert incompletos == [], "include incompleto:\n" + "\n".join(incompletos)


def test_a_isencao_do_gatilho_do_campo_continua_justificada():
    """Uma segunda isencao seria a lista crescendo pelo caminho mais facil: quem
    escrever um gatilho novo sem `aria-describedby` conserta o gatilho, e nao
    esta lista."""
    assert GATILHO_QUE_O_DJANGO_JA_DESCREVE == {"cursos/_campo.html"}
