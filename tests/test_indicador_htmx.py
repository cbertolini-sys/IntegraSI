"""Sinal visual de "isto esta trabalhando" nas cinco interacoes HTMX do sistema.

Trocar "tipo de publico" na ficha dispara ate duas requisicoes que substituem
regioes da tela (referencial + etapa, e habilidades por baixo de referencial), e
salvar uma secao do Plano de Ensino manda o texto para o servidor - nenhuma das
cinco tinha indicador nenhum. Em rede boa ninguem percebe; em rede de escola, a
pessoa muda o campo ou aperta salvar, nada acontece por um instante, e ela repete
a acao.

O caso mais sensivel e o de salvar secao: e onde o texto que o aluno escreveu
esta sendo enviado, e e onde a duvida ("salvou ou nao?") custa mais.
"""

from pathlib import Path

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)
CSS = (RAIZ / "static" / "css" / "integrasi.css").read_text(encoding="utf-8")


def test_a_folha_de_estilo_define_o_indicador_do_htmx():
    """`.htmx-indicator` comeca invisivel e aparece quando o ancestral ganha
    `htmx-request` - a convencao que o proprio htmx documenta, escrita aqui com a
    transicao do resto do sistema, e nao a injetada automaticamente por ele."""
    assert ".htmx-indicator" in CSS
    assert ".htmx-request .htmx-indicator" in CSS


def test_a_regiao_trocada_por_htmx_get_esmaece_durante_a_troca():
    """`_referencial.html`, `_etapa.html` e `_habilidades.html` trocam a propria
    regiao (`hx-target="this"` ou o proprio id) e nao declaram `hx-indicator`: o
    htmx poe `htmx-request` na propria regiao por padrao, e esta regra a esmaece
    enquanto a troca esta a caminho, sem acrescentar elemento nenhum a tela."""
    assert '.htmx-request[hx-get]' in CSS


def test_salvar_secao_tem_indicador_proprio():
    """O caso mais sensivel: um `hx-indicator` explicito, apontando para um
    elemento com a classe `.htmx-indicator` que existe no mesmo template."""
    texto = (RAIZ / "templates" / "cursos" / "_secao.html").read_text(encoding="utf-8")
    assert "hx-indicator=" in texto
    assert 'class="htmx-indicator"' in texto or "htmx-indicator" in texto


# --- O indicador tambem precisa existir para quem nao ve a tela ---------------


def test_o_indicador_parado_nao_e_anunciado():
    """`opacity: 0` esconde do olho e NAO tira da arvore de acessibilidade.

    Com so a opacidade, o texto "Salvando…" fica permanentemente exposto: quem
    usa leitor de tela o ouve ao percorrer a secao, mesmo com nada salvando, e
    nunca o ouve no momento em que ele realmente aparece. As duas metades do
    defeito vem da mesma causa.

    `visibility: hidden` remove da arvore; voltando a `visible`, o leitor de tela
    trata como conteudo que entrou na regiao viva e anuncia. A opacidade fica
    para o esmaecimento continuar existindo.
    """
    inicio = CSS.index(".htmx-indicator {")
    parado = CSS[inicio : CSS.index("}", inicio)]
    assert "visibility: hidden" in parado, (
        "com só `opacity: 0` o texto do indicador é anunciado o tempo todo"
    )


def test_o_indicador_em_movimento_volta_para_a_arvore():
    """Guarda separada da de cima: esconder sem voltar deixaria o indicador
    invisivel para sempre a quem usa leitor de tela, que e pior que o defeito
    original."""
    inicio = CSS.index(".htmx-request .htmx-indicator,")
    ativo = CSS[inicio : CSS.index("}", inicio)]
    assert "visibility: visible" in ativo, (
        "o indicador some da árvore de acessibilidade e nunca volta"
    )


def test_o_indicador_de_salvar_secao_e_uma_regiao_viva():
    """Sem `role="status"`, voltar a arvore nao anuncia nada: o leitor de tela
    so fala sozinho sobre regiao que foi declarada viva."""
    texto = (RAIZ / "templates" / "cursos" / "_secao.html").read_text(encoding="utf-8")
    inicio = texto.index('class="htmx-indicator')
    tag = texto[texto.rindex("<span", 0, inicio) : texto.index(">", inicio) + 1]
    assert 'role="status"' in tag, f"o indicador não é região viva: {tag}"
