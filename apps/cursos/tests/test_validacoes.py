import pytest

from apps.cursos import services, validacoes
from apps.cursos.choices import Rotulo, TipoEntregavel, TipoMidia, TipoPratica
from apps.cursos.models import Anexo


@pytest.fixture
def curso_criado(dados_curso):
    return services.criar_curso(**dados_curso)


def anexa(entregavel, aluno, arquivo, **extra):
    dados = {
        "entregavel": entregavel,
        "tipo_midia": TipoMidia.ARQUIVO,
        "titulo": "Material",
        "arquivo": arquivo,
        "enviado_por": aluno,
    }
    dados.update(extra)
    return Anexo.objects.create(**dados)


@pytest.mark.django_db
def test_plano_de_ensino_sem_anexo_e_sem_conteudo_lista_as_duas_faltas(curso_criado):
    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    faltas = validacoes.pendencias(plano)
    assert any("PDF" in f for f in faltas)
    assert any("seção" in f.lower() for f in faltas)


@pytest.mark.django_db
def test_plano_de_ensino_completo_nao_tem_pendencia(curso_criado, aluno, arquivo_qualquer):
    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    anexa(plano, aluno, arquivo_qualquer)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa da oficina.</p>"
    secao.save()
    assert validacoes.pendencias(plano) == []


@pytest.mark.django_db
def test_cards_sem_nenhum_anexo_e_apontado(curso_criado):
    cards = curso_criado.entregaveis.get(tipo=TipoEntregavel.CARDS)
    assert validacoes.pendencias(cards) == ["Anexe ao menos um card."]


@pytest.mark.django_db
def test_cards_sem_referencia_bibliografica_sao_apontados(curso_criado, aluno, arquivo_qualquer):
    cards = curso_criado.entregaveis.get(tipo=TipoEntregavel.CARDS)
    anexa(cards, aluno, arquivo_qualquer, titulo="Card 1")
    faltas = validacoes.pendencias(cards)
    assert len(faltas) == 1
    assert "Card 1" in faltas[0]


@pytest.mark.django_db
def test_cards_aponta_apenas_o_que_falta_referencia_entre_varios(curso_criado, aluno, arquivo_qualquer):
    """Com um so card a checagem passaria mesmo olhando so anexos[0]; com dois, o
    segundo sem referencia, so uma implementacao que percorre todos os anexos acerta
    tanto em nao reclamar do Card 1 quanto em citar o Card 2."""
    cards = curso_criado.entregaveis.get(tipo=TipoEntregavel.CARDS)
    anexa(cards, aluno, arquivo_qualquer, titulo="Card 1", referencia_bibliografica="BRASIL, 2022.")
    anexa(cards, aluno, arquivo_qualquer, titulo="Card 2")
    faltas = validacoes.pendencias(cards)
    assert len(faltas) == 1
    assert "Card 2" in faltas[0]
    assert "Card 1" not in faltas[0]


@pytest.mark.django_db
def test_cards_com_referencia_passam(curso_criado, aluno, arquivo_qualquer):
    cards = curso_criado.entregaveis.get(tipo=TipoEntregavel.CARDS)
    anexa(cards, aluno, arquivo_qualquer, referencia_bibliografica="BRASIL, 2022.")
    assert validacoes.pendencias(cards) == []


@pytest.mark.django_db
def test_caderno_exige_as_duas_versoes_e_as_duas_praticas(curso_criado, aluno, arquivo_qualquer):
    caderno = curso_criado.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    anexa(caderno, aluno, arquivo_qualquer, rotulo=Rotulo.SEM_GABARITO, tipo_pratica=TipoPratica.PLUGADA)
    faltas = validacoes.pendencias(caderno)
    assert any("gabarito" in f for f in faltas)
    assert any("desplugada" in f for f in faltas)


@pytest.mark.django_db
def test_caderno_sem_versao_sem_gabarito_e_apontado(curso_criado, aluno, arquivo_qualquer):
    """Cobre o guard de SEM_GABARITO, que na suite anterior estava sempre presente e
    nunca falhava: aqui so ha COM_GABARITO, com AMBAS as praticas para nao acionar os
    outros dois guards junto."""
    caderno = curso_criado.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    anexa(caderno, aluno, arquivo_qualquer, rotulo=Rotulo.COM_GABARITO, tipo_pratica=TipoPratica.AMBAS)
    faltas = validacoes.pendencias(caderno)
    assert "Anexe a versão sem gabarito." in faltas


@pytest.mark.django_db
def test_caderno_sem_atividade_plugada_e_apontado(curso_criado, aluno, arquivo_qualquer):
    """Cobre o guard de PLUGADA, que na suite anterior estava sempre presente e nunca
    falhava: aqui as duas versoes de gabarito estao presentes e a unica pratica e
    DESPLUGADA."""
    caderno = curso_criado.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    anexa(caderno, aluno, arquivo_qualquer, rotulo=Rotulo.SEM_GABARITO, tipo_pratica=TipoPratica.NENHUM)
    anexa(caderno, aluno, arquivo_qualquer, rotulo=Rotulo.COM_GABARITO, tipo_pratica=TipoPratica.DESPLUGADA)
    faltas = validacoes.pendencias(caderno)
    assert faltas == ["Inclua ao menos uma atividade plugada."]


@pytest.mark.django_db
def test_caderno_completo_passa(curso_criado, aluno, arquivo_qualquer):
    caderno = curso_criado.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    anexa(caderno, aluno, arquivo_qualquer, rotulo=Rotulo.SEM_GABARITO, tipo_pratica=TipoPratica.PLUGADA)
    anexa(caderno, aluno, arquivo_qualquer, rotulo=Rotulo.COM_GABARITO, tipo_pratica=TipoPratica.DESPLUGADA)
    assert validacoes.pendencias(caderno) == []


@pytest.mark.django_db
@pytest.mark.parametrize("quantidade,tem_falta", [(1, True), (2, False), (3, False), (4, True)])
def test_videos_de_dois_a_tres(curso_criado, aluno, arquivo_qualquer, quantidade, tem_falta):
    videos = curso_criado.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    for numero in range(quantidade):
        anexa(videos, aluno, arquivo_qualquer, tipo_midia=TipoMidia.VIDEO,
              titulo=f"Aula {numero}", duracao_minutos=7)
    assert bool(validacoes.pendencias(videos)) is tem_falta


@pytest.mark.django_db
@pytest.mark.parametrize("duracao", [4, 11])
def test_video_fora_da_faixa_de_duracao(curso_criado, aluno, arquivo_qualquer, duracao):
    videos = curso_criado.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    for numero in range(2):
        anexa(videos, aluno, arquivo_qualquer, tipo_midia=TipoMidia.VIDEO,
              titulo=f"Aula {numero}", duracao_minutos=duracao)
    assert any("minutos" in f for f in validacoes.pendencias(videos))


@pytest.mark.django_db
def test_link_nao_conta_como_video(curso_criado, aluno):
    videos = curso_criado.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    # duracao_minutos valida de proposito: se o filtro por tipo_midia=VIDEO sumir,
    # estes dois links teriam contagem e duracao perfeitas e passariam sem pendencia
    # nenhuma, o que e o unico jeito de o teste flagrar a ausencia do filtro.
    for numero in range(2):
        Anexo.objects.create(
            entregavel=videos, tipo_midia=TipoMidia.LINK, titulo=f"Video {numero}",
            url="https://exemplo.org/video", duracao_minutos=7, enviado_por=aluno,
        )
    assert validacoes.pendencias(videos) != []


@pytest.mark.django_db
@pytest.mark.parametrize("duracao", [5, 10])
def test_video_no_limite_da_faixa_de_duracao_passa(curso_criado, aluno, arquivo_qualquer, duracao):
    videos = curso_criado.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    for numero in range(2):
        anexa(videos, aluno, arquivo_qualquer, tipo_midia=TipoMidia.VIDEO,
              titulo=f"Aula {numero}", duracao_minutos=duracao)
    assert validacoes.pendencias(videos) == []


@pytest.mark.django_db
def test_plano_de_ensino_aponta_falta_de_publico_alvo(curso_criado, aluno, arquivo_qualquer):
    from apps.cursos.models import Curso

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    anexa(plano, aluno, arquivo_qualquer)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()

    # etapa_ano tem blank=True, entao o banco aceita "" direto; o .update() contorna
    # o full_clean() do Curso, que normalmente exigiria etapa_ano quando ESCOLAR.
    Curso.objects.filter(pk=curso_criado.pk).update(etapa_ano="")
    curso_criado.refresh_from_db()

    assert any("público-alvo" in f for f in validacoes.pendencias(plano))


@pytest.mark.django_db
def test_plano_de_ensino_aponta_falta_de_carga_horaria(curso_criado, aluno, arquivo_qualquer):
    from apps.cursos.models import Curso

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    anexa(plano, aluno, arquivo_qualquer)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()

    # carga_horaria e PositiveSmallIntegerField sem null=True: a coluna e NOT NULL no
    # banco, entao .update(carga_horaria=None) estouraria IntegrityError. 0 e o valor
    # falso que o banco aceita; so o MinValueValidator(1) do modelo o rejeitaria, e o
    # .update() contorna justamente esse full_clean().
    Curso.objects.filter(pk=curso_criado.pk).update(carga_horaria=0)
    curso_criado.refresh_from_db()

    assert any("carga horária" in f for f in validacoes.pendencias(plano))


@pytest.mark.django_db
def test_plano_de_ensino_aponta_falta_de_formato(curso_criado, aluno, arquivo_qualquer):
    from apps.cursos.models import Curso

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    anexa(plano, aluno, arquivo_qualquer)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()

    Curso.objects.filter(pk=curso_criado.pk).update(formato="")
    curso_criado.refresh_from_db()

    assert any("formato" in f for f in validacoes.pendencias(plano))


@pytest.mark.django_db
def test_curso_com_referencial_fora_da_faixa_e_apontado(curso_criado, aluno, arquivo_qualquer, db):
    from apps.referenciais.models import Categoria, Competencia, Referencial

    referencial = Referencial.objects.create(
        nome="BNCC da Computacao", sigla="BNCC-COMP", min_competencias=2, max_competencias=5
    )
    categoria = Categoria.objects.create(referencial=referencial, nome="Mundo Digital", ordem=1)
    competencia = Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="EF05CO01",
        descricao="Descricao", etapa="EF05", ordem=1,
    )
    curso_criado.referencial = referencial
    curso_criado.save()
    curso_criado.competencias.add(competencia)

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    anexa(plano, aluno, arquivo_qualquer)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()

    assert any("competências" in f for f in validacoes.pendencias(plano))


@pytest.mark.django_db
def test_curso_com_referencial_dentro_da_faixa_nao_tem_pendencia_de_competencias(
    curso_criado, aluno, arquivo_qualquer, db
):
    from apps.referenciais.models import Categoria, Competencia, Referencial

    referencial = Referencial.objects.create(
        nome="BNCC da Computacao 2", sigla="BNCC-COMP-2", min_competencias=1, max_competencias=5
    )
    categoria = Categoria.objects.create(referencial=referencial, nome="Mundo Digital", ordem=1)
    competencia = Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="EF05CO01",
        descricao="Descricao", etapa="EF05", ordem=1,
    )
    curso_criado.referencial = referencial
    curso_criado.save()
    curso_criado.competencias.add(competencia)

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    anexa(plano, aluno, arquivo_qualquer)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()

    assert not any("competências" in f for f in validacoes.pendencias(plano))


@pytest.mark.django_db
def test_curso_sem_referencial_nao_tem_pendencia_de_competencias(curso_criado, aluno, arquivo_qualquer):
    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    anexa(plano, aluno, arquivo_qualquer)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa</p>"
    secao.save()

    assert curso_criado.referencial_id is None
    assert not any("competências" in f for f in validacoes.pendencias(plano))


@pytest.mark.django_db
def test_slides_exigem_ao_menos_um_arquivo(curso_criado, aluno, arquivo_qualquer):
    slides = curso_criado.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    assert validacoes.pendencias(slides) != []
    anexa(slides, aluno, arquivo_qualquer)
    assert validacoes.pendencias(slides) == []
