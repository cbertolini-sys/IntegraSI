import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.contas.models import ConviteAluno, Usuario
from apps.cursos import services
from apps.cursos.choices import StatusCurso
from apps.notificacoes.models import Notificacao


@pytest.mark.django_db
def test_alocar_cria_a_conta_com_nome_e_email(curso, professor):
    """Regra 2: a alocação informa só nome e e-mail."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor
    )
    assert membro.pessoa.nome_completo == "Joana Silva"
    assert membro.pessoa.papel == Usuario.ALUNO
    assert membro.pessoa.cpf is None
    assert membro.pessoa.perfil_completo is False


@pytest.mark.django_db
def test_alocar_convida_o_aluno(curso, professor):
    services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor)
    assert ConviteAluno.objects.filter(usuario__email="joana@acad.ufsm.br").count() == 1
    assert (
        Notificacao.objects.filter(
            evento="CONVITE_ALUNO", destinatario="joana@acad.ufsm.br"
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_a_conta_nasce_sem_senha_utilizavel(curso, professor):
    """Só o convite dá acesso: uma senha vazia que autenticasse seria uma porta
    aberta em toda conta ainda não usada."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor
    )
    assert membro.pessoa.has_usable_password() is False


@pytest.mark.django_db
def test_email_ja_cadastrado_e_recusado(curso, professor, aluno):
    """Decisão do coordenador: recusa em vez de vincular a conta existente.
    Vincular em silêncio poria alguém numa equipe por um e-mail digitado errado."""
    with pytest.raises(ValidationError) as erro:
        services.alocar_aluno(curso, nome="Outro Nome", email=aluno.email, por=professor)
    # Afirma a MENSAGEM, e nao so o tipo: o indice unico do modelo recusaria este
    # mesmo caso sozinho, e um `pytest.raises(ValidationError)` pelado passaria com
    # a checagem do servico apagada (conferido por mutacao). O que o servico
    # acrescenta e dizer ao professor o que fazer a seguir.
    assert "Confira o endereço" in " ".join(erro.value.messages)


@pytest.mark.django_db
def test_email_ja_cadastrado_e_recusado_ignorando_maiusculas(curso, professor, aluno):
    """A recusa não pode depender de como a pessoa digitou: `Aluno@UFSM.br` é a
    mesma conta."""
    with pytest.raises(ValidationError):
        services.alocar_aluno(
            curso, nome="Outro Nome", email=aluno.email.upper(), por=professor
        )


@pytest.mark.django_db
def test_email_recusado_nao_deixa_conta_nem_convite(curso, professor, aluno):
    antes = Usuario.objects.count()
    with pytest.raises(ValidationError):
        services.alocar_aluno(curso, nome="Outro Nome", email=aluno.email, por=professor)
    assert Usuario.objects.count() == antes
    assert ConviteAluno.objects.count() == 0


@pytest.mark.django_db
def test_qualquer_dominio_de_email_e_aceito(curso, professor):
    """Decisão do coordenador: sem lista branca de domínio -- há aluno de
    intercâmbio e conta pessoal, e restringir travaria o professor."""
    membro = services.alocar_aluno(
        curso, nome="Joana Silva", email="joana@gmail.com", por=professor
    )
    assert membro.pessoa.email == "joana@gmail.com"


@pytest.mark.django_db
def test_alocar_tira_o_curso_do_rascunho(curso, professor):
    assert curso.status == StatusCurso.RASCUNHO
    services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO


@pytest.mark.django_db
def test_aluno_nao_aloca(curso, aluno):
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=aluno)


@pytest.mark.django_db
def test_professor_de_outro_curso_nao_aloca(curso, outro_professor):
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(
            curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=outro_professor
        )


@pytest.mark.django_db
def test_permissao_recusada_nao_deixa_conta(curso, outro_professor):
    """A guarda vem antes de qualquer escrita: sem isso, um professor de fora
    criaria a conta e só depois seria barrado."""
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(
            curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=outro_professor
        )
    assert Usuario.objects.filter(email="joana@acad.ufsm.br").exists() is False


@pytest.mark.django_db
def test_alocacao_e_atomica_quando_o_convite_falha(curso, professor, monkeypatch):
    """A conta, o vínculo e o convite nascem juntos ou não nascem.

    Sem a transação, um erro no envio deixaria uma conta órfã que ninguém ativa e
    que queima o e-mail para sempre: a segunda tentativa bateria na recusa de
    e-mail já cadastrado, e só a coordenação destravaria pelo Admin.

    O patch é na origem (`apps.contas.services.convidar`), e não no nome
    importado: `alocar_aluno` importa a função dentro do corpo, para não fechar
    ciclo entre `cursos` e `contas`.
    """

    def explode(*args, **kwargs):
        raise RuntimeError("fila fora do ar")

    monkeypatch.setattr("apps.contas.services.convidar", explode)
    with pytest.raises(RuntimeError):
        services.alocar_aluno(
            curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=professor
        )
    monkeypatch.undo()
    assert Usuario.objects.filter(email="joana@acad.ufsm.br").exists() is False
    assert curso.membros.count() == 0


@pytest.mark.django_db
def test_coordenador_nao_aloca_em_curso_alheio(curso, coordenador):
    """Era "o coordenador e professor e gere qualquer equipe". Virou por decisao
    do produto: ele e professor como qualquer outro, e gere a equipe dos cursos
    que responde. Em curso alheio, autoriza e despublica."""
    from django.core.exceptions import PermissionDenied

    from apps.contas.models import Usuario

    with pytest.raises(PermissionDenied):
        services.alocar_aluno(
            curso, nome="Joana Silva", email="joana@acad.ufsm.br", por=coordenador
        )
    assert not Usuario.objects.filter(email="joana@acad.ufsm.br").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("faltando", ["nome", "email"])
def test_nome_ou_email_em_branco_e_recusado(curso, professor, faltando):
    """Recusa explicita, e nao `ValueError` vindo do `create_user`: a view so
    captura `ValidationError`, e um POST incompleto viraria 500. Dois casos, para
    que apagar uma das duas checagens derrube exatamente a sua parametrizacao."""
    dados = {"nome": "Joana Silva", "email": "joana@acad.ufsm.br"}
    dados[faltando] = "   "
    with pytest.raises(ValidationError):
        services.alocar_aluno(curso, por=professor, **dados)
    assert Usuario.objects.filter(email="joana@acad.ufsm.br").exists() is False


# --- Alocar professor na equipe (Plano 6) ------------------------------------


@pytest.mark.django_db
def test_professor_e_alocado_na_equipe(curso, professor, outro_professor):
    membro = services.alocar_professor(curso, outro_professor, por=professor)
    assert membro.pessoa == outro_professor
    assert curso.tem_membro(outro_professor)


@pytest.mark.django_db
def test_alocar_professor_nao_manda_convite(curso, professor, outro_professor):
    """Professor ja tem conta: quem cria conta de professor e a coordenacao. Um
    convite de primeiro acesso aqui seria convite para quem ja entra no sistema."""
    antes = Notificacao.objects.count()
    services.alocar_professor(curso, outro_professor, por=professor)
    assert Notificacao.objects.count() == antes
    assert ConviteAluno.objects.filter(usuario=outro_professor).exists() is False


@pytest.mark.django_db
def test_alocar_aluno_pelo_caminho_de_professor_e_recusado(curso, professor, aluno):
    with pytest.raises(ValidationError):
        services.alocar_professor(curso, aluno, por=professor)


@pytest.mark.django_db
def test_alocar_professor_sem_escolher_ninguem_e_recusado(curso, professor):
    """O select pode chegar vazio (POST forjado, ou nenhum professor disponivel).

    Confere a MENSAGEM, e nao so o tipo: sem a recusa aqui, o None seguiria para
    MembroEquipe, cujo full_clean tambem levanta ValidationError por campo nulo.
    Um pytest.raises pelado ficaria verde com esta guarda apagada, e a pessoa veria
    "Este campo nao pode ser nulo" no lugar de uma frase que explica o que fazer.
    """
    with pytest.raises(ValidationError, match="Escolha um professor"):
        services.alocar_professor(curso, None, por=professor)


@pytest.mark.django_db
def test_professor_de_fora_nao_aloca_ninguem(curso, outro_professor, coordenador):
    with pytest.raises(PermissionDenied):
        services.alocar_professor(curso, coordenador, por=outro_professor)


@pytest.mark.django_db
def test_professor_alocado_produz_mas_nao_revisa(curso, professor, outro_professor):
    """A decisao da spec 10: professor colaborador produz e nao aprova. As duas
    metades no mesmo teste, porque e o contraste que descreve a regra."""
    from apps.cursos import permissions

    services.alocar_professor(curso, outro_professor, por=professor)
    assert permissions.pode_ver_curso(outro_professor, curso) is True
    assert permissions.pode_editar_ficha(outro_professor, curso) is True
    assert permissions.pode_revisar(outro_professor, curso) is False
    assert permissions.pode_gerir_equipe(outro_professor, curso) is False


@pytest.mark.django_db
def test_tela_de_equipe_aloca_professor_pelo_select(client, curso, professor, outro_professor):
    """Fiacao da tela: o campo escondido `acao` e o que separa os dois formularios.
    Sem ele o POST do select cairia no ramo do aluno e viraria "informe o nome"."""
    from django.urls import reverse

    client.force_login(professor)
    client.post(
        reverse("equipe", args=[curso.pk]),
        {"acao": "professor", "professor": outro_professor.pk},
        follow=True,
    )
    assert curso.tem_membro(outro_professor)


@pytest.mark.django_db
def test_select_de_professores_nao_oferece_quem_ja_esta_na_equipe(
    client, dados_curso, professor, outro_professor
):
    """O responsavel e membro desde a criacao, entao nao pode aparecer no select:
    escolhe-lo daria erro de unicidade em vez de mensagem."""
    from django.urls import reverse

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    disponiveis = client.get(reverse("equipe", args=[curso.pk])).context["professores"]
    assert professor not in disponiveis
    assert outro_professor in disponiveis


# --- Remover da equipe (Plano 6) ---------------------------------------------


@pytest.mark.django_db
def test_membro_e_removido_da_equipe(curso, professor, aluno):
    membro = services.adicionar_membro(curso, aluno, por=professor)
    services.remover_membro(curso, membro, por=professor)
    assert curso.tem_membro(aluno) is False


@pytest.mark.django_db
def test_remover_membro_preserva_o_que_ele_produziu(dados_curso, professor, aluno, arquivo_qualquer):
    """Remover tira o acesso, nao apaga o trabalho (spec 4.1).

    O anexo precisa estar pendurado no curso, e nao solto: um Arquivo avulso
    sobreviveria a qualquer coisa, e o teste passaria mesmo com a regra quebrada.
    E o vinculo com o entregavel que faz a pergunta valer a pena.
    """
    from apps.cursos.choices import TipoEntregavel, TipoMidia
    from apps.cursos.models import Anexo

    curso = services.criar_curso(**dados_curso)
    membro = services.adicionar_membro(curso, aluno, por=professor)
    anexo = Anexo.objects.create(
        entregavel=curso.entregaveis.get(tipo=TipoEntregavel.SLIDES),
        tipo_midia=TipoMidia.ARQUIVO,
        arquivo=arquivo_qualquer,
        titulo="Slides da oficina",
        enviado_por=aluno,
    )
    services.remover_membro(curso, membro, por=professor)
    anexo.refresh_from_db()
    assert anexo.enviado_por == aluno


@pytest.mark.django_db
def test_responsavel_nao_pode_ser_removido(dados_curso, professor):
    """Sem ele o curso fica sem quem revisa (spec 4.1). Confere a mensagem: sem
    esta guarda o delete passaria em silencio, e nada mais recusaria."""
    curso = services.criar_curso(**dados_curso)
    membro = curso.membros.get(pessoa=professor)
    with pytest.raises(ValidationError, match="responsável"):
        services.remover_membro(curso, membro, por=professor)


@pytest.mark.django_db
def test_nao_se_remove_membro_de_curso_ja_submetido(curso, professor, aluno):
    """Depois de submetido a coordenacao, quem compoe a equipe e parte do que
    esta sendo julgado (spec 4.1).

    O status e posto na mao, e nao por submeter_ao_coordenador: aquele servico
    exige os cinco entregaveis aprovados e a ficha completa, e montar tudo isso
    aqui faria o teste falhar por meia duzia de motivos alheios a regra.
    """
    membro = services.adicionar_membro(curso, aluno, por=professor)
    curso.status = StatusCurso.AGUARDANDO_COORDENADOR
    curso.save(update_fields=["status"])
    with pytest.raises(ValidationError, match="produção"):
        services.remover_membro(curso, membro, por=professor)


@pytest.mark.django_db
def test_nao_se_remove_membro_de_outro_curso(dados_curso, professor, aluno, edicao):
    """A url traz os dois ids. Sem conferir que o membro e deste curso, quem tem
    permissao aqui apagaria vinculo de curso alheio."""
    curso_a = services.criar_curso(**dados_curso)
    curso_b = services.criar_curso(titulo="Outro curso", professor_responsavel=professor)
    membro_de_b = services.adicionar_membro(curso_b, aluno, por=professor)
    with pytest.raises(ValidationError, match="deste curso"):
        services.remover_membro(curso_a, membro_de_b, por=professor)
    assert curso_b.tem_membro(aluno)


@pytest.mark.django_db
def test_aluno_da_equipe_nao_remove_ninguem(curso, professor, aluno, outro_aluno):
    membro = services.adicionar_membro(curso, outro_aluno, por=professor)
    services.adicionar_membro(curso, aluno, por=professor)
    with pytest.raises(PermissionDenied):
        services.remover_membro(curso, membro, por=aluno)


@pytest.mark.django_db
def test_get_da_equipe_recusa_aluno(client, curso, aluno, professor):
    """A guarda da view de equipe, isolada por GET: no POST o servico recusaria
    junto e o teste veria o mesmo 403 com a guarda da view apagada."""
    from django.urls import reverse

    services.adicionar_membro(curso, aluno, por=professor)
    client.force_login(aluno)
    assert client.get(reverse("equipe", args=[curso.pk])).status_code == 403


@pytest.mark.django_db
def test_get_de_remover_nao_apaga(client, curso, professor, aluno):
    """require_POST: remocao e ato destrutivo e nao pode acontecer por navegacao,
    pre-fetch de navegador ou link colado em conversa."""
    from django.urls import reverse

    membro = services.adicionar_membro(curso, aluno, por=professor)
    client.force_login(professor)
    resposta = client.get(reverse("remover_da_equipe", args=[curso.pk, membro.pk]))
    assert resposta.status_code == 405
    assert curso.tem_membro(aluno)


@pytest.mark.django_db
def test_remover_recusa_antes_de_procurar_o_membro(client, curso, aluno, professor):
    """Isola a guarda da VIEW, que nao tem GET por onde responder sozinha.

    O caminho e o membro inexistente: com a guarda no lugar, quem nao pode gerir a
    equipe leva 403 antes do get_object_or_404. Sem ela, o fluxo chega ao lookup e
    devolve 404, o que alem de trocar o erro vira um oraculo de existencia: um
    aluno descobriria quais MembroEquipe existem comparando 403 com 404.
    """
    from django.urls import reverse

    services.adicionar_membro(curso, aluno, por=professor)
    client.force_login(aluno)
    resposta = client.post(reverse("remover_da_equipe", args=[curso.pk, 99999]))
    assert resposta.status_code == 403
