import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel
from apps.cursos.models import LogTransicaoCurso, Revisao
from apps.notificacoes.models import Notificacao


@pytest.fixture
def curso_pronto(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    return curso


@pytest.mark.django_db
def test_submeter_exige_os_cinco_aprovados(dados_curso, aluno, professor):
    """Isola a guarda dos cinco aprovados: o curso precisa estar em EM_PRODUCAO
    (adicionar_membro tira do RASCUNHO) para que a guarda de status nao dispare
    tambem e mascare qual das duas recusou."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO
    with pytest.raises(ValidationError):
        services.submeter_ao_coordenador(curso, por=professor)


@pytest.mark.django_db
def test_a_mensagem_do_portao_usa_o_numero_real_de_entregaveis(dados_curso, aluno, professor):
    """A mensagem precisa nascer do modelo, e nao de um numero escrito a mao: a
    migracao 0016 acrescentou o sexto entregavel e o texto ficou dizendo "cinco"
    por uma sessao inteira, contradizendo a pagina Sobre na mesma tela.

    Comparar com `len(TipoEntregavel.choices)` prende a mensagem ao numero real
    de entregaveis do roteiro, entao um setimo entregavel nao pode reabrir o
    mesmo defeito silenciosamente.
    """
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.refresh_from_db()
    with pytest.raises(ValidationError) as excecao:
        services.submeter_ao_coordenador(curso, por=professor)
    total = len(TipoEntregavel.choices)
    assert str(total) in str(excecao.value)


@pytest.mark.django_db
def test_submeter_exige_curso_em_producao_ou_devolvido(dados_curso, professor):
    """Isola a guarda de status: os cinco entregaveis aprovados de proposito,
    para que so a guarda de status (curso ainda RASCUNHO) possa recusar."""
    curso = services.criar_curso(**dados_curso)
    assert curso.status == StatusCurso.RASCUNHO
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    with pytest.raises(ValidationError):
        services.submeter_ao_coordenador(curso, por=professor)


@pytest.mark.django_db
def test_submeter_muda_o_estado_e_registra_o_log(curso_pronto, professor):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.AGUARDANDO_COORDENADOR
    log = LogTransicaoCurso.objects.get(curso=curso_pronto)
    assert log.de_status == StatusCurso.EM_PRODUCAO
    assert log.usuario == professor


@pytest.mark.django_db
def test_submeter_revalida_os_dados_do_curso(curso_pronto, professor):
    """O curso pode ser editado depois do plano de ensino aprovado (spec 6)."""
    curso_pronto.carga_horaria = 1
    curso_pronto.save()
    curso_pronto.referencial = None
    curso_pronto.save()
    from apps.cursos.models import Curso

    # carga_horaria nao tem null=True (NOT NULL no banco); 0 e o valor falso que
    # o .update() aceita sem violar a constraint, e continua acionando "informe a
    # carga horaria" em validacoes.dados_do_curso.
    Curso.objects.filter(pk=curso_pronto.pk).update(carga_horaria=0)
    curso_pronto.refresh_from_db()
    with pytest.raises(ValidationError):
        services.submeter_ao_coordenador(curso_pronto, por=professor)


@pytest.mark.django_db
def test_aluno_nao_submete(curso_pronto, aluno):
    with pytest.raises(PermissionDenied):
        services.submeter_ao_coordenador(curso_pronto, por=aluno)


@pytest.mark.django_db
def test_professor_nao_publica(curso_pronto, professor):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    with pytest.raises(PermissionDenied):
        services.publicar_curso(curso_pronto, por=professor)


@pytest.mark.django_db
def test_professor_nao_devolve(curso_pronto, professor):
    """Apenas o coordenador devolve o curso (spec 5, 11) - mesmo o professor
    responsavel, que submeteu, nao pode se auto-devolver."""
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    with pytest.raises(PermissionDenied):
        services.devolver_curso(curso_pronto, por=professor, comentario="Preciso revisar.")


@pytest.mark.django_db
def test_professor_nao_despublica(curso_pronto, professor, coordenador):
    """Apenas o coordenador despublica o curso (spec 5, 11)."""
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    with pytest.raises(PermissionDenied):
        services.despublicar_curso(curso_pronto, por=professor, motivo="Material desatualizado.")


@pytest.mark.django_db
def test_coordenador_publica_e_avisa_a_equipe(curso_pronto, professor, coordenador, aluno):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.PUBLICADO
    assert curso_pronto.publicado_em is not None
    destinatarios = set(Notificacao.objects.values_list("destinatario", flat=True))
    assert {aluno.email, professor.email} <= destinatarios


@pytest.mark.django_db
def test_publicar_curso_que_nao_foi_submetido_e_recusado(curso_pronto, coordenador):
    with pytest.raises(ValidationError):
        services.publicar_curso(curso_pronto, por=coordenador)


@pytest.mark.django_db
def test_devolver_ao_professor_exige_comentario(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    with pytest.raises(ValidationError):
        services.devolver_curso(curso_pronto, por=coordenador, comentario=" ")


@pytest.mark.django_db
def test_devolver_curso_ja_devolvido_e_recusado(curso_pronto, professor, coordenador):
    """So se devolve curso que esta aguardando aprovacao (spec 5, 11). Sem esta
    guarda o coordenador poderia devolver de novo um curso ja DEVOLVIDO,
    reabrindo os cinco entregaveis (R54) e reenfileirando o aviso ao professor
    uma segunda vez, silenciosamente. comentario preenchido de proposito, para
    que so a guarda de status possa recusar."""
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.devolver_curso(curso_pronto, por=coordenador, comentario="Primeira devolucao.")
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.DEVOLVIDO
    with pytest.raises(ValidationError):
        services.devolver_curso(curso_pronto, por=coordenador, comentario="Segunda devolucao.")


@pytest.mark.django_db
def test_despublicar_curso_que_nunca_foi_publicado_e_recusado(curso_pronto, coordenador):
    """Este curso nao esta publicado (spec 5, 11): sem a guarda de status,
    despublicar_curso aceitaria um curso que nunca chegou a PUBLICADO. motivo
    preenchido de proposito, para que so a guarda de status possa recusar."""
    with pytest.raises(ValidationError):
        services.despublicar_curso(curso_pronto, por=coordenador, motivo="Motivo qualquer.")


@pytest.mark.django_db
def test_despublicar_exige_motivo(curso_pronto, professor, coordenador):
    """Espelha test_devolver_ao_professor_exige_comentario: despublicar_curso tem
    a mesma guarda de motivo obrigatorio que devolver_curso tem para comentario."""
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    with pytest.raises(ValidationError):
        services.despublicar_curso(curso_pronto, por=coordenador, motivo=" ")


@pytest.mark.django_db
def test_devolvido_volta_a_producao_ao_ser_submetido_de_novo(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.devolver_curso(curso_pronto, por=coordenador, comentario="Faltou detalhar o cronograma.")
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.DEVOLVIDO
    curso_pronto.entregaveis.update(status=StatusEntregavel.APROVADO)
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.AGUARDANDO_COORDENADOR


@pytest.mark.django_db
def test_despublicar_registra_o_motivo(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    services.despublicar_curso(curso_pronto, por=coordenador, motivo="Material desatualizado.")
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.DESPUBLICADO
    log = LogTransicaoCurso.objects.filter(para_status=StatusCurso.DESPUBLICADO).get()
    assert log.observacao == "Material desatualizado."


@pytest.mark.django_db
def test_devolver_curso_reabre_os_cinco_entregaveis(curso_pronto, professor, coordenador, aluno):
    """R54: o coordenador devolve o curso, nao cada entregavel - mas os cinco
    entregaveis continuam APROVADO (portanto congelados) se ninguem os reabrir, e a
    equipe fica sem poder agir sobre o feedback recebido. devolver_curso precisa
    devolver tambem os cinco entregaveis, na mesma transacao, sem criar Revisao (a
    decisao pedagogica sobre cada entrega continua sendo so do professor)."""
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    total_revisoes_antes = Revisao.objects.count()

    services.devolver_curso(curso_pronto, por=coordenador, comentario="Revisar o material didatico.")

    status_entregaveis = set(curso_pronto.entregaveis.values_list("status", flat=True))
    # RASCUNHO: o que o teste prende e que os seis voltam EDITAVEIS para a
    # equipe, e nao o rotulo que a coluna guardava.
    assert status_entregaveis == {StatusEntregavel.RASCUNHO}
    assert all(e.editavel for e in curso_pronto.entregaveis.all())
    assert all(e.editavel for e in curso_pronto.entregaveis.all())
    assert Revisao.objects.count() == total_revisoes_antes

    # A equipe consegue voltar a editar uma secao do plano de ensino.
    plano = curso_pronto.entregaveis.get(tipo="PLANO_ENSINO")
    secao = plano.secoes.first()
    secao.conteudo = "Texto revisado apos a devolucao."
    secao.atualizado_por = aluno
    secao.save()
    secao.refresh_from_db()
    assert "revisado" in secao.conteudo


# --- republicacao (spec 5: curso DESPUBLICADO "pode ser republicado") ---------


@pytest.fixture
def curso_despublicado(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    services.despublicar_curso(curso_pronto, por=coordenador, motivo="Material desatualizado.")
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.DESPUBLICADO
    return curso_pronto


@pytest.mark.django_db
def test_curso_despublicado_pode_ser_republicado(curso_despublicado, coordenador):
    """Spec 5, textualmente: curso DESPUBLICADO "pode ser republicado". Antes
    deste teste nenhum servico aceitava DESPUBLICADO como de_status - nem
    publicar_curso nem submeter_ao_coordenador -, e com CursoAdmin.readonly_fields
    fechando o Admin, a unica recuperacao era um .update() no shell, que pula
    _transicionar (achado Importante 1 da revisao de branch)."""
    services.publicar_curso(curso_despublicado, por=coordenador)
    curso_despublicado.refresh_from_db()
    assert curso_despublicado.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_republicacao_grava_o_log_da_transicao(curso_despublicado, coordenador):
    """A republicacao existe para passar pelo servico, nao so para mudar o campo:
    o historico administrativo (spec 11) precisa registrar a volta ao catalogo
    com de_status DESPUBLICADO. Um .update() no shell mudaria o status sem isto."""
    services.publicar_curso(curso_despublicado, por=coordenador)
    log = LogTransicaoCurso.objects.get(
        curso=curso_despublicado,
        de_status=StatusCurso.DESPUBLICADO,
        para_status=StatusCurso.PUBLICADO,
    )
    assert log.usuario == coordenador


@pytest.mark.django_db
def test_republicacao_avisa_a_equipe_com_evento_proprio(
    curso_despublicado, coordenador, aluno, professor
):
    """Evento distinto de CURSO_PUBLICADO: o corpo de CURSO_PUBLICADO diz que o
    curso "foi aprovado pela coordenacao", o que e falso numa republicacao - o
    curso nunca deixou de estar aprovado, so saiu do catalogo. Filtra por evento
    de proposito: sem o filtro, as notificacoes que a propria fixture enfileira
    (submissao, publicacao) fariam o teste passar mesmo sem aviso nenhum aqui."""
    services.publicar_curso(curso_despublicado, por=coordenador)
    destinatarios = set(
        Notificacao.objects.filter(evento="CURSO_REPUBLICADO").values_list(
            "destinatario", flat=True
        )
    )
    assert destinatarios == {aluno.email, professor.email}


@pytest.mark.django_db
def test_professor_nao_republica(curso_despublicado, professor):
    """So o coordenador publica ou republica (spec 5). O curso esta em
    DESPUBLICADO de proposito - um de_status agora valido -, para que so a guarda
    de permissao possa recusar, e nao a de status."""
    with pytest.raises(PermissionDenied):
        services.publicar_curso(curso_despublicado, por=professor)
    curso_despublicado.refresh_from_db()
    assert curso_despublicado.status == StatusCurso.DESPUBLICADO


@pytest.mark.django_db
def test_curso_substituido_nao_pode_ser_republicado(curso_pronto, aluno, professor, coordenador):
    """Spec 5: SUBSTITUIDO e terminal, "nao republicavel" - o contraponto exato
    da frase que autoriza republicar o DESPUBLICADO.

    O status chega aqui pelo caminho de verdade desde o Plano 4, Task 5:
    publicar a versao seguinte da linhagem. Ate entao era um .update() direto,
    porque nenhum service alcancava SUBSTITUIDO."""
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    nova = services.abrir_nova_versao(curso_pronto, por=coordenador, motivo="Refazer o caderno.")
    services.adicionar_membro(nova, aluno, por=professor)
    nova.entregaveis.update(status=StatusEntregavel.APROVADO)
    nova.refresh_from_db()
    services.submeter_ao_coordenador(nova, por=professor)
    services.publicar_curso(nova, por=coordenador)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.SUBSTITUIDO

    with pytest.raises(ValidationError):
        services.publicar_curso(curso_pronto, por=coordenador)

    curso_pronto.refresh_from_db()
    nova.refresh_from_db()
    assert curso_pronto.status == StatusCurso.SUBSTITUIDO
    assert nova.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_republicar_curso_volta_ao_catalogo_publico(client, curso_despublicado, coordenador):
    """Costura com o catalogo: republicar nao pode so mudar o campo, tem de
    devolver o curso as portas publicas - o espelho de
    test_curso_nao_publicado_fica_fora_das_duas_portas, que ja crava a ida."""
    from django.urls import reverse

    assert curso_despublicado.titulo not in client.get(reverse("catalogo")).content.decode()
    services.publicar_curso(curso_despublicado, por=coordenador)
    assert curso_despublicado.titulo in client.get(reverse("catalogo")).content.decode()
