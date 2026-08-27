import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel
from apps.cursos.models import Curso, LogTransicaoCurso


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


# --- despublicar e republicar pela tela ---------------------------------------


@pytest.fixture
def curso_publicado(curso_submetido, coordenador):
    services.publicar_curso(curso_submetido, por=coordenador)
    curso_submetido.refresh_from_db()
    return curso_submetido


@pytest.fixture
def curso_despublicado(curso_publicado, coordenador):
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Material desatualizado.")
    curso_publicado.refresh_from_db()
    return curso_publicado


@pytest.mark.django_db
def test_despublicar_pela_tela(client, coordenador, curso_publicado):
    """despublicar_curso existia desde a Task 3 e nao tinha nenhum chamador de
    producao: a tela do coordenador so oferecia Publicar e Devolver, e a unica
    forma de tirar um curso do catalogo era o shell (achado Importante 2)."""
    client.force_login(coordenador)
    resposta = client.post(
        reverse("decidir_curso", args=[curso_publicado.pk]),
        {"decisao": "DESPUBLICAR", "comentario": "Material desatualizado."},
        follow=True,
    )
    curso_publicado.refresh_from_db()
    assert curso_publicado.status == StatusCurso.DESPUBLICADO
    assert "Curso retirado do catálogo." in resposta.content.decode()


@pytest.mark.django_db
def test_despublicar_sem_motivo_e_barrado(client, coordenador, curso_publicado):
    """Espelha test_devolver_sem_comentario_e_barrado: o motivo obrigatorio do
    servico precisa chegar a tela como mensagem, uma vez so (base.html ja
    renderiza messages globalmente)."""
    client.force_login(coordenador)
    resposta = client.post(
        reverse("decidir_curso", args=[curso_publicado.pk]),
        {"decisao": "DESPUBLICAR", "comentario": ""},
        follow=True,
    )
    assert resposta.content.decode().count("Informe o motivo da despublicação.") == 1
    curso_publicado.refresh_from_db()
    assert curso_publicado.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_republicar_pela_tela(client, coordenador, curso_despublicado):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("decidir_curso", args=[curso_despublicado.pk]), {"decisao": "PUBLICAR"}, follow=True
    )
    curso_despublicado.refresh_from_db()
    assert curso_despublicado.status == StatusCurso.PUBLICADO
    assert "Curso publicado no catálogo." in resposta.content.decode()


@pytest.mark.django_db
def test_a_tela_de_analise_oferece_despublicar_ao_curso_publicado(
    client, coordenador, curso_publicado
):
    """A capacidade so existe se a tela a oferecer: o botao e o chamador de
    producao que faltava. Confere tambem que a tela nao oferece Publicar/Devolver
    a um curso que ja saiu da fila."""
    client.force_login(coordenador)
    conteudo = client.get(reverse("analisar_curso", args=[curso_publicado.pk])).content.decode()
    assert 'value="DESPUBLICAR"' in conteudo
    assert 'value="PUBLICAR"' not in conteudo
    assert 'value="DEVOLVER"' not in conteudo


@pytest.mark.django_db
def test_a_tela_de_analise_oferece_republicar_ao_curso_despublicado(
    client, coordenador, curso_despublicado
):
    client.force_login(coordenador)
    conteudo = client.get(reverse("analisar_curso", args=[curso_despublicado.pk])).content.decode()
    assert 'value="PUBLICAR"' in conteudo
    assert "Republicar" in conteudo
    assert 'value="DESPUBLICAR"' not in conteudo


@pytest.mark.django_db
def test_decisao_desconhecida_nao_devolve_o_curso(client, coordenador, curso_submetido):
    """O ramo else de decidir_curso era pega-tudo: qualquer POST cujo "decisao"
    nao fosse exatamente "PUBLICAR" caia em devolver_curso, devolvia o curso ao
    professor e reabria os cinco entregaveis (R54) em silencio - o mesmo defeito
    que a Task 8 corrigiu em turmas.views.responder_solicitacao.

    O comentario vai preenchido de proposito: com ele vazio, a guarda de
    comentario obrigatorio de devolver_curso recusaria a operacao e o teste
    passaria mesmo com o pega-tudo de volta, sem provar nada sobre o roteamento.
    """
    client.force_login(coordenador)
    logs_antes = LogTransicaoCurso.objects.filter(curso=curso_submetido).count()
    resposta = client.post(
        reverse("decidir_curso", args=[curso_submetido.pk]),
        {"decisao": "ARQUIVAR", "comentario": "Falta revisar a bibliografia."},
        follow=True,
    )
    curso_submetido.refresh_from_db()
    assert curso_submetido.status == StatusCurso.AGUARDANDO_COORDENADOR
    assert LogTransicaoCurso.objects.filter(curso=curso_submetido).count() == logs_antes
    assert set(curso_submetido.entregaveis.values_list("status", flat=True)) == {
        StatusEntregavel.APROVADO
    }
    assert "Decisão não reconhecida." in resposta.content.decode()


@pytest.mark.django_db
def test_lista_do_catalogo_mostra_publicado_e_despublicado(
    client, coordenador, professor, aluno, dados_curso, curso_despublicado
):
    """Inclusao e exclusao: os dois status do catalogo entram, e o curso ainda na
    fila fica de fora - senao o filtro por status poderia virar "todos os cursos"
    sem ninguem notar. Cursos novos a partir de dados_curso, e nao as fixtures
    encadeadas: curso_despublicado *e* curso_submetido, o mesmo objeto levado
    adiante, entao compara-los nao provaria nada."""
    publicado = services.criar_curso(**{**dados_curso, "titulo": "Iniciação a Python"})
    services.adicionar_membro(publicado, aluno, por=professor)
    publicado.entregaveis.update(status=StatusEntregavel.APROVADO)
    publicado.refresh_from_db()
    services.submeter_ao_coordenador(publicado, por=professor)
    services.publicar_curso(publicado, por=coordenador)

    na_fila = services.criar_curso(**{**dados_curso, "titulo": "Robótica com Sucata"})
    services.adicionar_membro(na_fila, aluno, por=professor)
    na_fila.entregaveis.update(status=StatusEntregavel.APROVADO)
    na_fila.refresh_from_db()
    services.submeter_ao_coordenador(na_fila, por=professor)

    client.force_login(coordenador)
    conteudo = client.get(reverse("cursos_no_catalogo")).content.decode()
    assert curso_despublicado.titulo in conteudo
    assert publicado.titulo in conteudo
    assert na_fila.titulo not in conteudo


@pytest.mark.django_db
def test_lista_do_catalogo_vazia_mostra_mensagem(client, coordenador):
    client.force_login(coordenador)
    assert (
        "Nenhum curso publicado ou despublicado."
        in client.get(reverse("cursos_no_catalogo")).content.decode()
    )


@pytest.mark.django_db
def test_professor_nao_entra_na_lista_do_catalogo(client, professor, curso_despublicado):
    """Pelo GET, onde a guarda da view carrega o peso sozinha: nao ha servico
    nenhum nesta requisicao para recusar em lugar dela."""
    client.force_login(professor)
    assert client.get(reverse("cursos_no_catalogo")).status_code == 403


@pytest.mark.django_db
def test_aluno_nao_entra_na_lista_do_catalogo(client, aluno, curso_despublicado):
    client.force_login(aluno)
    assert client.get(reverse("cursos_no_catalogo")).status_code == 403


@pytest.mark.django_db
def test_aluno_nao_decide_pela_tela(client, aluno, curso_submetido):
    """A guarda de view de decidir_curso, isolada.

    Este POST leva uma "decisao" desconhecida de propósito: é o único ramo de
    decidir_curso que não chama serviço nenhum, então a guarda da view carrega o
    peso sozinha e o 403 só pode vir dela. Nos outros ramos a guarda do serviço
    também recusaria, e o teste não distinguiria as duas.
    """
    client.force_login(aluno)
    resposta = client.post(
        reverse("decidir_curso", args=[curso_submetido.pk]),
        {"decisao": "ARQUIVAR", "comentario": "qualquer coisa"},
    )
    assert resposta.status_code == 403
    curso_submetido.refresh_from_db()
    assert curso_submetido.status == StatusCurso.AGUARDANDO_COORDENADOR


@pytest.mark.django_db
def test_decidir_curso_nao_revela_se_o_curso_existe(client, aluno, curso_submetido):
    """A guarda precisa rodar ANTES do get_object_or_404, não depois.

    Com a busca primeiro, quem não é coordenador recebia 302 para um pk que
    existe e 404 para um que não existe - diferença suficiente para varrer os
    ids e descobrir quantos cursos há e quais. analisar_curso já devolvia 403
    nos dois casos; decidir_curso não (achado da re-revisão).
    """
    client.force_login(aluno)
    inexistente = Curso.objects.order_by("-pk").first().pk + 1000
    existente = client.post(
        reverse("decidir_curso", args=[curso_submetido.pk]), {"decisao": "ARQUIVAR"}
    )
    ausente = client.post(reverse("decidir_curso", args=[inexistente]), {"decisao": "ARQUIVAR"})
    assert existente.status_code == 403
    assert ausente.status_code == 403


@pytest.mark.django_db
def test_visitante_anonimo_vai_para_o_login(client, curso_despublicado):
    """Espelha o portão de login de apps/turmas/tests/test_views.py, que o app
    cursos não tinha para rota nenhuma.

    permissions.pode_publicar lê usuario.e_coordenador, atributo que
    AnonymousUser não tem: sem @login_required *antes* da checagem de papel, a
    resposta seria AttributeError (500), não um redirecionamento. Prende a
    ordem, não a boa vontade do decorador.
    """
    resposta = client.get(reverse("cursos_no_catalogo"))
    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))
