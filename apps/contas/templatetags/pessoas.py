"""`{{ nome|iniciais }}` - as duas letras do avatar.

Mora em `contas` porque e o app base: nada depende dele, entao uma tag global
aqui nao cria dependencia nova (CLAUDE.md, Arquitetura). O avatar aparece no
cabecalho de toda pagina e na tela do perfil, e a conta pode nao ter nome ainda -
professor cadastrado so com o e-mail nasce assim.
"""

from django import template

register = template.Library()


@register.filter
def iniciais(nome):
    """Primeira letra do primeiro e do último nome. Devolve "?" se não houver nome."""
    partes = (nome or "").split()
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][0].upper()
    return (partes[0][0] + partes[-1][0]).upper()
