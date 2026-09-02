"""Quem produziu o curso, e quanto dele esta pronto.

A pagina publica nao dizia quem fez o curso: um curso de extensao e produzido por
uma equipe de estudantes, e o credito e parte do que a pagina publica. E a previa
nao dizia quanto falta - a equipe tinha que abrir os seis entregaveis, um a um,
para saber.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel


@pytest.fixture
def curso_em_producao(dados_curso, aluno, outro_aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    services.adicionar_membro(curso, outro_aluno, por=curso.professor_responsavel)
    return curso


def previa(client, curso):
    return client.get(reverse("previa_do_curso", args=[curso.pk])).content.decode()


def autoria(html):
    """So a secao de autoria.

    Afirmar sobre a pagina inteira nao serve: a barra do topo imprime o nome de
    quem esta logado, entao `professor.nome_completo in html` passava com a secao
    inexistente. Foi o que a primeira versao destes testes fez.
    """
    inicio = html.index('id="quem-produziu"')
    return html[inicio : html.index("</section>", inicio)]


# --- Autoria ------------------------------------------------------------------


@pytest.mark.django_db
def test_a_previa_mostra_o_responsavel_e_a_equipe_pelo_nome(
    client, curso_em_producao, aluno, outro_aluno, professor
):
    client.force_login(professor)
    bloco = autoria(previa(client, curso_em_producao))
    assert professor.nome_completo in bloco
    assert aluno.nome_completo in bloco
    assert outro_aluno.nome_completo in bloco


@pytest.mark.django_db
def test_o_responsavel_nao_aparece_duas_vezes(
    client, curso_em_producao, professor
):
    """Desde o Plano 6 o responsavel e membro da equipe do curso que responde, e
    listar `membros` cru imprimia o nome dele duas vezes na mesma tela."""
    client.force_login(professor)
    bloco = autoria(previa(client, curso_em_producao))
    assert bloco.count(professor.nome_completo) == 1


@pytest.mark.django_db
def test_a_autoria_nao_leva_dado_pessoal(
    client, curso_em_producao, aluno, professor
):
    """So o nome. E-mail, CPF, matricula e SIAPE nao tem o que fazer numa pagina
    que o publico le (spec 12)."""
    client.force_login(professor)
    html = previa(client, curso_em_producao)
    for dado in (aluno.email, professor.email, professor.siape):
        assert dado not in html, dado
    # E no proprio bloco, para o caso de a pagina passar a mostrar dado pessoal
    # so ali dentro no futuro.
    assert "@" not in autoria(html)


@pytest.mark.django_db
def test_a_pagina_publica_tambem_credita_quem_produziu(
    client, dados_curso, aluno, professor, coordenador
):
    """O credito nao e informacao de producao: e parte do que a escola le."""
    from apps.catalogo.tests.test_catalogo import publica

    curso = services.criar_curso(**dados_curso)
    publica(curso, aluno, professor, coordenador)
    bloco = autoria(client.get(reverse("catalogo_curso", args=[curso.pk])).content.decode())
    assert professor.nome_completo in bloco
    assert aluno.nome_completo in bloco


# --- Progresso ----------------------------------------------------------------


@pytest.mark.django_db
def test_curso_novo_esta_em_zero(curso_em_producao):
    p = curso_em_producao.progresso
    assert p.total == len(TipoEntregavel.values)
    assert p.prontos == 0
    assert p.revisados == 0
    assert p.percentual == 0


@pytest.mark.django_db
def test_revisados_conta_os_aprovados(curso_em_producao):
    """`revisados` e o status; `prontos` e a ausencia de pendencia. Sao medidas
    diferentes: um entregavel pode estar completo e ainda nao revisado."""
    curso_em_producao.entregaveis.filter(tipo=TipoEntregavel.SLIDES).update(
        status=StatusEntregavel.APROVADO
    )
    assert curso_em_producao.progresso.revisados == 1


@pytest.mark.django_db
def test_cem_por_cento_quando_nenhum_entregavel_tem_pendencia(
    curso_em_producao, monkeypatch
):
    """100% quer dizer material terminado: nenhum dos seis com pendencia."""
    from apps.cursos import validacoes

    monkeypatch.setattr(validacoes, "pendencias", lambda entregavel: [])
    p = curso_em_producao.progresso
    assert p.prontos == p.total
    assert p.percentual == 100


@pytest.mark.django_db
def test_o_percentual_acompanha_os_prontos(curso_em_producao, monkeypatch):
    from apps.cursos import validacoes

    prontos = {TipoEntregavel.SLIDES, TipoEntregavel.CARDS, TipoEntregavel.VIDEOS}
    monkeypatch.setattr(
        validacoes, "pendencias", lambda e: [] if e.tipo in prontos else ["falta algo"]
    )
    p = curso_em_producao.progresso
    assert p.prontos == 3
    assert p.percentual == 50


@pytest.mark.django_db
def test_o_cartao_de_progresso_fica_ao_lado_dos_entregaveis(
    client, curso_em_producao, professor
):
    """No painel do curso, que e onde a lista de entregaveis esta."""
    client.force_login(professor)
    html = client.get(reverse("curso", args=[curso_em_producao.pk])).content.decode()
    assert "Progresso da produção" in html
    assert "Progresso da revisão" in html
    assert "etapas prontas" in html
    assert "etapas revisadas" in html


@pytest.mark.django_db
def test_o_cartao_de_progresso_nao_vai_para_a_previa_nem_para_a_pagina_publica(
    client, dados_curso, aluno, professor, coordenador
):
    """A previa e a pagina publica vista por dentro. Ali o numero falaria de
    producao para quem foi ver o curso, e num curso publicado ele e 100% por
    definicao."""
    from apps.catalogo.tests.test_catalogo import publica

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    assert "Progresso da produção" not in previa(client, curso)

    # `publica` ja aloca o aluno na equipe; aloca-lo antes bateria na unicidade
    # de membro por curso.
    publica(curso, aluno, professor, coordenador)
    client.logout()
    html = client.get(reverse("catalogo_curso", args=[curso.pk])).content.decode()
    assert "Progresso da produção" not in html


@pytest.mark.django_db
def test_a_previa_nao_cresce_uma_consulta_por_membro(
    client, dados_curso, aluno, outro_aluno, professor
):
    """A autoria le `pessoa.nome_completo` de cada membro; sem prefetch e uma
    consulta por pessoa (o painel interno ja tinha aprendido isso)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    client.force_login(professor)
    with CaptureQueriesContext(connection) as com_um:
        previa(client, curso)
    services.adicionar_membro(curso, outro_aluno, por=professor)
    with CaptureQueriesContext(connection) as com_dois:
        previa(client, curso)
    assert len(com_dois) == len(com_um)


@pytest.mark.django_db
def test_o_painel_le_os_anexos_e_as_secoes_numa_consulta_so(
    client, dados_curso, aluno, professor
):
    """O cartao roda `pendencias` nos seis entregaveis, e a regra de cada um le
    anexos ou secoes.

    Contar consultas antes e depois de acrescentar anexos NAO prende isto: a conta
    e uma consulta por entregavel de qualquer jeito, com ou sem anexo, entao o
    numero nao muda e o teste passa com o prefetch apagado. Foi o que a primeira
    versao deste teste fez. O que separa os dois casos e QUANTAS consultas batem
    em cada tabela: uma, com o prefetch; seis, sem ele.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.cursos.models import Anexo, Secao

    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    client.force_login(professor)
    with CaptureQueriesContext(connection) as consultas:
        client.get(reverse("curso", args=[curso.pk]))

    for tabela in (Anexo._meta.db_table, Secao._meta.db_table):
        batidas = [c for c in consultas if tabela in c["sql"]]
        assert len(batidas) == 1, f"{tabela}: {len(batidas)} consultas"


# --- O cartao precisa dizer o que ele conta ------------------------------------


@pytest.mark.django_db
def test_cada_cartao_diz_o_que_conta(client, curso_em_producao, professor):
    """"Prontos 1 de 6" nao dizia prontos DE QUE, nem o que torna um pronto.

    O percentual e a divisao desses dois numeros, entao quem nao entende o que
    esta sendo contado tambem nao entende o percentual: um curso com o Plano de
    Ensino inteiro escrito mostra 17%, e o numero parece errado ate a pessoa
    descobrir que a conta e por etapa, e nao por trabalho feito.
    """
    client.force_login(professor)
    html = client.get(reverse("curso", args=[curso_em_producao.pk])).content.decode()
    for classe, legenda in (("producao", "etapas prontas"), ("revisao", "etapas revisadas")):
        inicio = html.index(f'cartao-progresso {classe}')
        cartao = html[inicio : html.index("</div>", inicio)]
        assert legenda in cartao, classe
        assert "de 6" in cartao, classe


@pytest.mark.django_db
def test_cada_cartao_explica_o_proprio_criterio(client, curso_em_producao, professor):
    """A explicacao vai no mesmo balao de ajuda do resto do sistema, e precisa
    dizer as duas coisas: pronto e ausencia de pendencia, revisado e aprovacao do
    professor. Sao medidas diferentes, e e por isso que sao dois numeros."""
    client.force_login(professor)
    html = client.get(reverse("curso", args=[curso_em_producao.pk])).content.decode()
    # Cada cartao explica o SEU criterio: separados, uma explicacao que falasse
    # dos dois deixaria de novo a duvida de qual numero e qual.
    for classe, palavra in (("producao", "pendência"), ("revisao", "aprov")):
        inicio = html.index(f'cartao-progresso {classe}')
        cartao = html[inicio : html.index("</div>", inicio)]
        assert 'class="ajuda-campo"' in cartao, classe
        ajuda = cartao[cartao.index("data-ajuda=") : cartao.index('"', cartao.index("data-ajuda=") + 12)]
        assert palavra in ajuda.lower(), classe


@pytest.mark.django_db
def test_a_pendencia_da_avaliacao_nao_fala_mais_em_link(curso_em_producao):
    """A mensagem mandava anexar "como arquivo ou link" num entregavel cujo
    formulario nao tem mais campo de link. Instrucao para um campo que a pessoa
    nao encontra e pior que nenhuma - a mesma licao que a mensagem do
    `AnexoForm.clean()` ja tinha aprendido."""
    from apps.cursos import validacoes
    from apps.cursos.choices import TipoEntregavel

    avaliacao = curso_em_producao.entregaveis.get(tipo=TipoEntregavel.AVALIACAO)
    faltas = validacoes.pendencias(avaliacao)
    assert faltas, "a avaliação vazia precisa continuar sendo pendência"
    assert "link" not in " ".join(faltas).lower()


# --- Producao e revisao viram dois cartoes -------------------------------------


@pytest.mark.django_db
def test_o_progresso_da_revisao_tem_percentual_proprio(curso_em_producao):
    """Somados num cartao so, os dois numeros passavam por medidas do mesmo
    fenomeno. Nao sao: da para ter tudo pronto e nada revisado."""
    curso_em_producao.entregaveis.filter(
        tipo__in=[TipoEntregavel.SLIDES, TipoEntregavel.CARDS, TipoEntregavel.VIDEOS]
    ).update(status=StatusEntregavel.APROVADO)
    p = curso_em_producao.progresso
    assert p.revisados == 3
    assert p.percentual_revisado == 50


@pytest.mark.django_db
def test_o_percentual_de_revisao_e_zero_num_curso_sem_entregavel():
    """Divisao por zero: `total` vem de uma consulta, e um curso sem entregavel e
    estado alcancavel (uma migracao, um comando). O da producao ja se protegia."""
    from apps.cursos.models.curso import Progresso

    assert Progresso(total=0, prontos=0, revisados=0).percentual_revisado == 0


@pytest.mark.django_db
def test_a_tela_traz_os_dois_cartoes_separados(client, curso_em_producao, professor):
    client.force_login(professor)
    html = client.get(reverse("curso", args=[curso_em_producao.pk])).content.decode()
    assert "Progresso da produção" in html
    assert "Progresso da revisão" in html
    assert html.count("cartao-progresso") == 2


@pytest.mark.django_db
def test_cada_barra_mede_o_proprio_numero(client, curso_em_producao, professor):
    """Duas barras com o mesmo `value` seria pior que uma: pareceriam dois dados
    e seriam o mesmo."""
    import re

    curso_em_producao.entregaveis.filter(tipo=TipoEntregavel.SLIDES).update(
        status=StatusEntregavel.APROVADO
    )
    client.force_login(professor)
    html = client.get(reverse("curso", args=[curso_em_producao.pk])).content.decode()
    valores = re.findall(r'<progress class="barra-progresso" value="(\d+)"', html)
    assert valores == ["0", "1"], valores  # nada pronto, um revisado


# --- A equipe precisa de porta ------------------------------------------------


@pytest.mark.django_db
def test_o_cartao_de_equipe_leva_a_tela_de_gerir(client, curso_em_producao, professor):
    """A tela de equipe existia, com alocar e remover, e NENHUM template linkava
    para ela: quem quisesse acrescentar um aluno tinha que digitar a URL."""
    client.force_login(professor)
    html = client.get(reverse("curso", args=[curso_em_producao.pk])).content.decode()
    assert reverse("equipe", args=[curso_em_producao.pk]) in html


@pytest.mark.django_db
def test_quem_nao_gere_a_equipe_nao_ve_o_botao(client, curso_em_producao, aluno):
    """`pode_gerir_equipe` e do professor responsavel e da coordenacao. O aluno da
    equipe ve o cartao e nao ve o botao - e a decisao fica no Python, nao num
    `{% if %}` de papel no template (spec 10)."""
    client.force_login(aluno)
    html = client.get(reverse("curso", args=[curso_em_producao.pk])).content.decode()
    assert "Equipe" in html
    assert reverse("equipe", args=[curso_em_producao.pk]) not in html


# --- CSS: espaco que mora no componente, e nao no contexto ---------------------


def test_o_gatilho_de_ajuda_carrega_o_proprio_espaco():
    """O `?` colava no título dos cartões de progresso.

    O espaço dele existia numa regra presa a UM contexto,
    `.bloco > h3 .ajuda-campo`, então o `<h2>` do cartão de progresso não casava e
    o círculo nascia grudado. Qualquer contexto novo nasceria assim também.

    `.obrigatorio` já fazia certo ao lado: margem na regra base e ajuste por
    contexto. Este teste lê o CSS porque espaçamento não aparece no HTML, e o
    defeito é invisível para a suíte.
    """
    from pathlib import Path

    from django.conf import settings

    css = (Path(settings.BASE_DIR) / "static" / "css" / "integrasi.css").read_text(
        encoding="utf-8"
    )
    inicio = css.index(".ajuda-campo {")
    base = css[inicio : css.index("}", inicio)]
    assert "margin-left" in base, (
        "o espaço do gatilho voltou a depender do contexto; ponha-o na regra base"
    )


@pytest.mark.django_db
def test_os_cartoes_do_painel_do_curso_sao_section_com_h3(
    client, curso_em_producao, professor
):
    """O painel do curso ficou de fora da rodada que uniformizou os entregáveis:
    continuava com `<div class="bloco">` e `<h2>`.

    Não era defeito visual - `.bloco > h2` e `.bloco > h3` são desenhados igual -,
    mas é a mesma estrutura descrita de dois jeitos em duas telas vizinhas, e a
    próxima regra escrita para uma delas passa a valer só para metade.
    """
    client.force_login(professor)
    html = client.get(reverse("curso", args=[curso_em_producao.pk])).content.decode()
    corpo = html[html.index("corpo-trabalho") : html.index("<aside")]
    assert '<div class="bloco"' not in corpo
    assert "<h2" not in corpo
    assert corpo.count('class="bloco"') >= 1
