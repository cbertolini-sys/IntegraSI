"""A transcricao da BNCC, conferida contra numeros lidos do documento.

Dado ausente nao levanta excecao: um CSV pela metade importa limpo, a tela mostra
menos habilidades e ninguem percebe. Os numeros abaixo foram contados no
Complemento a BNCC (Resolucao CNE/CEB no 1/2022), nao no arquivo, e e isso que faz
deles um teste.
"""

import csv
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

CSV = Path(settings.BASE_DIR) / "docs" / "dados" / "bncc_computacao_habilidades.csv"

POR_ETAPA = {
    "EI": 11, "EF01": 7, "EF02": 6, "EF03": 9, "EF04": 8, "EF05": 11,
    "EF06": 10, "EF07": 11, "EF08": 11, "EF09": 10, "EM": 26,
}
TOTAL = 120


def linhas():
    with CSV.open(encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def test_o_csv_tem_a_contagem_do_documento():
    contagem = {}
    for linha in linhas():
        contagem[linha["etapa"]] = contagem.get(linha["etapa"], 0) + 1
    assert contagem == POR_ETAPA


def test_o_csv_tem_o_total_do_documento():
    assert len(linhas()) == TOTAL


def test_nenhum_codigo_repetido():
    codigos = [linha["codigo"] for linha in linhas()]
    assert len(set(codigos)) == len(codigos)


def test_nenhuma_descricao_vazia():
    """Codigo sem descricao passaria pela contagem e apareceria em branco na tela."""
    vazias = [linha["codigo"] for linha in linhas() if not (linha["descricao"] or "").strip()]
    assert vazias == []


def test_a_descricao_nao_repete_o_codigo():
    """O codigo ja e a primeira coluna; repeti-lo no texto sairia duplicado na tela."""
    com_codigo = [l["codigo"] for l in linhas() if l["descricao"].lstrip().startswith("(")]
    assert com_codigo == []


def test_codigo_do_quinto_ano_normalizado():
    """O PDF imprime (EF05CO011), com tres digitos. A divergencia esta registrada
    em docs/dados/README.md; este teste impede que ela volte em silencio."""
    codigos = {linha["codigo"] for linha in linhas()}
    assert "EF05CO11" in codigos
    assert "EF05CO011" not in codigos


def test_blocos_consolidados_ficaram_de_fora():
    """Decisao registrada na spec 15: EF15CO e EF69CO reagrupam o mesmo conteudo
    com outro codigo, e importar os dois listaria cada habilidade duas vezes."""
    codigos = {linha["codigo"] for linha in linhas()}
    assert not [c for c in codigos if c.startswith(("EF15CO", "EF69CO"))]


@pytest.mark.django_db
def test_importacao_carrega_tudo_e_agrupa():
    """Ponta a ponta: a fixture mais o CSV precisam bastar. Se uma categoria do
    CSV nao existir na fixture, o comando recusa e este teste acusa."""
    from apps.referenciais.models import Competencia, Referencial

    call_command("loaddata", "bncc_computacao", verbosity=0)
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(CSV), verbosity=0)

    bncc = Referencial.objects.get(sigla="BNCC-COMP")
    assert bncc.competencias.count() == TOTAL
    assert Competencia.objects.filter(referencial=bncc, etapa="EM").count() == 26
    # O Medio pendura em competencia especifica, nao em eixo (spec 4.2).
    eixos_no_medio = set(
        Competencia.objects.filter(referencial=bncc, etapa="EM").values_list(
            "categoria__nome", flat=True
        )
    )
    assert "Pensamento Computacional" not in eixos_no_medio


@pytest.mark.django_db
def test_objeto_de_conhecimento_so_no_fundamental():
    """O nivel intermediario existe no Fundamental; a Infantil e o Medio nao o tem."""
    from apps.referenciais.models import Competencia, Referencial

    call_command("loaddata", "bncc_computacao", verbosity=0)
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(CSV), verbosity=0)
    bncc = Referencial.objects.get(sigla="BNCC-COMP")

    fundamental = Competencia.objects.filter(referencial=bncc, etapa="EF05")
    assert all(c.objeto_conhecimento for c in fundamental)
    fora = Competencia.objects.filter(referencial=bncc, etapa__in=("EI", "EM"))
    assert not [c.codigo for c in fora if c.objeto_conhecimento]


@pytest.mark.django_db
def test_importar_duas_vezes_nao_duplica():
    """O comando usa update_or_create; reimportar corrige descricao sem duplicar."""
    from apps.referenciais.models import Referencial

    call_command("loaddata", "bncc_computacao", verbosity=0)
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(CSV), verbosity=0)
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(CSV), verbosity=0)
    assert Referencial.objects.get(sigla="BNCC-COMP").competencias.count() == TOTAL


@pytest.mark.django_db
def test_habilidades_de_uma_etapa_vem_agrupadas_por_categoria():
    """O agrupamento da tela e sequencial, e depende de a ordenacao trazer as
    competencias de uma mesma categoria juntas. Se a ordem intercalar categorias,
    o mesmo eixo apareceria duas vezes na tela, com um pedaco em cada lugar.

    E pressuposto do CSV seguir a ordem do documento, que agrupa por eixo. Nada
    no banco garante isso, entao garante aqui."""
    from apps.referenciais.models import Referencial

    call_command("loaddata", "bncc_computacao", verbosity=0)
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(CSV), verbosity=0)
    bncc = Referencial.objects.get(sigla="BNCC-COMP")

    for etapa in POR_ETAPA:
        vistas = []
        for competencia in bncc.competencias.filter(etapa=etapa).select_related("categoria"):
            nome = competencia.categoria.nome
            if not vistas or vistas[-1] != nome:
                vistas.append(nome)
        assert len(vistas) == len(set(vistas)), f"{etapa}: categoria aparece em dois blocos"
