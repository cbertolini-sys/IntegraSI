"""As guardas de view e o caminho de volta, decididos na auditoria do perfil
Professor.

P1: a fila de revisao so tinha `@login_required`. O filtro por
`professor_responsavel` fazia o aluno receber pagina vazia - protecao por
acidente de dado, que e o que `minhas_turmas` documenta como errado e corrigiu.

P4: as views que so delegavam a guarda ao servico passam a filtrar tambem. Isso
cria o caso que a CLAUDE.md descreve: duas guardas, um 403 so, e nenhum teste de
POST distingue qual esta valendo. A saida usada aqui e derrubar o SERVICO: se a
view recusa antes, vem 403; se nao recusa, vem o estouro do servico. E a unica
forma de a guarda da view responder sozinha.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel


@pytest.fixture
def curso_alheio(dados_curso, outro_professor, outro_aluno):
    """Curso de outro professor, com outro aluno na equipe."""
    dados = dict(dados_curso)
    dados["professor_responsavel"] = outro_professor
    curso = services.criar_curso(**dados)
    services.adicionar_membro(curso, outro_aluno, por=outro_professor)
    return curso


def explode(*args, **kwargs):
    raise RuntimeError("o serviço não devia ter sido chamado")


# --- P1: a fila e area de quem revisa -----------------------------------------


@pytest.mark.django_db
def test_o_aluno_nao_abre_a_fila_de_revisao(client, aluno):
    client.force_login(aluno)
    assert client.get(reverse("fila_revisao")).status_code == 403


@pytest.mark.django_db
def test_o_professor_continua_abrindo(client, professor):
    client.force_login(professor)
    assert client.get(reverse("fila_revisao")).status_code == 200


# --- P2: um nome so para a tela -----------------------------------------------


@pytest.mark.django_db
def test_a_fila_se_chama_como_o_cartao_que_leva_ate_ela(client, professor):
    """Tres nomes para a mesma tela: o cartao do painel, o titulo da pagina e o
    passo do fluxograma. Este teste prende os dois primeiros um ao outro, lendo o
    rotulo do proprio `_resumo` em vez de repeti-lo aqui."""
    from apps.contas.views import _resumo

    rotulo = next(i["rotulo"] for i in _resumo(professor) if i["url"] == "fila_revisao")
    client.force_login(professor)
    html = client.get(reverse("fila_revisao")).content.decode()
    assert f"<h1>{rotulo}</h1>" in html


# --- P3: a volta leva de onde a pessoa veio -----------------------------------


@pytest.fixture
def slides_em_revisao(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    slides.status = StatusEntregavel.EM_REVISAO
    slides.save(update_fields=["status", "atualizado_em"])
    return slides


@pytest.mark.django_db
def test_a_volta_leva_ao_entregavel_quando_veio_de_la(client, slides_em_revisao, professor):
    client.force_login(professor)
    html = client.get(
        reverse("revisar", args=[slides_em_revisao.pk]) + "?voltar=entregavel"
    ).content.decode()
    assert reverse("entregavel", args=[slides_em_revisao.pk]) in html
    assert "Voltar ao entregável" in html


@pytest.mark.django_db
def test_sem_parametro_a_volta_leva_a_fila(client, slides_em_revisao, professor):
    client.force_login(professor)
    html = client.get(reverse("revisar", args=[slides_em_revisao.pk])).content.decode()
    assert reverse("fila_revisao") in html


@pytest.mark.django_db
def test_valor_desconhecido_cai_na_fila(client, slides_em_revisao, professor):
    """Lista fechada, e nao o endereco que vier no parametro: refletir um valor de
    fora num `href` e como se abre um redirecionamento para qualquer lugar."""
    client.force_login(professor)
    html = client.get(
        reverse("revisar", args=[slides_em_revisao.pk]) + "?voltar=https://exemplo.org"
    ).content.decode()
    assert reverse("fila_revisao") in html
    assert "exemplo.org" not in html


@pytest.mark.django_db
def test_o_entregavel_manda_a_volta_no_link(client, slides_em_revisao, professor):
    """Prende as duas pontas: nao adianta a tela de revisao saber voltar se o
    caminho de ida nao diz de onde veio."""
    client.force_login(professor)
    html = client.get(reverse("entregavel", args=[slides_em_revisao.pk])).content.decode()
    assert reverse("revisar", args=[slides_em_revisao.pk]) + "?voltar=entregavel" in html


# --- P4: a view filtra, e nao so o servico ------------------------------------


@pytest.mark.django_db
def test_decidir_recusa_antes_de_chamar_o_servico(
    client, curso_alheio, professor, monkeypatch
):
    slides = curso_alheio.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    monkeypatch.setattr(services, "aprovar_entregavel", explode)
    monkeypatch.setattr(services, "devolver_entregavel", explode)
    monkeypatch.setattr(services, "reabrir_entregavel", explode)
    client.force_login(professor)
    resposta = client.post(
        reverse("decidir", args=[slides.pk]), {"decisao": "APROVAR", "comentario": "x"}
    )
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_enviar_recusa_antes_de_chamar_o_servico(
    client, curso_alheio, aluno, monkeypatch
):
    slides = curso_alheio.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    monkeypatch.setattr(services, "enviar_para_revisao", explode)
    client.force_login(aluno)
    assert client.post(reverse("enviar_entregavel", args=[slides.pk])).status_code == 403


@pytest.mark.django_db
def test_submeter_recusa_antes_de_chamar_o_servico(
    client, curso_alheio, professor, monkeypatch
):
    monkeypatch.setattr(services, "submeter_ao_coordenador", explode)
    client.force_login(professor)
    assert client.post(reverse("submeter_curso", args=[curso_alheio.pk])).status_code == 403


@pytest.mark.django_db
def test_quem_tem_direito_continua_passando(client, slides_em_revisao, professor):
    """O outro lado: a guarda nova nao pode fechar a porta de quem revisa."""
    client.force_login(professor)
    resposta = client.post(
        reverse("decidir", args=[slides_em_revisao.pk]),
        {"decisao": "APROVAR", "comentario": "<p>Ficou bom.</p>"},
        follow=True,
    )
    assert resposta.status_code == 200
    slides_em_revisao.refresh_from_db()
    assert slides_em_revisao.status == StatusEntregavel.APROVADO
