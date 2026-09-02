"""O historico das decisoes, e a volta atras de uma aprovacao.

`Revisao` guarda cada decisao desde o Plano 2 e a spec 4.6 a chama de historico
das idas e vindas. Ate agora ele nao aparecia em tela nenhuma: aprovar com um
comentario gravava o comentario e ninguem mais o via, o que na pratica e o mesmo
que nao poder comentar.

E uma aprovacao era definitiva enquanto o curso ainda estava em producao. O
professor que aprovasse cedo demais nao tinha volta - `_exige_em_revisao` recusa
qualquer decisao fora de EM_REVISAO.
"""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel
from apps.cursos.models import Revisao


@pytest.fixture
def slides_aprovados(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    slides.status = StatusEntregavel.EM_REVISAO
    slides.save(update_fields=["status", "atualizado_em"])
    services.aprovar_entregavel(slides, por=professor, comentario="<p>Ficou bom.</p>")
    return slides


# --- comentario obrigatorio em toda decisao -----------------------------------


@pytest.mark.django_db
def test_aprovar_exige_comentario(dados_curso, professor, aluno):
    """Devolver ja exigia; aprovar aceitava vazio, e o registro nascia mudo.
    O historico so serve se cada linha dele disser alguma coisa."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    slides.status = StatusEntregavel.EM_REVISAO
    slides.save(update_fields=["status", "atualizado_em"])

    with pytest.raises(ValidationError, match="omentário"):
        services.aprovar_entregavel(slides, por=professor, comentario="   ")
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.EM_REVISAO


# --- reabrir ------------------------------------------------------------------


@pytest.mark.django_db
def test_reabrir_devolve_o_entregavel_para_a_equipe(slides_aprovados, professor):
    services.reabrir_entregavel(
        slides_aprovados, por=professor, comentario="<p>Faltou a aula 3.</p>"
    )
    slides_aprovados.refresh_from_db()
    assert slides_aprovados.status == StatusEntregavel.DEVOLVIDO
    assert slides_aprovados.editavel


@pytest.mark.django_db
def test_reabrir_grava_a_propria_decisao_no_historico(slides_aprovados, professor):
    """Nao e "devolvido": devolver responde a um envio, reabrir desfaz uma
    aprovacao. Quem le o historico precisa distinguir os dois."""
    services.reabrir_entregavel(slides_aprovados, por=professor, comentario="Faltou algo.")
    ultima = slides_aprovados.revisoes.last()
    assert ultima.decisao == Revisao.REABERTO
    assert ultima.revisor == professor


@pytest.mark.django_db
def test_reabrir_exige_comentario(slides_aprovados, professor):
    # `match` na palavra da mensagem de REABRIR: "Escreva por que está reabrindo
    # o entregável." Ancorar em "comentário" casaria com a mensagem de aprovar e
    # com a de devolver, e o teste passaria mesmo com a guarda errada disparando.
    with pytest.raises(ValidationError, match="reabrindo"):
        services.reabrir_entregavel(slides_aprovados, por=professor, comentario="")
    slides_aprovados.refresh_from_db()
    assert slides_aprovados.status == StatusEntregavel.APROVADO


@pytest.mark.django_db
def test_so_reabre_o_que_esta_aprovado(dados_curso, professor, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    with pytest.raises(ValidationError, match="aprovado"):
        services.reabrir_entregavel(slides, por=professor, comentario="Qualquer coisa.")


@pytest.mark.django_db
def test_nao_reabre_depois_de_o_curso_subir(slides_aprovados, professor):
    """O curso ja saiu das maos da equipe: mexer num entregavel agora mudaria por
    baixo o material que a coordenacao esta analisando."""
    curso = slides_aprovados.curso
    curso.status = StatusCurso.AGUARDANDO_COORDENADOR
    curso.save(update_fields=["status"])
    with pytest.raises(ValidationError, match="coordenação"):
        services.reabrir_entregavel(slides_aprovados, por=professor, comentario="Faltou.")


@pytest.mark.django_db
def test_so_quem_revisa_reabre(slides_aprovados, aluno):
    with pytest.raises(PermissionDenied):
        services.reabrir_entregavel(slides_aprovados, por=aluno, comentario="Faltou.")


# --- o historico na tela ------------------------------------------------------


@pytest.mark.django_db
def test_a_tela_mostra_as_decisoes_anteriores(client, slides_aprovados, professor):
    client.force_login(professor)
    html = client.get(reverse("revisar", args=[slides_aprovados.pk])).content.decode()
    assert "Ficou bom." in html
    assert professor.nome_completo in html
    assert "Aprovado" in html


@pytest.mark.django_db
def test_o_historico_vem_do_mais_novo_para_o_mais_antigo(
    client, slides_aprovados, professor
):
    services.reabrir_entregavel(slides_aprovados, por=professor, comentario="Faltou a aula 3.")
    client.force_login(professor)
    html = client.get(reverse("revisar", args=[slides_aprovados.pk])).content.decode()
    assert html.index("Faltou a aula 3.") < html.index("Ficou bom.")


@pytest.mark.django_db
def test_o_botao_de_reabrir_aparece_no_aprovado(client, slides_aprovados, professor):
    client.force_login(professor)
    html = client.get(reverse("revisar", args=[slides_aprovados.pk])).content.decode()
    assert 'value="REABRIR"' in html
    assert 'value="APROVAR"' not in html


@pytest.mark.django_db
def test_o_botao_de_reabrir_some_com_o_curso_na_coordenacao(
    client, slides_aprovados, professor
):
    curso = slides_aprovados.curso
    curso.status = StatusCurso.AGUARDANDO_COORDENADOR
    curso.save(update_fields=["status"])
    client.force_login(professor)
    html = client.get(reverse("revisar", args=[slides_aprovados.pk])).content.decode()
    assert 'value="REABRIR"' not in html


@pytest.mark.django_db
def test_reabrir_pela_tela(client, slides_aprovados, professor):
    client.force_login(professor)
    resposta = client.post(
        reverse("decidir", args=[slides_aprovados.pk]),
        {"decisao": "REABRIR", "comentario": "<p>Faltou a aula 3.</p>"},
        follow=True,
    )
    assert resposta.status_code == 200
    slides_aprovados.refresh_from_db()
    assert slides_aprovados.status == StatusEntregavel.DEVOLVIDO


@pytest.mark.django_db
def test_a_equipe_ve_o_motivo_da_reabertura(client, slides_aprovados, professor, aluno):
    """A devolutiva na tela da equipe olhava so por DEVOLVIDO: uma reabertura
    passaria calada, e o entregavel voltaria a ser editavel sem ninguem dizer
    por que."""
    services.reabrir_entregavel(
        slides_aprovados, por=professor, comentario="<p>Faltou a aula 3.</p>"
    )
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[slides_aprovados.pk])).content.decode()
    assert "Faltou a aula 3." in html


@pytest.mark.django_db
def test_a_tela_diz_que_o_comentario_e_obrigatorio(client, slides_aprovados, professor):
    """O servico ja recusava vazio ao devolver, e a tela nao avisava: a pessoa
    escrevia a decisao inteira para descobrir depois."""
    client.force_login(professor)
    html = client.get(reverse("revisar", args=[slides_aprovados.pk])).content.decode()
    campo = html[html.index('class="campo"') : html.index("acoes-empilhadas")]
    assert 'class="obrigatorio"' in campo
    assert "required" in campo
