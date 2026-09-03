"""`{% estatico %}` - como `{% static %}`, mas com a versão do arquivo na URL.

Existe porque o servidor de desenvolvimento manda `Last-Modified` sem
`Cache-Control`, e o navegador passa a cachear por heurística: uma folha de
estilo alterada continua servindo a versão velha até alguém forçar a recarga.
Custou uma sessão inteira de confusão -- a página parecia quebrada e o CSS estava
correto no servidor.

Vale em produção também, e é lá que ele é o único mecanismo: o projeto **não**
usa `ManifestStaticFilesStorage`. Habilitá-lo derruba o `collectstatic`, e o
motivo é concreto - quatro arquivos vendorizados (`quill.snow.css`,
`quill.min.js`, `tippy.min.js`, `popper.min.js`) terminam com um
`sourceMappingURL` apontando para um `.map` que não vendorizamos, e o
`ManifestStaticFilesStorage` reescreve essas referências e falha em quem não
acha. Sairia caro pelo motivo errado: ou modificar biblioteca de terceiro, ou
carregar quatro mapas de código que produção nenhuma lê.

Então o `?v=` daqui é o que quebra o cache nos dois ambientes, que era o ponto:
não ter um comportamento em desenvolvimento e outro no ar. O nginx serve
`/static/` com `expires 30d` (deploy/nginx.conf) contando com ele.

Mora em `contas` porque é o app base -- nada depende dele, então uma tag global
aqui não cria dependência nova (CLAUDE.md, Arquitetura).
"""

from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def estatico(caminho):
    url = static(caminho)
    achado = finders.find(caminho)
    if not achado:
        # Em produção o arquivo pode estar só no STATIC_ROOT, fora do alcance dos
        # finders. Sem versão é melhor que sem folha de estilo.
        return url
    try:
        versao = int(Path(achado).stat().st_mtime)
    except OSError:
        return url
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}v={versao}"
