from django import template

from apps.referenciais.choices import ETAPAS_REFERENCIAL

register = template.Library()
NOMES = dict(ETAPAS_REFERENCIAL)


@register.filter
def etapa_legivel(codigo):
    """Traduz o codigo da etapa do referencial para o nome que a pessoa le."""
    return NOMES.get(codigo, codigo)
