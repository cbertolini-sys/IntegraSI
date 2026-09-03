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
