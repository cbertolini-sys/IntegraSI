"""`{% estatico %}` - como `{% static %}`, mas com a versão do arquivo na URL.

Existe porque o servidor de desenvolvimento manda `Last-Modified` sem
`Cache-Control`, e o navegador passa a cachear por heurística: uma folha de
estilo alterada continua servindo a versão velha até alguém forçar a recarga.
Custou uma sessão inteira de confusão -- a página parecia quebrada e o CSS estava
correto no servidor.

Em produção, `collectstatic` com `ManifestStaticFilesStorage` já põe o hash no
nome do arquivo; aqui o parâmetro é inofensivo e o mecanismo continua o mesmo em
ambos os ambientes, o que é o ponto: não ter um comportamento em dev e outro no
ar.

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
