"""Paginacao das listas, num lugar so.

Mora em `contas` pelo mesmo motivo de `rede.py`: quatro apps precisam dela, e
`contas` e o app base, entao todos importam daqui sem inverter a dependencia de
mao unica do projeto.

O tamanho da pagina e um numero so para todas as telas de proposito: listas com
paginas de tamanhos diferentes fazem a pessoa perder a nocao de quanto ja viu.
"""

from django.core.paginator import Paginator

POR_PAGINA = 12


def paginar(request, itens):
    """A pagina pedida, ou a primeira quando o numero nao faz sentido.

    `get_page` ja trata numero fora da faixa, texto e ausencia devolvendo a
    primeira (ou a ultima) pagina em vez de levantar excecao: endereco de pagina
    e coisa que a pessoa digita e que link velho guarda, e uma lista nao pode
    virar erro por causa disso.
    """
    return Paginator(itens, POR_PAGINA).get_page(request.GET.get("pagina"))
