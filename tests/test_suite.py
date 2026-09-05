"""A suite conferindo a si mesma.

Um teste que nao roda e pior que um teste que falta: o nome dele esta no
arquivo, a regra parece coberta, e a revisao passa por cima. A disciplina de
mutacao do projeto ("apague a guarda e veja o teste falhar") nao pega este
caso, porque o teste que sumiu nao falharia de qualquer jeito.
"""

import ast
from collections import Counter
from pathlib import Path

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)


def arquivos_de_teste():
    """Todo `test_*.py` do repositorio, nos apps e na raiz."""
    return sorted(
        caminho
        for caminho in RAIZ.rglob("test_*.py")
        if ".venv" not in caminho.parts and "node_modules" not in caminho.parts
    )


def nomes_repetidos(caminho):
    """Funcoes de teste declaradas mais de uma vez no mesmo modulo."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    nomes = [
        no.name
        for no in arvore.body
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
        and no.name.startswith("test_")
    ]
    return [nome for nome, quantas in Counter(nomes).items() if quantas > 1]


def test_nenhum_teste_e_declarado_duas_vezes_no_mesmo_modulo():
    """Python substitui a primeira definicao pela segunda ao carregar o arquivo,
    sem aviso nenhum: o pytest coleta UM teste onde a leitura sugere dois.

    Aconteceu com `test_enfileirar_ignora_destinatario_vazio`, declarado nas
    linhas 28 e 317 de `apps/notificacoes/tests/test_fila.py`. Ali as duas
    versoes afirmavam a mesma coisa, entao nenhuma regra ficou desprotegida - o
    proximo caso pode nao ter essa sorte.
    """
    repetidos = [
        f"{caminho.relative_to(RAIZ)}: {', '.join(nomes)}"
        for caminho in arquivos_de_teste()
        if (nomes := nomes_repetidos(caminho))
    ]
    assert repetidos == [], (
        "teste declarado duas vezes (a primeira versão nunca roda):\n"
        + "\n".join(repetidos)
    )


def test_a_varredura_enxerga_os_arquivos_de_teste():
    """Um glob errado devolveria lista vazia e o teste acima ficaria verde para
    sempre. Confere que a varredura acha os arquivos E que le funcoes dentro
    deles: achar o arquivo e nao achar `def test_` seria o mesmo silencio."""
    arquivos = arquivos_de_teste()
    assert len(arquivos) > 30, f"a varredura achou só {len(arquivos)} arquivos"

    total = sum(
        1
        for caminho in arquivos
        for no in ast.parse(caminho.read_text(encoding="utf-8")).body
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
        and no.name.startswith("test_")
    )
    assert total > 200, f"a varredura achou só {total} funções de teste"
