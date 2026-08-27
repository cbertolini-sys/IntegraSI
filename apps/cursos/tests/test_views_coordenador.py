import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel


@pytest.fixture
def curso_submetido(dados_curso, aluno, professor):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    return curso


@pytest.mark.django_db
def test_professor_submete_pela_tela(client, dados_curso, aluno, professor):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    client.force_login(professor)
    resposta = client.post(reverse("submeter_curso", args=[curso.pk]), follow=True)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.AGUARDANDO_COORDENADOR
    assert "Curso enviado para aprovação da coordenação." in resposta.content.decode()


@pytest.mark.django_db
def test_submeter_curso_via_get_e_rejeitado(client, dados_curso, aluno, professor):
    # A mesma vulnerabilidade que test_enviar_entregavel_via_get_e_rejeitado crava
    # em apps/cursos/tests/test_views_aluno.py: sem @require_POST, um GET (fora do
    # alcance da protecao CSRF) bastava para submeter o curso a coordenacao.
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    client.force_login(professor)
    resposta = client.get(reverse("submeter_curso", args=[curso.pk]))
    assert resposta.status_code == 405
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO


@pytest.mark.django_db
def test_fila_da_coordenacao_lista_o_curso(client, coordenador, curso_submetido):
    client.force_login(coordenador)
    resposta = client.get(reverse("fila_coordenacao"))
    conteudo = resposta.content.decode()
    assert curso_submetido.titulo in conteudo
    assert "Cursos aguardando aprovação" in conteudo


@pytest.mark.django_db
def test_fila_da_coordenacao_vazia_mostra_mensagem(client, coordenador):
    client.force_login(coordenador)
    resposta = client.get(reverse("fila_coordenacao"))
    assert "Nenhum curso aguardando aprovação." in resposta.content.decode()


@pytest.mark.django_db
def test_professor_nao_entra_na_fila_da_coordenacao(client, professor, curso_submetido):
    client.force_login(professor)
    resposta = client.get(reverse("fila_coordenacao"))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_fila_da_coordenacao_exclui_curso_em_outro_status(
    client, coordenador, professor, aluno, dados_curso, curso_submetido
):
    # A unica coisa que os testes anteriores provam e que o curso certo aparece.
    # Um filtro que virasse "todos os cursos" (ou perdesse o status=) passaria em
    # todos eles sem ser notado - este teste crava a exclusao, nao so a inclusao.
    # EM_PRODUCAO e o falso positivo realista: e o estado de todo curso com equipe
    # montada que ainda nao foi submetido. PUBLICADO cobre a outra ponta: um curso
    # que ja passou pela fila nao deveria voltar a aparecer nela.
    em_producao = services.criar_curso(**{**dados_curso, "titulo": "Robótica com Sucata"})
    services.adicionar_membro(em_producao, aluno, por=professor)
    assert em_producao.status == StatusCurso.EM_PRODUCAO

    publicado = services.criar_curso(**{**dados_curso, "titulo": "Iniciação a Python"})
    services.adicionar_membro(publicado, aluno, por=professor)
    publicado.entregaveis.update(status=StatusEntregavel.APROVADO)
    publicado.refresh_from_db()
    services.submeter_ao_coordenador(publicado, por=professor)
    services.publicar_curso(publicado, por=coordenador)
    assert publicado.status == StatusCurso.PUBLICADO

    client.force_login(coordenador)
    resposta = client.get(reverse("fila_coordenacao"))
    conteudo = resposta.content.decode()
    assert curso_submetido.titulo in conteudo
    assert em_producao.titulo not in conteudo
    assert publicado.titulo not in conteudo


@pytest.mark.django_db
def test_professor_nao_acessa_a_analise(client, professor, curso_submetido):
    client.force_login(professor)
    resposta = client.get(reverse("analisar_curso", args=[curso_submetido.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_publicar_pela_tela(client, coordenador, curso_submetido):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("decidir_curso", args=[curso_submetido.pk]), {"decisao": "PUBLICAR"}, follow=True
    )
    curso_submetido.refresh_from_db()
    assert curso_submetido.status == StatusCurso.PUBLICADO
    assert "Curso publicado no catálogo." in resposta.content.decode()


@pytest.mark.django_db
def test_devolver_pela_tela(client, coordenador, curso_submetido):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("decidir_curso", args=[curso_submetido.pk]),
        {"decisao": "DEVOLVER", "comentario": "Falta revisar a bibliografia."},
        follow=True,
    )
    curso_submetido.refresh_from_db()
    assert curso_submetido.status == StatusCurso.DEVOLVIDO
    assert "Curso devolvido ao professor." in resposta.content.decode()


@pytest.mark.django_db
def test_devolver_sem_comentario_e_barrado(client, coordenador, curso_submetido):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("decidir_curso", args=[curso_submetido.pk]),
        {"decisao": "DEVOLVER", "comentario": ""},
        follow=True,
    )
    conteudo = resposta.content.decode()
    # count == 1, nao apenas "in": base.html ja renderiza messages globalmente
    # desde o Plano 1 (R50). Um {% for mensagem in messages %} deixado no
    # template de analisar_curso.html - como o rascunho do brief trazia -
    # duplicaria esta mensagem, o mesmo defeito que uma tela do Plano 2 teve.
    assert conteudo.count("Escreva o que precisa ser corrigido") == 1
    curso_submetido.refresh_from_db()
    assert curso_submetido.status == StatusCurso.AGUARDANDO_COORDENADOR


@pytest.mark.django_db
def test_decidir_curso_via_get_e_rejeitado(client, coordenador, curso_submetido):
    # Mesmo raciocinio de test_submeter_curso_via_get_e_rejeitado: decidir_curso
    # muda o status do curso e precisa ficar fora do alcance de um GET.
    client.force_login(coordenador)
    resposta = client.get(reverse("decidir_curso", args=[curso_submetido.pk]))
    assert resposta.status_code == 405
    curso_submetido.refresh_from_db()
    assert curso_submetido.status == StatusCurso.AGUARDANDO_COORDENADOR


@pytest.mark.django_db
def test_professor_nao_decide_pela_tela(client, professor, curso_submetido):
    client.force_login(professor)
    resposta = client.post(
        reverse("decidir_curso", args=[curso_submetido.pk]), {"decisao": "PUBLICAR"}
    )
    assert resposta.status_code == 403
    curso_submetido.refresh_from_db()
    assert curso_submetido.status == StatusCurso.AGUARDANDO_COORDENADOR


@pytest.mark.django_db
def test_analise_mostra_todos_os_entregaveis(client, coordenador, curso_submetido):
    client.force_login(coordenador)
    resposta = client.get(reverse("analisar_curso", args=[curso_submetido.pk]))
    assert resposta.content.decode().count("entregavel-analise") == 5
