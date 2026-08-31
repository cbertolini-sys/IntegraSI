import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.referenciais.models import Categoria, Competencia, Referencial

CSV = """codigo,descricao,etapa,categoria
EF05CO01,Decompor um problema em partes menores,EF05,Pensamento Computacional
EF05CO04,Reconhecer dados pessoais e sua protecao,EF05,Cultura Digital
"""


@pytest.fixture
def bncc(db):
    call_command("loaddata", "bncc_computacao")
    return Referencial.objects.get(sigla="BNCC-COMP")


@pytest.mark.django_db
def test_fixture_traz_os_tres_eixos_e_as_sete_competencias_do_medio(bncc):
    """Ate o Plano 7 a fixture tinha so os tres eixos. O Ensino Medio da BNCC nao
    os usa: suas 26 habilidades penduram em sete competencias especificas, que
    entram como Categoria ao lado deles (spec 4.2).

    Assercao pelo conjunto exato, e nao por contagem: contar deixaria passar uma
    categoria trocada por outra."""
    assert bncc.min_competencias == 2
    assert bncc.max_competencias == 5
    nomes = set(bncc.categorias.values_list("nome", flat=True))
    assert {"Pensamento Computacional", "Mundo Digital", "Cultura Digital"} <= nomes
    assert len(nomes) == 10


@pytest.mark.django_db
def test_competencia_do_medio_guarda_o_texto_oficial(bncc):
    """O `nome` e rotulo curto, redacao nossa, porque o texto oficial e um
    paragrafo e nao cabe num select. O texto inteiro fica em `descricao`; sem ele,
    o rotulo seria a unica versao e a fonte se perderia."""
    categoria = bncc.categorias.get(nome="Possibilidades e limites da Computação")
    assert categoria.descricao.startswith("Compreender as possibilidades e os limites")
    assert len(categoria.descricao) > 120


@pytest.mark.django_db
def test_os_tres_eixos_nao_precisam_de_texto_oficial(bncc):
    """Prende o outro lado: o nome dos eixos JA e o termo do documento, entao nao
    ha rotulo nosso a justificar. Se `descricao` virasse obrigatoria, este teste
    avisa que a regra mudou de forma."""
    for eixo in ("Pensamento Computacional", "Mundo Digital", "Cultura Digital"):
        assert bncc.categorias.get(nome=eixo).descricao == ""


@pytest.mark.django_db
def test_importa_competencias_do_csv(bncc, tmp_path):
    arquivo = tmp_path / "habilidades.csv"
    arquivo.write_text(CSV, encoding="utf-8")
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    assert Competencia.objects.filter(referencial=bncc).count() == 2
    competencia = Competencia.objects.get(codigo="EF05CO01")
    assert competencia.categoria.nome == "Pensamento Computacional"
    assert competencia.etapa == "EF05"


@pytest.mark.django_db
def test_importar_duas_vezes_nao_duplica_e_atualiza_descricao(bncc, tmp_path):
    arquivo = tmp_path / "habilidades.csv"
    arquivo.write_text(CSV, encoding="utf-8")
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    arquivo.write_text(CSV.replace("Decompor um problema em partes menores", "Texto corrigido"), encoding="utf-8")
    call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    assert Competencia.objects.filter(referencial=bncc).count() == 2
    assert Competencia.objects.get(codigo="EF05CO01").descricao == "Texto corrigido"


@pytest.mark.django_db
def test_categoria_desconhecida_no_csv_interrompe_a_importacao(bncc, tmp_path):
    """A primeira linha é válida de propósito: se alguém tirar o @transaction.atomic
    do comando, essa linha sobrevive à falha da segunda e o count() abaixo vira 1,
    não 0. Com uma única linha inválida o teste passaria mesmo sem a transação,
    porque nada teria sido inserido antes do erro -- não testaria rollback nenhum."""
    arquivo = tmp_path / "habilidades.csv"
    arquivo.write_text(
        "codigo,descricao,etapa,categoria\n"
        "EF05CO01,Decompor um problema,EF05,Pensamento Computacional\n"
        "EF05CO09,X,EF05,Eixo Inexistente\n",
        encoding="utf-8",
    )
    with pytest.raises(CommandError):
        call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    assert Competencia.objects.filter(referencial=bncc).count() == 0


@pytest.mark.django_db
def test_etapa_invalida_no_csv_interrompe_a_importacao(bncc, tmp_path):
    """A CSV é transcrita à mão do PDF da Resolução: um erro de digitação na etapa
    (EF5 em vez de EF05) é o erro esperado, não uma hipótese remota. Sem validar
    contra ETAPAS, update_or_create salva silenciosamente -- a habilidade some do
    ano certo sem nenhum aviso. Antes desta guarda, esta importação tinha sucesso e
    deixava uma Competencia com etapa='EF5' no banco."""
    arquivo = tmp_path / "habilidades.csv"
    arquivo.write_text(
        "codigo,descricao,etapa,categoria\n"
        "EF05CO01,Decompor um problema,EF5,Pensamento Computacional\n",
        encoding="utf-8",
    )
    with pytest.raises(CommandError):
        call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    assert Competencia.objects.filter(referencial=bncc).count() == 0


@pytest.mark.django_db
def test_linha_com_campo_faltando_da_erro_tratado_em_vez_de_traceback(bncc, tmp_path):
    """csv.DictReader preenche campos ausentes com None quando falta uma vírgula na
    linha. Sem tratamento, linha["categoria"].strip() estoura AttributeError -- um
    traceback cru no terminal do coordenador em vez de uma mensagem útil."""
    arquivo = tmp_path / "habilidades.csv"
    arquivo.write_text(
        "codigo,descricao,etapa,categoria\nEF05CO01,Decompor um problema,EF05\n",
        encoding="utf-8",
    )
    with pytest.raises(CommandError):
        call_command("importar_competencias", referencial="BNCC-COMP", csv=str(arquivo))
    assert Competencia.objects.filter(referencial=bncc).count() == 0
