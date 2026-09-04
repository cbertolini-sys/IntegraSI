"""A dependência entre apps é de mão única (A1 da revisão técnica).

A CLAUDE.md dizia isso em prosa e o código não cumpria: o painel morava em
`contas`, o app base, e precisava contar cursos, solicitações e turmas. Resultado,
três ciclos - `contas` importava `cursos`, `catalogo` e `turmas`, e os três
importavam `contas` de volta.

Ciclo entre apps não quebra nada hoje (o Python resolve, e os importes adiados
contornam o resto). O que ele quebra é a possibilidade de ler, testar ou mover um
app sozinho, e isso só se descobre no dia em que alguém tenta.
"""

import re
import subprocess
from pathlib import Path

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)

# O que cada app pode conhecer. As camadas vão de cima para baixo: `contas` e os
# vocabulários não conhecem ninguém; `cursos` é o núcleo; `catalogo` e `turmas`
# leem o núcleo; `painel` existe justamente para poder olhar todos.
PERMITIDO = {
    # `notificacoes` e folha (nao importa ninguem), entao todos podem usa-la:
    # `contas` enfileira o convite de primeiro acesso por ali.
    "contas": {"notificacoes"},
    "referenciais": set(),
    "notificacoes": set(),
    "cursos": {"contas", "referenciais", "notificacoes"},
    "catalogo": {"contas", "cursos", "notificacoes", "referenciais"},
    "turmas": {"contas", "cursos", "catalogo", "notificacoes"},
    "painel": {"contas", "cursos", "catalogo", "turmas", "notificacoes"},
}


def grafo_de_dependencias():
    """Quem importa quem, lido do código de produção.

    Testes ficam de fora: um teste de `contas` pode montar um cenário de curso
    sem que isso torne `contas` dependente de `cursos` em produção. Migrações
    também: elas citam apps por string, não por importe.
    """
    arquivos = subprocess.run(
        ["git", "ls-files", "apps"], capture_output=True, text=True, cwd=RAIZ, check=True
    ).stdout.split()
    grafo = {app: set() for app in PERMITIDO}
    for caminho in arquivos:
        if not caminho.endswith(".py") or "/tests/" in caminho or "/migrations/" in caminho:
            continue
        origem = caminho.split("/")[1]
        texto = (RAIZ / caminho).read_text(encoding="utf-8")
        for achado in re.finditer(r"from apps\.(\w+)|import apps\.(\w+)", texto):
            destino = achado.group(1) or achado.group(2)
            if destino != origem:
                grafo.setdefault(origem, set()).add(destino)
    return grafo


def test_nenhum_app_conhece_mais_do_que_pode():
    fora = []
    for app, destinos in grafo_de_dependencias().items():
        for destino in sorted(destinos - PERMITIDO.get(app, set())):
            fora.append(f"{app} importa {destino}")
    assert fora == [], (
        "dependência fora das camadas:\n" + "\n".join(fora)
        + "\n\nSe a dependência for legítima, mova o código para a camada certa "
        "antes de abrir PERMITIDO."
    )


def test_nao_ha_ciclo_entre_apps():
    """O que a lista acima permite tem que ser aciclico de verdade.

    Sem este teste, bastaria alguém acrescentar duas linhas em `PERMITIDO` e o
    ciclo voltaria com a bênção do arquivo que existe para impedi-lo.
    """
    grafo = grafo_de_dependencias()
    ciclos = sorted(
        {tuple(sorted((a, b))) for a, destinos in grafo.items() for b in destinos if a in grafo.get(b, set())}
    )
    assert ciclos == [], "ciclo entre apps: " + ", ".join(f"{a} <-> {b}" for a, b in ciclos)


def test_a_lista_de_camadas_cobre_os_apps_instalados():
    """App novo esquecido aqui nunca seria conferido."""
    instalados = {
        nome.split(".")[-1] for nome in settings.INSTALLED_APPS if nome.startswith("apps.")
    }
    assert instalados == set(PERMITIDO), (
        f"só em INSTALLED_APPS: {instalados - set(PERMITIDO)}; "
        f"só em PERMITIDO: {set(PERMITIDO) - instalados}"
    )
