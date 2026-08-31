#!/usr/bin/env bash
# Renderiza os fluxogramas de docs/fluxos/*.mmd para static/img/fluxos/*.svg.
#
# Por que pre-renderizar em vez de carregar o Mermaid no navegador: a biblioteca
# tem 3,2 MB -- 65 vezes o HTMX -- para desenhar quatro diagramas que nunca mudam.
# Este sistema e feito para escolas do interior; mandar isso pelo fio a cada visita
# da pagina "Sobre" e caro pelo que entrega. Em SVG a pagina abre instantanea,
# funciona sem JavaScript e o texto do diagrama continua selecionavel e buscavel.
#
# A fonte da verdade continua sendo o .mmd. Rode este script depois de edita-lo.
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
TRABALHO="$(mktemp -d)"
trap 'rm -rf "$TRABALHO"' EXIT

MERMAID="${MERMAID_JS:-$TRABALHO/mermaid.min.js}"
if [ ! -f "$MERMAID" ]; then
  echo "Baixando o Mermaid (nao vai para o repositorio; so serve para gerar)..."
  curl -sL "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js" -o "$MERMAID"
fi

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
[ -x "$CHROME" ] || { echo "Chrome nao encontrado; defina CHROME=..." >&2; exit 1; }

mkdir -p "$RAIZ/static/img/fluxos"
for fonte in "$RAIZ"/docs/fluxos/*.mmd; do
  nome="$(basename "$fonte" .mmd)"
  pagina="$TRABALHO/$nome.html"
  cp "$MERMAID" "$TRABALHO/mermaid.min.js"
  {
    echo '<!doctype html><meta charset="utf-8"><body><pre class="mermaid">'
    sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g' "$fonte"
    echo '</pre><script src="mermaid.min.js"></script><script>'
    cat <<'JS'
mermaid.initialize({
  startOnLoad: true,
  securityLevel: "strict",
  theme: "base",
  fontFamily: "Inter, system-ui, sans-serif",
  themeVariables: {
    primaryColor: "#e9f1fa", primaryTextColor: "#16202e", primaryBorderColor: "#a8c6e2",
    lineColor: "#5a6675", secondaryColor: "#e4f7f7", tertiaryColor: "#f5f8fb",
    fontSize: "15px",
  },
  // htmlLabels: false e o que torna o SVG valido como arquivo avulso. Com true,
  // o Mermaid desenha os rotulos em HTML dentro de <foreignObject>, e o <br> sai
  // sem fechar: valido em HTML, invalido em XML. Como <img src="*.svg"> e lido em
  // XML estrito, o navegador mostra imagem quebrada sem dizer por que. Com false
  // os rotulos viram <text>/<tspan> de SVG puro -- e o texto segue selecionavel.
  flowchart: {
    curve: "basis", nodeSpacing: 42, rankSpacing: 52,
    useMaxWidth: true, htmlLabels: false,
  },
});
JS
    echo '</script></body>'
  } > "$pagina"

  "$CHROME" --headless=new --disable-gpu --virtual-time-budget=9000 \
    --dump-dom "file://$pagina" 2>/dev/null \
    | python3 "$RAIZ/deploy/extrair-svg.py" > "$RAIZ/static/img/fluxos/$nome.svg"
  echo "  $nome.svg  ($(wc -c < "$RAIZ/static/img/fluxos/$nome.svg" | tr -d ' ') bytes)"
done
echo "Pronto."
