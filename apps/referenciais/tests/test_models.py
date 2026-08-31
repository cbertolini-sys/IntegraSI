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


# --- O vocabulario de etapa do referencial (Plano 7) -------------------------


def test_etapa_do_curso_vira_etapa_do_referencial():
    """As habilidades do Medio (EM13CO) valem para os tres anos de uma vez, entao
    os tres anos do curso apontam para a mesma etapa do referencial."""
    from apps.referenciais.choices import etapa_do_referencial

    assert etapa_do_referencial("EM01") == "EM"
    assert etapa_do_referencial("EM02") == "EM"
    assert etapa_do_referencial("EM03") == "EM"


def test_etapas_do_fundamental_e_da_infantil_passam_direto():
    """Prende o outro lado: so o Medio e agregado. Sem este par, um
    `return "EM"` incondicional passaria no teste de cima."""
    from apps.referenciais.choices import etapa_do_referencial

    assert etapa_do_referencial("EF05") == "EF05"
    assert etapa_do_referencial("EI") == "EI"


def test_curso_sem_etapa_nao_tem_etapa_de_referencial():
    """Curso comunitario nao tem etapa_ano. Devolver "" e o que deixa a tela
    mostrar lista vazia em vez de estourar."""
    from apps.referenciais.choices import etapa_do_referencial

    assert etapa_do_referencial("") == ""
    assert etapa_do_referencial(None) == ""


def test_educacao_infantil_chama_de_objetivo_de_aprendizagem():
    """O documento usa dois termos, e a tela precisa usar o da etapa (spec 4.2)."""
    from apps.referenciais.choices import rotulo_da_competencia

    assert rotulo_da_competencia("EI") == "objetivo de aprendizagem"
    assert rotulo_da_competencia("EI", plural=True) == "objetivos de aprendizagem"


def test_do_primeiro_ano_em_diante_chama_de_habilidade():
    from apps.referenciais.choices import rotulo_da_competencia

    assert rotulo_da_competencia("EF01") == "habilidade"
    assert rotulo_da_competencia("EM", plural=True) == "habilidades"


@pytest.mark.django_db
def test_referencial_sem_competencias_nao_organiza_por_etapa():
    """A pergunta e sobre o DADO, e nao sobre a sigla: nenhuma tela pode
    pressupor BNCC (spec 4.2). Referencial recem-criado, sem CSV importado
    ainda, nao pode exigir etapa de curso nenhum."""
    referencial = Referencial.objects.create(nome="Vazio", sigla="VAZIO")
    assert referencial.organiza_por_etapa is False


@pytest.mark.django_db
def test_referencial_com_competencias_organiza_por_etapa():
    """Prende o outro lado: sem este par, um `return False` fixo passaria.

    `etapa="EM"` de proposito: e o valor que so existe no vocabulario novo, entao
    este teste tambem prende a troca de ETAPAS por ETAPAS_REFERENCIAL."""
    referencial = Referencial.objects.create(nome="Com dados", sigla="COMD")
    categoria = Categoria.objects.create(referencial=referencial, nome="Eixo", ordem=1)
    Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="XX01CO01",
        descricao="Descricao qualquer.", etapa="EM", ordem=1,
    )
    assert referencial.organiza_por_etapa is True
