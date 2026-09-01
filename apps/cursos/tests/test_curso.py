import pytest
from django.core.exceptions import ValidationError

from apps.cursos.choices import StatusCurso, TipoPublico
from apps.cursos.models import Curso


@pytest.mark.django_db
def test_curso_nasce_em_rascunho(curso):
    assert curso.status == StatusCurso.RASCUNHO
    assert curso.publicado_em is None


@pytest.mark.django_db
def test_publico_escolar_exige_etapa(dados_curso):
    dados_curso["etapa_ano"] = ""
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)


@pytest.mark.django_db
def test_publico_escolar_aceita_descricao_como_complemento(dados_curso):
    """Regra invertida a pedido de quem preenche. A descricao era PROIBIDA junto
    com a etapa; passou a ser complemento, porque "5o ano" e "turmas da escola do
    campo" dizem mais juntos do que separados."""
    dados_curso["publico_descricao"] = "Turmas da escola do campo"
    curso = Curso.objects.create(**dados_curso)
    assert curso.publico_descricao == "Turmas da escola do campo"


@pytest.mark.django_db
def test_publico_comunitario_nao_exige_descricao(dados_curso):
    """A outra metade da mesma inversao: a descricao era OBRIGATORIA no
    comunitario. O catalogo nao fica sem publico porque `publico_alvo` cai para o
    rotulo do tipo, o que o teste confere junto: sem essa queda, a regra teria
    sido trocada por um buraco."""
    dados_curso["tipo_publico"] = TipoPublico.COMUNITARIO
    dados_curso["etapa_ano"] = ""
    curso = Curso.objects.create(**dados_curso)
    assert curso.publico_descricao == ""
    assert curso.publico_alvo == "Público da comunidade"


@pytest.mark.django_db
def test_publico_comunitario_nao_aceita_etapa(dados_curso):
    dados_curso["tipo_publico"] = TipoPublico.COMUNITARIO
    dados_curso["publico_descricao"] = "Adultos em vulnerabilidade digital"
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)


@pytest.mark.django_db
def test_publico_alvo_legivel(curso, dados_curso):
    assert curso.publico_alvo == "5º ano do Ensino Fundamental"
    dados_curso.update(
        tipo_publico=TipoPublico.COMUNITARIO,
        etapa_ano="",
        publico_descricao="Adultos em vulnerabilidade digital",
        titulo="Outro curso",
    )
    comunitario = Curso.objects.create(**dados_curso)
    assert comunitario.publico_alvo == "Adultos em vulnerabilidade digital"


@pytest.mark.django_db
def test_carga_horaria_zero_e_recusada(dados_curso):
    dados_curso["carga_horaria"] = 0
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)


@pytest.mark.django_db
def test_curso_sem_referencial_e_valido(curso):
    assert curso.referencial is None
    assert curso.competencias.count() == 0


@pytest.mark.django_db
def test_professor_responsavel_precisa_ser_professor(dados_curso, aluno):
    dados_curso["professor_responsavel"] = aluno
    with pytest.raises(ValidationError):
        Curso.objects.create(**dados_curso)


@pytest.mark.django_db
def test_identidade_de_proposta_sem_ficha_nao_mostra_none(edicao, professor):
    """Achado olhando a tela: a pagina de um curso recem-proposto mostrava
    " . Noneh . ", porque o template do Django renderiza None como "None" e a
    ficha nasce vazia (spec 4.3). A suite inteira passava com o defeito no ar."""
    from apps.cursos import services

    curso = services.criar_curso(titulo="Proposta nova", professor_responsavel=professor)
    assert "None" not in curso.identidade
    assert curso.identidade == "Ficha ainda não preenchida"


@pytest.mark.django_db
def test_identidade_monta_so_com_o_que_esta_preenchido(curso):
    """Prende o outro lado: com a ficha completa a linha traz as tres partes."""
    assert curso.identidade == "5º ano do Ensino Fundamental · 12h · Presencial"


@pytest.mark.django_db
def test_identidade_omite_a_parte_que_falta(curso):
    """Ficha pela metade nao pode virar "12h . " nem "None": a parte ausente sai."""
    curso.formato = ""
    curso.save()
    assert curso.identidade == "5º ano do Ensino Fundamental · 12h"


@pytest.mark.django_db
def test_entregaveis_saem_na_ordem_do_roteiro(dados_curso):
    """Os rotulos sao numerados de A a E, e e nessa ordem que a tela deve mostra-los.

    O `ordering` antigo era ["curso", "tipo"], que ordena pelo VALOR gravado
    (CADERNO, CARDS, PLANO_ENSINO, SLIDES, VIDEOS) e nao pelo rotulo: a pagina do
    curso exibia C, B, A, E, D. Assercao pela lista inteira, e nao pelo primeiro
    item: com so o primeiro, trocar D com E passaria batido.
    """
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    rotulos = [e.get_tipo_display() for e in curso.entregaveis.all()]
    assert rotulos == [
        "1 - Plano de Ensino e Mapeamento Pedagógico",
        "2 - Slides e Apresentações",
        "3 - Vídeo-Aulas",
        "4 - Infográficos e Cards Educativos",
        "5 - Caderno de Exercícios e Atividades Práticas",
        "6 - Avaliação",
    ]


# --- O card do entregavel: etapa e nome separados (a pedido) -----------------


@pytest.mark.django_db
def test_entregavel_sabe_o_numero_da_etapa(dados_curso):
    """A posicao vem da ordem de declaracao de TipoEntregavel, a mesma fonte de
    ORDEM_DO_ROTEIRO: dois lugares lendo a mesma lista nao saem de sincronia."""
    from apps.cursos import services
    from apps.cursos.choices import TipoEntregavel

    curso = services.criar_curso(**dados_curso)
    numeros = {e.tipo: e.numero for e in curso.entregaveis.all()}
    assert numeros[TipoEntregavel.PLANO_ENSINO] == 1
    assert numeros[TipoEntregavel.AVALIACAO] == 6


@pytest.mark.django_db
def test_entregavel_tem_nome_sem_o_numero(dados_curso):
    """A tela mostra "Etapa 1" ao lado; repetir o numero no titulo o diria duas
    vezes na mesma linha."""
    from apps.cursos import services
    from apps.cursos.choices import TipoEntregavel

    curso = services.criar_curso(**dados_curso)
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    assert plano.nome == "Plano de Ensino e Mapeamento Pedagógico"
    assert plano.get_tipo_display() == "1 - Plano de Ensino e Mapeamento Pedagógico"
