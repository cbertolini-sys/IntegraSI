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
def test_plano_de_ensino_em_branco_nomeia_as_secoes_que_faltam(curso_criado):
    """Regra trocada a pedido: nao ha mais anexo em PDF, e todas as sete secoes
    passaram a ser exigidas. A mensagem NOMEIA as que faltam, e nao diz apenas que
    falta alguma: e a mensagem que evita a ida e volta com o professor (spec 6)."""
    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    faltas = validacoes.pendencias(plano)
    assert not any("PDF" in f for f in faltas)
    cobranca = [f for f in faltas if "Preencha estas seções" in f]
    assert len(cobranca) == 1
    for titulo in plano.secoes.values_list("titulo", flat=True):
        assert titulo in cobranca[0]


@pytest.mark.django_db
def test_plano_de_ensino_completo_nao_tem_pendencia(curso_criado):
    """Completo passou a significar as sete secoes escritas, e nenhum anexo."""
    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    for secao in plano.secoes.all():
        secao.conteudo = f"<p>Conteúdo de {secao.titulo}.</p>"
        secao.save()
    assert validacoes.pendencias(plano) == []


# O teste que prendia "o anexo do plano precisa ser PDF" saiu daqui junto com a
# regra: o Plano de Ensino deixou de ter anexo, e a tela nao oferece mais materiais
# para ele. Ele existia porque a regra do PDF nunca tinha como falhar na suite (o
# unico Arquivo criado por ela era um PDF), e essa licao continua valendo para
# qualquer filtro por mime que apareca depois.

@pytest.mark.django_db
def test_cards_sem_nenhum_anexo_e_apontado(curso_criado):
    cards = curso_criado.entregaveis.get(tipo=TipoEntregavel.CARDS)
    assert validacoes.pendencias(cards) == ["Anexe ao menos um card."]


@pytest.mark.django_db
def test_link_nao_conta_como_card(curso_criado, aluno):
    # _arquivos() exclui TipoMidia.LINK, mas so test_link_nao_conta_como_video
    # cravava isso - CARDS, CADERNO e SLIDES passavam pelo mesmo _arquivos() sem
    # nenhum teste que anexasse so um link (item 10 da revisao de branco). A spec
    # diz que link nao satisfaz validacao nenhuma.
    cards = curso_criado.entregaveis.get(tipo=TipoEntregavel.CARDS)
    Anexo.objects.create(
        entregavel=cards, tipo_midia=TipoMidia.LINK, titulo="Card por link",
        url="https://exemplo.org/card", enviado_por=aluno,
    )
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
def test_link_nao_conta_como_caderno(curso_criado, aluno):
    # Os dois links juntos teriam as duas versoes de gabarito e as duas praticas -
    # se contassem, pendencias(caderno) viria vazia. So assim o teste realmente
    # depende da exclusao de LINK em _arquivos(), e nao passa so porque os valores
    # default (NENHUM) de um unico anexo ja deixam faltas sobrando.
    caderno = curso_criado.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    Anexo.objects.create(
        entregavel=caderno, tipo_midia=TipoMidia.LINK, titulo="Sem gabarito por link",
        url="https://exemplo.org/caderno-sem-gabarito", enviado_por=aluno,
        rotulo=Rotulo.SEM_GABARITO, tipo_pratica=TipoPratica.PLUGADA,
    )
    Anexo.objects.create(
        entregavel=caderno, tipo_midia=TipoMidia.LINK, titulo="Com gabarito por link",
        url="https://exemplo.org/caderno-com-gabarito", enviado_por=aluno,
        rotulo=Rotulo.COM_GABARITO, tipo_pratica=TipoPratica.DESPLUGADA,
    )
    faltas = validacoes.pendencias(caderno)
    assert "Anexe a versão sem gabarito." in faltas
    assert "Anexe a versão com gabarito." in faltas
    assert "Inclua ao menos uma atividade plugada." in faltas
    assert "Inclua ao menos uma atividade desplugada." in faltas


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
def test_curso_com_referencial_fora_da_faixa_e_apontado(curso_criado, aluno, arquivo_qualquer):
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
    curso_criado, aluno, arquivo_qualquer
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


@pytest.mark.django_db
def test_link_nao_conta_como_slides(curso_criado, aluno):
    slides = curso_criado.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.LINK, titulo="Slides por link",
        url="https://exemplo.org/slides", enviado_por=aluno,
    )
    assert validacoes.pendencias(slides) == ["Anexe ao menos um arquivo de slides."]


@pytest.mark.django_db
def test_resumo_vazio_e_pendencia_do_curso(curso_criado):
    """O resumo deixou de ser obrigatorio na criacao (Plano 6), entao alguem
    precisa cobra-lo antes do catalogo. O portao e onde isso mora."""
    curso_criado.resumo = ""
    curso_criado.save()
    faltas = validacoes.dados_do_curso(curso_criado)
    assert any("resumo" in f.lower() for f in faltas)


@pytest.mark.django_db
def test_curso_com_resumo_nao_tem_essa_pendencia(curso_criado):
    """Prende o outro lado: com resumo preenchido a cobranca some. Sem este par,
    um `faltas.append` incondicional passaria no teste de cima."""
    assert curso_criado.resumo
    assert not any("resumo" in f.lower() for f in validacoes.dados_do_curso(curso_criado))


# --- Referencial organizado por etapa exige etapa (Plano 7) ------------------


@pytest.fixture
def bncc_carregada(db):
    from pathlib import Path

    from django.conf import settings
    from django.core.management import call_command

    from apps.referenciais.models import Referencial

    call_command("loaddata", "bncc_computacao", verbosity=0)
    call_command(
        "importar_competencias", referencial="BNCC-COMP",
        csv=str(Path(settings.BASE_DIR) / "docs" / "dados" / "bncc_computacao_habilidades.csv"),
        verbosity=0,
    )
    return Referencial.objects.get(sigla="BNCC-COMP")


@pytest.mark.django_db
def test_referencial_por_etapa_exige_etapa_do_curso(curso_criado, bncc_carregada):
    """Spec 4.2: sem etapa, o curso fica com um referencial cujas habilidades
    nenhuma tela consegue listar."""
    from apps.cursos.choices import TipoPublico

    curso_criado.referencial = bncc_carregada
    curso_criado.tipo_publico = TipoPublico.COMUNITARIO
    curso_criado.etapa_ano = ""
    curso_criado.publico_descricao = "Grupo de convivência do bairro"
    curso_criado.save()
    faltas = validacoes.dados_do_curso(curso_criado)
    assert any("etapa" in f.lower() for f in faltas)


@pytest.mark.django_db
def test_referencial_sem_competencias_nao_exige_etapa(curso_criado):
    """Prende o outro lado, e prende a regra CERTA: a exigencia vem do dado, nao
    da sigla. Um referencial recem-criado, sem CSV importado, nao pode travar
    curso nenhum (spec 4.2: nenhuma tela pressupoe BNCC)."""
    from apps.cursos.choices import TipoPublico
    from apps.referenciais.models import Referencial

    curso_criado.referencial = Referencial.objects.create(nome="Novo", sigla="NOVO")
    curso_criado.tipo_publico = TipoPublico.COMUNITARIO
    curso_criado.etapa_ano = ""
    curso_criado.publico_descricao = "Grupo de convivência do bairro"
    curso_criado.save()
    assert not any("etapa" in f.lower() for f in validacoes.dados_do_curso(curso_criado))


@pytest.mark.django_db
def test_curso_escolar_com_etapa_nao_tem_essa_pendencia(curso_criado, bncc_carregada):
    """Com etapa definida a cobranca some. Sem este par, um append incondicional
    passaria no primeiro teste."""
    curso_criado.referencial = bncc_carregada
    curso_criado.save()
    assert curso_criado.etapa_ano
    assert not any("etapa escolar" in f for f in validacoes.dados_do_curso(curso_criado))


# --- Descricao do publico opcional e palavras-chave exigidas (a pedido) ------


@pytest.mark.django_db
def test_descricao_do_publico_e_livre_no_publico_escolar(curso_criado):
    """Era proibida junto com a etapa. Passa a ser complemento: "5o ano" e "turmas
    da escola do campo" dizem mais juntos do que separados."""
    curso_criado.publico_descricao = "Turmas da escola do campo"
    curso_criado.save()  # full_clean roda aqui; antes levantava ValidationError
    assert curso_criado.publico_descricao


@pytest.mark.django_db
def test_curso_comunitario_sem_descricao_ainda_diz_para_quem_e(curso_criado):
    """A descricao deixou de ser obrigatoria, e o catalogo nao pode ficar sem
    dizer para quem o curso e: cai para o tipo de publico."""
    from apps.cursos.choices import TipoPublico

    curso_criado.tipo_publico = TipoPublico.COMUNITARIO
    curso_criado.etapa_ano = ""
    curso_criado.publico_descricao = ""
    curso_criado.save()
    assert curso_criado.publico_alvo == "Público da comunidade"
    assert not any("público-alvo" in f for f in validacoes.dados_do_curso(curso_criado))


@pytest.mark.django_db
def test_descricao_preenchida_ganha_do_tipo(curso_criado):
    """Prende o outro lado: com descricao, e ela que aparece, nao o rotulo generico."""
    from apps.cursos.choices import TipoPublico

    curso_criado.tipo_publico = TipoPublico.COMUNITARIO
    curso_criado.etapa_ano = ""
    curso_criado.publico_descricao = "Grupos de convivência do bairro"
    curso_criado.save()
    assert curso_criado.publico_alvo == "Grupos de convivência do bairro"


@pytest.mark.django_db
def test_publico_escolar_continua_exigindo_etapa(curso_criado):
    """O que caiu foi a regra da DESCRICAO. A etapa continua obrigatoria no
    publico escolar, e continua proibida no comunitario."""
    from django.core.exceptions import ValidationError as ErroDeValidacao

    from apps.cursos.choices import TipoPublico

    curso_criado.etapa_ano = ""
    with pytest.raises(ErroDeValidacao):
        curso_criado.save()

    curso_criado.refresh_from_db()
    curso_criado.tipo_publico = TipoPublico.COMUNITARIO
    with pytest.raises(ErroDeValidacao):
        curso_criado.save()


@pytest.mark.django_db
def test_cinco_palavras_chave_sao_cobradas_no_portao(curso_criado):
    """Cobrado no portao, e nao no formulario: a ficha salva pela metade de
    proposito, e quem escreveu so o resumo nao pode perder o que digitou por nao
    ter pensado em cinco palavras ainda."""
    curso_criado.palavras_chave = "robotica, sucata"
    curso_criado.save()
    faltas = validacoes.dados_do_curso(curso_criado)
    assert any("palavras-chave" in f for f in faltas)


@pytest.mark.django_db
def test_cinco_palavras_chave_completas_nao_sao_cobradas(curso_criado):
    """Prende o outro lado: sem este par, um append incondicional passaria."""
    curso_criado.palavras_chave = "robotica, sucata, reciclagem, motor, oficina"
    curso_criado.save()
    assert not any("palavras-chave" in f for f in validacoes.dados_do_curso(curso_criado))


@pytest.mark.django_db
def test_avaliacao_exige_ao_menos_um_anexo(curso_criado):
    """O entregavel e o MATERIAL de avaliacao (instrumento, roteiro de correcao,
    rubrica), e nao a nota de quem assiste, que e do modulo de execucao."""
    from apps.cursos.choices import TipoEntregavel

    avaliacao = curso_criado.entregaveis.get(tipo=TipoEntregavel.AVALIACAO)
    assert validacoes.pendencias(avaliacao) != []


@pytest.mark.django_db
def test_avaliacao_com_anexo_pode_ser_enviada(curso_criado, aluno, arquivo_qualquer):
    """Prende o outro lado: com anexo, a pendencia some."""
    from apps.cursos.choices import TipoEntregavel

    avaliacao = curso_criado.entregaveis.get(tipo=TipoEntregavel.AVALIACAO)
    anexa(avaliacao, aluno, arquivo_qualquer)
    assert validacoes.pendencias(avaliacao) == []


@pytest.mark.django_db
def test_avaliacao_aceita_link(curso_criado, aluno):
    """Aceita link, e nao so arquivo: um instrumento de avaliacao pode ser um
    formulario online, e exigir upload obrigaria a equipe a imprimir para anexar."""
    from apps.cursos.choices import TipoEntregavel, TipoMidia
    from apps.cursos.models import Anexo

    avaliacao = curso_criado.entregaveis.get(tipo=TipoEntregavel.AVALIACAO)
    Anexo.objects.create(
        entregavel=avaliacao, tipo_midia=TipoMidia.LINK,
        titulo="Formulário de avaliação", url="https://exemplo.ufsm.br/form",
        enviado_por=aluno,
    )
    assert validacoes.pendencias(avaliacao) == []


# --- O Plano de Ensino exige todas as secoes (a pedido) ----------------------


@pytest.mark.django_db
def test_plano_exige_todas_as_secoes(curso_criado):
    """Antes bastava UMA secao preenchida. O plano e o documento que descreve o
    curso inteiro: ementa sem metodologia, ou sem avaliacao, nao e plano."""
    from apps.cursos.choices import TipoEntregavel

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa escrita.</p>"
    secao.save()

    faltas = validacoes.pendencias(plano)
    assert any("Metodologia" in f for f in faltas)
    assert any("Avaliação" in f for f in faltas)
    # A que foi preenchida nao pode ser cobrada.
    assert not any(f.count(secao.titulo) and "Preencha" in f for f in faltas)


@pytest.mark.django_db
def test_plano_com_todas_as_secoes_nao_cobra_secao(curso_criado):
    """Prende o outro lado: com as sete escritas, a cobranca some."""
    from apps.cursos.choices import TipoEntregavel

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    for secao in plano.secoes.all():
        secao.conteudo = f"<p>Conteúdo de {secao.titulo}.</p>"
        secao.save()
    assert not any("Preencha" in f for f in validacoes.pendencias(plano))


@pytest.mark.django_db
def test_secao_so_com_marcacao_vazia_conta_como_vazia(curso_criado):
    """`<p></p>` nao e conteudo: o editor grava marcacao mesmo quando a pessoa nao
    escreveu nada, e comparar com string vazia deixaria o plano passar em branco."""
    from apps.cursos.choices import TipoEntregavel

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    for secao in plano.secoes.all():
        secao.conteudo = "<p></p>"
        secao.save()
    assert any("Preencha" in f for f in validacoes.pendencias(plano))


@pytest.mark.django_db
def test_plano_nao_exige_mais_anexo(curso_criado):
    """O plano deixou de ter materiais: a tela nao oferece anexar, entao cobrar
    anexo travaria o envio para sempre."""
    from apps.cursos.choices import TipoEntregavel

    plano = curso_criado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    assert not any("PDF" in f or "Anexe" in f for f in validacoes.pendencias(plano))
