import pytest
from django.core.exceptions import ValidationError

from apps.referenciais.choices import ETAPAS
from apps.referenciais.models import Categoria, Competencia, Referencial


@pytest.fixture
def bncc(db):
    return Referencial.objects.create(
        nome="BNCC da Computacao",
        sigla="BNCC-COMP",
        descricao="Resolucao CNE/CEB 1/2022",
        min_competencias=2,
        max_competencias=5,
    )


@pytest.fixture
def pensamento(bncc):
    return Categoria.objects.create(referencial=bncc, nome="Pensamento Computacional", ordem=1)


def test_etapas_cobrem_da_infantil_ao_medio():
    codigos = [codigo for codigo, _ in ETAPAS]
    assert "EI" in codigos
    assert "EF05" in codigos
    assert "EM03" in codigos


@pytest.mark.django_db
def test_faixa_aceita_quantidade_dentro_do_intervalo(bncc):
    bncc.valida_quantidade(2)
    bncc.valida_quantidade(5)


@pytest.mark.django_db
def test_faixa_recusa_abaixo_do_minimo(bncc):
    with pytest.raises(ValidationError):
        bncc.valida_quantidade(1)


@pytest.mark.django_db
def test_faixa_recusa_acima_do_maximo(bncc):
    with pytest.raises(ValidationError):
        bncc.valida_quantidade(6)


@pytest.mark.django_db
def test_maximo_menor_que_minimo_e_recusado(bncc):
    bncc.max_competencias = 1
    with pytest.raises(ValidationError):
        bncc.full_clean()


@pytest.mark.django_db
def test_criar_com_maximo_menor_que_minimo_e_recusado():
    """clean() só é alcançável via full_clean(); sem save() -> full_clean(), o
    .create() abaixo passa direto pelo INSERT e deixa no banco um referencial
    cuja faixa Curso.valida_quantidade() (Plano 2) nunca consegue satisfazer."""
    with pytest.raises(ValidationError):
        Referencial.objects.create(
            nome="Faixa Invertida",
            sigla="FAIXA-INV",
            min_competencias=5,
            max_competencias=1,
        )


@pytest.mark.django_db
def test_competencia_de_categoria_de_outro_referencial_e_recusada(bncc, pensamento):
    outro = Referencial.objects.create(
        nome="Curriculo Gaucho", sigla="CG", min_competencias=1, max_competencias=3
    )
    competencia = Competencia(
        referencial=outro,
        categoria=pensamento,
        codigo="XX01",
        descricao="Qualquer",
        etapa="EF05",
        ordem=1,
    )
    with pytest.raises(ValidationError):
        competencia.full_clean()


@pytest.mark.django_db
def test_codigo_repetido_no_mesmo_referencial_e_recusado(bncc, pensamento):
    Competencia.objects.create(
        referencial=bncc, categoria=pensamento, codigo="EF05CO01", descricao="A", etapa="EF05", ordem=1
    )
    duplicada = Competencia(
        referencial=bncc, categoria=pensamento, codigo="EF05CO01", descricao="B", etapa="EF05", ordem=2
    )
    with pytest.raises(ValidationError):
        duplicada.full_clean()


@pytest.mark.django_db
def test_str_da_competencia_mostra_codigo(bncc, pensamento):
    competencia = Competencia.objects.create(
        referencial=bncc, categoria=pensamento, codigo="EF05CO01", descricao="Descricao", etapa="EF05", ordem=1
    )
    assert str(competencia).startswith("EF05CO01")


@pytest.mark.django_db
def test_apagar_referencial_apaga_categorias_e_competencias(bncc, pensamento):
    Competencia.objects.create(
        referencial=bncc, categoria=pensamento, codigo="EF05CO01", descricao="A", etapa="EF05", ordem=1
    )
    bncc.delete()
    assert Categoria.objects.count() == 0
    assert Competencia.objects.count() == 0


@pytest.mark.django_db
def test_apagar_categoria_apaga_suas_competencias(bncc, pensamento):
    Competencia.objects.create(
        referencial=bncc, categoria=pensamento, codigo="EF05CO01", descricao="A", etapa="EF05", ordem=1
    )
    pensamento.delete()
    assert Competencia.objects.count() == 0
