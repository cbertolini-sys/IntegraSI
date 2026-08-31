"""Recorta o SVG que o Mermaid gerou dentro do DOM despejado pelo Chrome.

Existe como arquivo, e nao embutido no shell: o padrao precisa de aspas simples,
e elas fechariam a string do `python3 -c` do gerar-fluxogramas.sh.
"""

import re
import sys

html = sys.stdin.read()
achado = re.search(r"(<svg\b.*?</svg>)", html, re.S)
if not achado:
    sys.exit("O Mermaid nao gerou SVG -- confira a sintaxe do .mmd")

svg = achado.group(1)
# O Mermaid grava uma largura fixa em pixels; sem ela o SVG flui na coluna e o
# `max-width` do CSS manda. A altura e o viewBox ficam, senao ele achata.
svg = re.sub(r'\swidth="[^"]*"', "", svg, count=1)
# NAO acrescente role aqui: o Mermaid ja escreve `role="graphics-document
# document"` no <svg>, e um segundo atributo `role` torna o XML invalido. Como
# `<img src="*.svg">` e parseado em XML estrito, o navegador mostra imagem
# quebrada -- silenciosamente, sem erro no console. A funcao acessivel do
# diagrama vem do `alt` da <img> e da legenda ao lado, na propria pagina.
sys.stdout.write(svg)
