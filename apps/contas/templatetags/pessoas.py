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


@register.filter
def como_pessoa(pessoa):
    """O nome, ou o e-mail quando ainda nao ha nome.

    So repassa a `Usuario.identificacao`: a regra mora no modelo (usada tambem
    pelas mensagens de sucesso em contas/views.py e cursos/views/professor.py), e
    este filtro so a deixa alcancavel de dentro do template.
    """
    if pessoa is None:
        return ""
    return pessoa.identificacao
