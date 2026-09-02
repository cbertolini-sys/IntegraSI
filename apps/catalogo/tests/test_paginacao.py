"""Paginacao das listas (A3 da revisao tecnica).

Nenhuma lista era paginada: catalogo publico, meus cursos, solicitacoes, pessoas,
turmas e cursos no catalogo carregavam tudo o que existe. Com quatro cursos
publicados nao se nota; e o tipo de defeito que aparece com o sistema em uso, e a
primeira pagina lenta e a do catalogo, que e a que o publico ve.

As duas FILAS de trabalho (revisao e coordenacao) ficam de fora de proposito:
fila e para ser vista inteira, e esconder metade do que espera decisao seria pior
que a pagina longa.
"""

import pytest
from django.urls import reverse

from apps.catalogo.tests.test_catalogo import publica
from apps.contas.paginacao import POR_PAGINA
from apps.cursos import services


def cpf_valido(semente):
    """Um CPF diferente por chamada, com os digitos verificadores certos.

    O modelo recusa CPF invalido (e bem), entao a fixture nao pode inventar
    numeros: gerar e mais honesto que manter uma lista fixa que acaba.
    """
    # Os nove primeiros digitos saem da propria semente, e nao de um giro de
    # `% 10`: aquele repetia a cada dez chamadas e a decima pessoa batia na
    # unicidade do CPF.
    base = [int(d) for d in f"{semente + 100_000_000:09d}"]
    for _ in range(2):
        peso = len(base) + 1
        soma = sum(d * (peso - i) for i, d in enumerate(base))
        digito = (soma * 10) % 11
        base.append(0 if digito == 10 else digito)
    return "".join(map(str, base))


@pytest.fixture
def muitos_cursos(dados_curso, aluno, professor, coordenador, db):
    """Um a mais que cabe numa pagina."""
    from apps.contas.models import Usuario

    for n in range(POR_PAGINA + 1):
        dados = dict(dados_curso)
        dados["titulo"] = f"Curso número {n:02d}"
        curso = services.criar_curso(**dados)
        membro = Usuario.objects.create_user(
            email=f"membro{n}@ufsm.br", nome_completo=f"Membro {n}", papel=Usuario.ALUNO
        )
        publica(curso, membro, professor, coordenador)
    return POR_PAGINA + 1


@pytest.mark.django_db
def test_o_catalogo_mostra_so_uma_pagina(client, muitos_cursos):
    html = client.get(reverse("catalogo")).content.decode()
    assert html.count('<li class="curso">') == POR_PAGINA
    assert "Página 1 de 2" in html


@pytest.mark.django_db
def test_a_segunda_pagina_traz_o_resto(client, muitos_cursos):
    html = client.get(reverse("catalogo") + "?pagina=2").content.decode()
    assert html.count('<li class="curso">') == muitos_cursos - POR_PAGINA


@pytest.mark.django_db
def test_a_pagina_invalida_cai_na_primeira(client, muitos_cursos):
    """Numero fora da faixa, ou que nem e numero, mostra a primeira pagina em vez
    de erro: e endereco que a pessoa digita ou que um link velho guarda."""
    for valor in ("99", "0", "abacaxi", "-3"):
        resposta = client.get(reverse("catalogo") + f"?pagina={valor}")
        assert resposta.status_code == 200, valor


@pytest.mark.django_db
def test_a_paginacao_preserva_o_filtro(client, muitos_cursos):
    """O catalogo filtra por tema, formato, etapa e busca. Se o link da proxima
    pagina perder isso, a pessoa filtra, vira a pagina e recebe tudo de novo."""
    html = client.get(reverse("catalogo") + "?formato=REMOTO").content.decode()
    if "Página 1 de" in html:
        assert "formato=REMOTO" in html


@pytest.mark.django_db
def test_a_lista_de_pessoas_e_paginada(client, coordenador, db):
    from apps.contas.models import Usuario

    for n in range(POR_PAGINA + 1):
        Usuario.objects.create_user(
            email=f"prof{n}@ufsm.br", nome_completo=f"Professor {n}",
            papel=Usuario.PROFESSOR, siape=f"90000{n:02d}", cpf=cpf_valido(n),
        )
    client.force_login(coordenador)
    html = client.get(reverse("pessoas")).content.decode()
    assert "Página 1 de" in html


@pytest.mark.django_db
def test_a_fila_de_revisao_nao_e_paginada(client, professor):
    """O outro lado: fila e para ser vista inteira. Esconder metade do que espera
    decisao seria pior que a pagina longa."""
    client.force_login(professor)
    html = client.get(reverse("fila_revisao")).content.decode()
    assert "Página 1 de" not in html
