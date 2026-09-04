from unittest import mock

import pytest
from django.core.exceptions import ValidationError

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel
from apps.cursos.models import Entregavel, Secao


@pytest.mark.django_db
def test_criar_curso_gera_os_cinco_entregaveis(dados_curso):
    curso = services.criar_curso(**dados_curso)
    tipos = list(curso.entregaveis.values_list("tipo", flat=True))
    assert sorted(tipos) == sorted([t.value for t in TipoEntregavel])
    assert all(e.status == StatusEntregavel.RASCUNHO for e in curso.entregaveis.all())


@pytest.mark.django_db
def test_criar_curso_gera_as_secoes_do_plano_de_ensino(dados_curso):
    # Titulos hardcoded, nao lidos de services.SECOES_PLANO_ENSINO: essa constante
    # e o que o codigo popula a partir dela, entao compara-la consigo mesma nunca
    # falharia se alguem desacentuasse ou reordenasse a lista.
    titulos_esperados = [
        "Ementa",
        "Objetivos",
        "Conteúdo programático",
        "Metodologia",
        "Cronograma",
        "Avaliação",
        "Referências",
    ]
    curso = services.criar_curso(**dados_curso)
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    titulos = list(plano.secoes.order_by("ordem").values_list("titulo", flat=True))
    assert titulos == titulos_esperados
    assert all(secao.conteudo == "" for secao in plano.secoes.all())


@pytest.mark.django_db
def test_apenas_o_plano_de_ensino_nasce_com_secoes(dados_curso):
    curso = services.criar_curso(**dados_curso)
    outros = curso.entregaveis.exclude(tipo=TipoEntregavel.PLANO_ENSINO)
    assert Secao.objects.filter(entregavel__in=outros).count() == 0


@pytest.mark.django_db
def test_adicionar_o_primeiro_membro_leva_o_curso_para_producao(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    assert curso.status == StatusCurso.RASCUNHO
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO


@pytest.mark.django_db
def test_adicionar_membro_nao_revalida_o_curso_inteiro(dados_curso, aluno):
    """curso.save() sem update_fields chama full_clean() sobre o Curso inteiro
    (docs/onde-mora-a-validacao.md); se um curso ja aprovado tiver ficado invalido
    por outro caminho (o proprio full_clean, por exemplo, permite formato="" so via
    .update(), que contorna a validacao), adicionar_membro nao pode falhar por causa
    disso - a troca de equipe nao tem nada a ver com o campo quebrado, e o usuario
    nao teria como entender o erro (item 5 da revisao de branco)."""
    from apps.cursos.models import Curso

    curso = services.criar_curso(**dados_curso)
    Curso.objects.filter(pk=curso.pk).update(formato="")
    curso.refresh_from_db()

    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)

    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO
    assert curso.formato == ""


@pytest.mark.django_db
def test_entregavel_repetido_no_mesmo_curso_e_recusado(dados_curso):
    curso = services.criar_curso(**dados_curso)
    with pytest.raises(ValidationError):
        Entregavel.objects.create(curso=curso, tipo=TipoEntregavel.SLIDES)


@pytest.mark.django_db
def test_conteudo_da_secao_e_sanitizado(dados_curso):
    curso = services.criar_curso(**dados_curso)
    secao = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO).secoes.first()
    secao.conteudo = "<p>Texto</p><script>alert(1)</script>"
    secao.save()
    secao.refresh_from_db()
    assert "<p>Texto</p>" in secao.conteudo
    assert "script" not in secao.conteudo


@pytest.mark.django_db
def test_sanitizacao_roda_mesmo_com_update_fields(dados_curso):
    """A sanitizacao nao pode viver dentro do guarda do update_fields: um save
    direcionado e exatamente o caminho que um form de edicao rapida usaria, e e
    o caminho que mais precisa ficar seguro contra script no navegador."""
    curso = services.criar_curso(**dados_curso)
    secao = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO).secoes.first()
    secao.conteudo = "<p>Texto</p><script>alert(1)</script>"
    secao.save(update_fields=["conteudo"])
    secao.refresh_from_db()
    assert "<p>Texto</p>" in secao.conteudo
    assert "script" not in secao.conteudo


@pytest.mark.django_db
def test_sanitizacao_remove_atributos_perigosos_e_tags_nao_permitidas(dados_curso):
    """<script> nao e o unico vetor: handlers de evento, href com esquema
    javascript:, style inline e tags fora do allowlist tambem executam script
    no navegador de quem le. Task 10 renderiza Secao.conteudo com |safe no
    template do professor, entao este allowlist e a unica barreira - e a
    marcacao legitima ao redor precisa sobreviver, senao o teste passaria so
    porque tudo foi apagado."""
    curso = services.criar_curso(**dados_curso)
    secao = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO).secoes.first()
    secao.conteudo = (
        '<p onclick="alert(1)">Texto</p>'
        '<img src="x" onerror="alert(2)">'
        '<p onmouseover="alert(3)">Outro</p>'
        '<a href="javascript:alert(4)">link</a>'
        '<p style="background:url(javascript:alert(5))">Estilizado</p>'
    )
    secao.save()
    secao.refresh_from_db()
    conteudo = secao.conteudo

    # vetores perigosos removidos
    assert "onclick" not in conteudo
    assert "onerror" not in conteudo
    assert "onmouseover" not in conteudo
    assert "javascript:" not in conteudo
    assert "style=" not in conteudo
    assert "<img" not in conteudo

    # marcacao legitima ao redor sobrevive
    assert "<p>Texto</p>" in conteudo
    assert "<p>Outro</p>" in conteudo
    assert "<p>Estilizado</p>" in conteudo
    assert "<a" in conteudo and "link</a>" in conteudo


@pytest.mark.django_db
def test_criar_curso_recusa_dados_invalidos(dados_curso):
    """Renomeado: isto prova que a validacao do Curso barra dados invalidos,
    nao que o servico e atomico - o Curso falha antes de qualquer Entregavel
    existir, entao nao ha rollback nenhum para provar aqui."""
    dados_curso["carga_horaria"] = 0
    from apps.cursos.models import Curso

    with pytest.raises(ValidationError):
        services.criar_curso(**dados_curso)
    assert Curso.objects.count() == 0
    assert Entregavel.objects.count() == 0


@pytest.mark.django_db
def test_criar_curso_e_atomico(dados_curso):
    """Forca uma falha no meio do laco de criacao dos entregaveis (na terceira
    chamada a Entregavel.objects.create, depois que o Plano de Ensino e suas
    sete secoes ja existem em memoria de transacao) e prova que nada disso
    sobrevive: nem o curso, nem os entregaveis parciais, nem as secoes."""
    from apps.cursos.models import Curso

    original_create = Entregavel.objects.create

    def falha_na_terceira_chamada(*args, **kwargs):
        if falha_na_terceira_chamada.chamadas == 2:
            raise RuntimeError("falha simulada no meio do laco de criacao")
        falha_na_terceira_chamada.chamadas += 1
        return original_create(*args, **kwargs)

    falha_na_terceira_chamada.chamadas = 0

    with mock.patch.object(Entregavel.objects, "create", side_effect=falha_na_terceira_chamada):
        with pytest.raises(RuntimeError):
            services.criar_curso(**dados_curso)

    assert Curso.objects.count() == 0
    assert Entregavel.objects.count() == 0
    assert Secao.objects.count() == 0


@pytest.mark.django_db
def test_responsavel_entra_na_equipe_ao_criar(dados_curso, professor):
    """Ser responsavel e formalidade que atribui a revisao, e nao dispensa de
    produzir (spec 4.1): ele e membro do curso que responde."""
    curso = services.criar_curso(**dados_curso)
    assert curso.tem_membro(professor)


@pytest.mark.django_db
def test_curso_recem_criado_continua_em_rascunho(dados_curso):
    """O responsavel na equipe nao pode tirar o curso do rascunho: proposta com
    uma pessoa so ainda e proposta. Se isto falhar, alguem trocou a escrita direta
    do MembroEquipe por adicionar_membro, que transiciona o status."""
    curso = services.criar_curso(**dados_curso)
    assert curso.status == StatusCurso.RASCUNHO


@pytest.mark.django_db
def test_primeiro_aluno_alocado_tira_o_curso_do_rascunho(dados_curso, professor, aluno):
    """Prende o outro lado do teste acima: a transicao continua existindo, so
    mudou de gatilho - e o primeiro membro alem do responsavel."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO


@pytest.mark.django_db
def test_proposta_nasce_so_com_titulo(edicao, professor):
    """Spec 4.3: o professor abre o trabalho, a equipe preenche a ficha."""
    curso = services.criar_curso(titulo="Robotica com sucata", professor_responsavel=professor)
    assert curso.pk is not None
    assert curso.edicao == edicao
    assert curso.resumo == ""
    assert curso.carga_horaria is None


@pytest.mark.django_db
def test_proposta_sem_edicao_aberta_e_criada(professor, db):
    """Proposta se faz a qualquer momento, por qualquer professor. Ela nao depende
    de a coordenacao ter lembrado de abrir a edicao corrente.

    `abrir_nova_versao` ja se recusava a depender disso, com todas as letras no
    comentario dele. A criacao dependia, e o resultado foi o sistema inteiro
    travado para todo professor na instalacao nova, ate alguem abrir uma edicao
    pelo Admin. A edicao e rotulo de catalogo (spec 4.1), e rotulo nao tranca
    porta."""
    from apps.edicoes.models import Edicao

    Edicao.objects.filter(ativa=True).update(ativa=False)
    curso = services.criar_curso(titulo="Robotica com sucata", professor_responsavel=professor)
    assert curso.pk is not None
    assert curso.edicao is None


# --- Seis entregaveis, numerados (a pedido) ----------------------------------


@pytest.mark.django_db
def test_criar_curso_gera_os_seis_entregaveis(dados_curso):
    curso = services.criar_curso(**dados_curso)
    assert curso.entregaveis.count() == 6
    assert curso.entregaveis.filter(tipo=TipoEntregavel.AVALIACAO).exists()


@pytest.mark.django_db
def test_os_valores_gravados_nao_mudaram(dados_curso):
    """A renumeracao mexeu no rotulo, e nao no valor. Trocar o valor faria toda
    linha ja gravada virar lixo, e e regra do projeto nunca fazer isso."""
    curso = services.criar_curso(**dados_curso)
    assert set(curso.entregaveis.values_list("tipo", flat=True)) == {
        "PLANO_ENSINO", "SLIDES", "VIDEOS", "CARDS", "CADERNO", "AVALIACAO",
    }


@pytest.mark.django_db
def test_curso_so_vai_a_coordenacao_com_os_seis_aprovados(dados_curso):
    """A contagem vem de len(TipoEntregavel.values), entao passou de cinco para
    seis sozinha. Este teste e o que prova que passou."""
    from apps.cursos.choices import StatusEntregavel

    curso = services.criar_curso(**dados_curso)
    curso.entregaveis.exclude(tipo=TipoEntregavel.AVALIACAO).update(
        status=StatusEntregavel.APROVADO
    )
    assert curso.pronto_para_o_coordenador is False

    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    assert curso.pronto_para_o_coordenador is True


@pytest.mark.django_db
def test_descricao_do_anexo_e_sanitizada(dados_curso, aluno):
    """A descricao passou a ser escrita num editor rico e renderizada com |safe na
    lista de materiais. Sem esta sanitizacao ela e o segundo caminho para script
    no navegador de quem le - o primeiro, `Secao.conteudo`, ja esta fechado."""
    from apps.cursos.choices import TipoMidia
    from apps.cursos.models import Anexo

    curso = services.criar_curso(**dados_curso)
    anexo = Anexo(
        entregavel=curso.entregaveis.get(tipo=TipoEntregavel.SLIDES),
        tipo_midia=TipoMidia.LINK,
        titulo="Aula 1",
        descricao='<p>Texto</p><script>alert(1)</script><img src="x" onerror="alert(2)">',
        url="https://exemplo.org/a",
        enviado_por=aluno,
    )
    anexo.save()
    anexo.refresh_from_db()
    assert "<p>Texto</p>" in anexo.descricao
    assert "script" not in anexo.descricao
    assert "onerror" not in anexo.descricao


@pytest.mark.django_db
def test_sanitizacao_da_descricao_roda_mesmo_com_update_fields(dados_curso, aluno):
    """Pelo mesmo motivo da secao: o save direcionado e o caminho de uma edicao
    rapida, e e o que mais precisa ficar seguro."""
    from apps.cursos.choices import TipoMidia
    from apps.cursos.models import Anexo

    curso = services.criar_curso(**dados_curso)
    anexo = Anexo.objects.create(
        entregavel=curso.entregaveis.get(tipo=TipoEntregavel.SLIDES),
        tipo_midia=TipoMidia.LINK,
        titulo="Aula 1",
        url="https://exemplo.org/a",
        enviado_por=aluno,
    )
    anexo.descricao = "<p>Texto</p><script>alert(1)</script>"
    anexo.save(update_fields=["descricao"])
    anexo.refresh_from_db()
    assert "<p>Texto</p>" in anexo.descricao
    assert "script" not in anexo.descricao
