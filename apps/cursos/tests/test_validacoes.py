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
def test_cards_sem_referencia_bibliografica_sao_apontados(curso_criado, aluno, arquivo_qualquer):
    cards = curso_criado.entregaveis.get(tipo=TipoEntregavel.CARDS)
    anexa(cards, aluno, arquivo_qualquer, titulo="Card 1")
    faltas = validacoes.pendencias(cards)
    assert len(faltas) == 1
    assert "Card 1" in faltas[0]


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
    for numero in range(2):
        Anexo.objects.create(
            entregavel=videos, tipo_midia=TipoMidia.LINK, titulo=f"Video {numero}",
            url="https://exemplo.org/video", enviado_por=aluno,
        )
    assert validacoes.pendencias(videos) != []


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
