import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.contas.models import ConviteAluno, Usuario
from apps.cursos import services
from apps.cursos.choices import StatusCurso
from apps.notificacoes.models import Notificacao


@pytest.mark.django_db
def test_alocar_cria_a_conta_so_com_o_email(curso, professor):
    """A alocação informa só o e-mail, como o cadastro de professor.

    O professor digitava o nome do aluno, e digitar o nome de outra pessoa é onde
    nasce erro de grafia que ninguém corrige depois - esse nome aparece no crédito
    público do curso. Quem o escreve agora é o próprio aluno, no primeiro acesso.
    """
    membro = services.alocar_aluno(curso, email="joana@acad.ufsm.br", por=professor)
    assert membro.pessoa.nome_completo == ""
    assert membro.pessoa.papel == Usuario.ALUNO
    assert membro.pessoa.cpf is None
    assert membro.pessoa.perfil_completo is False


@pytest.mark.django_db
def test_alocar_convida_o_aluno(curso, professor):
    services.alocar_aluno(curso, email="joana@acad.ufsm.br", por=professor)
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
        curso, email="joana@acad.ufsm.br", por=professor
    )
    assert membro.pessoa.has_usable_password() is False


@pytest.mark.django_db
def test_email_ja_cadastrado_e_recusado(curso, professor, aluno):
    """Decisão do coordenador: recusa em vez de vincular a conta existente.
    Vincular em silêncio poria alguém numa equipe por um e-mail digitado errado."""
    with pytest.raises(ValidationError) as erro:
        services.alocar_aluno(curso, email=aluno.email, por=professor)
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
            curso, email=aluno.email.upper(), por=professor
        )


@pytest.mark.django_db
def test_email_recusado_nao_deixa_conta_nem_convite(curso, professor, aluno):
    antes = Usuario.objects.count()
    with pytest.raises(ValidationError):
        services.alocar_aluno(curso, email=aluno.email, por=professor)
    assert Usuario.objects.count() == antes
    assert ConviteAluno.objects.count() == 0


@pytest.mark.django_db
def test_qualquer_dominio_de_email_e_aceito(curso, professor):
    """Decisão do coordenador: sem lista branca de domínio -- há aluno de
    intercâmbio e conta pessoal, e restringir travaria o professor."""
    membro = services.alocar_aluno(
        curso, email="joana@gmail.com", por=professor
    )
    assert membro.pessoa.email == "joana@gmail.com"


@pytest.mark.django_db
def test_alocar_tira_o_curso_do_rascunho(curso, professor):
    assert curso.status == StatusCurso.RASCUNHO
    services.alocar_aluno(curso, email="joana@acad.ufsm.br", por=professor)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.EM_PRODUCAO


@pytest.mark.django_db
def test_aluno_nao_aloca(curso, aluno):
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(curso, email="joana@acad.ufsm.br", por=aluno)


@pytest.mark.django_db
def test_professor_de_outro_curso_nao_aloca(curso, outro_professor):
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(
            curso, email="joana@acad.ufsm.br", por=outro_professor
        )


@pytest.mark.django_db
def test_permissao_recusada_nao_deixa_conta(curso, outro_professor):
    """A guarda vem antes de qualquer escrita: sem isso, um professor de fora
    criaria a conta e só depois seria barrado."""
    with pytest.raises(PermissionDenied):
        services.alocar_aluno(
            curso, email="joana@acad.ufsm.br", por=outro_professor
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
            curso, email="joana@acad.ufsm.br", por=professor
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
            curso, email="joana@acad.ufsm.br", por=coordenador
        )
    assert not Usuario.objects.filter(email="joana@acad.ufsm.br").exists()


@pytest.mark.django_db
def test_email_em_branco_e_recusado(curso, professor):
    """Recusa explicita, e nao `ValueError` vindo do `create_user`: a view so
    captura `ValidationError`, e um POST sem e-mail viraria 500.

    O nome saiu da checagem junto com o campo: a conta nasce sem ele de proposito.
    """
    with pytest.raises(ValidationError):
        services.alocar_aluno(curso, email="   ", por=professor)
    assert Usuario.objects.filter(email="joana@acad.ufsm.br").exists() is False


@pytest.mark.django_db
def test_a_tela_de_aluno_novo_pede_so_o_email(client, curso, professor):
    """O formulario tinha nome e e-mail; passa a ter so o e-mail, como o cadastro
    de professor na tela de Pessoas."""
    from django.urls import reverse

    client.force_login(professor)
    html = client.get(reverse("equipe", args=[curso.pk])).content.decode()
    formulario = html[html.index("Aluno novo") : html.index("Alocar professor")]
    assert 'name="email"' in formulario
    assert 'name="nome"' not in formulario


@pytest.mark.django_db
def test_alocar_pela_tela_so_com_o_email(client, curso, professor):
    """Ponta a ponta: o POST leva so o e-mail, a conta nasce sem nome e o convite
    sai. A mensagem de sucesso identifica pelo e-mail, que e tudo o que existe."""
    from django.urls import reverse

    client.force_login(professor)
    resposta = client.post(
        reverse("equipe", args=[curso.pk]),
        {"acao": "aluno", "email": "joana@acad.ufsm.br"},
        follow=True,
    )
    assert resposta.status_code == 200
    nova = Usuario.objects.get(email="joana@acad.ufsm.br")
    assert nova.nome_completo == ""
    assert curso.tem_membro(nova)
    assert nova.convites.filter(usado_em__isnull=True).count() == 1
    assert "joana@acad.ufsm.br entrou na equipe." in resposta.content.decode()


@pytest.mark.django_db
def test_o_select_de_aluno_mostra_email_de_quem_nao_tem_nome(client, curso, professor):
    """Desde que o aluno tambem nasce so com o e-mail, ele pode aparecer neste
    select antes do primeiro acesso. Com o `str(obj)` padrao a option sairia
    vazia - a mesma lacuna que o select de professor ja tinha."""
    from django.urls import reverse

    sem_nome = Usuario.objects.create_user(
        email="semnome@acad.ufsm.br", nome_completo="", papel=Usuario.ALUNO, password=None
    )
    client.force_login(professor)
    html = client.get(reverse("equipe", args=[curso.pk])).content.decode()
    assert f'<option value="{sem_nome.pk}">semnome@acad.ufsm.br</option>' in html


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
def test_alocar_professor_sem_nome_produz_mensagem_com_email(client, curso, professor):
    """`f"{membro.pessoa.nome_completo} entrou na equipe."` com nome vazio produz
    " entrou na equipe.", sem sujeito e com espaco sobrando - a pessoa nao sabe se
    a acao valeu. So o professor pode chegar aqui sem nome (aluno sempre nasce com
    o nome que o professor digitou em `alocar_aluno`); coordenador tambem, pela
    mesma origem."""
    from django.urls import reverse

    sem_nome = Usuario.objects.create_user(
        email="semnome@ufsm.br", nome_completo="", papel=Usuario.PROFESSOR, password=None
    )
    client.force_login(professor)
    resposta = client.post(
        reverse("equipe", args=[curso.pk]),
        {"acao": "professor", "professor": sem_nome.pk},
        follow=True,
    )
    html = resposta.content.decode()
    assert "semnome@ufsm.br entrou na equipe." in html


@pytest.mark.django_db
def test_select_de_professores_nao_oferece_quem_ja_esta_na_equipe(
    client, dados_curso, professor, outro_professor
):
    """O responsavel e membro desde a criacao, entao nao pode aparecer no select:
    escolhe-lo daria erro de unicidade em vez de mensagem."""
    from django.urls import reverse

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.get(reverse("equipe", args=[curso.pk]))
    disponiveis = resposta.context["form_professor"].fields["professor"].queryset
    assert professor not in disponiveis
    assert outro_professor in disponiveis


@pytest.mark.django_db
def test_sem_professor_disponivel_mostra_mensagem_especifica(client, dados_curso, professor):
    """`_campo.html` teria mostrado a frase generica de "sem opcoes" - certa para
    um referencial ou uma competencia, que so a coordenacao cadastra pelo Admin -,
    mas errada aqui: qualquer professor esvazia este campo sozinho, so por ja ter
    alocado todo mundo disponivel. O `vazio=` do include precisa estar chegando.

    `services.criar_curso`, e nao a fixture `curso`: e ele que grava o
    MembroEquipe do responsavel, o que tira `professor` (o unico professor da
    base neste teste) do queryset - a fixture `curso` crua nao faz isso, e o
    professor sobraria disponivel para si mesmo.
    """
    from django.urls import reverse

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    html = client.get(reverse("equipe", args=[curso.pk])).content.decode()
    assert "Nenhum professor disponível." in html
    assert "A coordenação cadastra pelo painel de administração" not in html


@pytest.mark.django_db
def test_select_de_professores_mostra_email_para_quem_ainda_nao_tem_nome(
    client, curso, professor
):
    """A coordenacao cadastra professor so com o e-mail (CLAUDE.md, Papeis e
    primeiro acesso); ate o primeiro acesso `nome_completo` fica vazio.

    `_professores_disponiveis` nao filtra por perfil completo, entao essa conta
    aparece no select de "Alocar professor" - e sem fallback, a option nasce com
    o rotulo vazio: aparece na lista e ninguem consegue ler qual e.
    """
    from django.urls import reverse

    sem_nome = Usuario.objects.create_user(
        email="semnome@ufsm.br", nome_completo="", papel=Usuario.PROFESSOR, password=None
    )
    client.force_login(professor)
    html = client.get(reverse("equipe", args=[curso.pk])).content.decode()
    assert f'<option value="{sem_nome.pk}">semnome@ufsm.br</option>' in html


@pytest.mark.django_db
def test_a_lista_na_equipe_mostra_email_para_quem_ainda_nao_tem_nome(
    client, curso, professor
):
    """Mesma lacuna, na lista "Na equipe" acima dos selects. Tela login-gated
    (pode_gerir_equipe): mostrar o e-mail aqui não é o mesmo risco de mostrá-lo
    na página pública do catálogo, que é outra tela."""
    from django.urls import reverse

    sem_nome = Usuario.objects.create_user(
        email="semnomelista@ufsm.br", nome_completo="", papel=Usuario.PROFESSOR, password=None
    )
    services.alocar_professor(curso, sem_nome, por=professor)
    client.force_login(professor)
    html = client.get(reverse("equipe", args=[curso.pk])).content.decode()
    assert "semnomelista@ufsm.br" in html


@pytest.mark.django_db
def test_a_lista_da_equipe_usa_o_componente_de_linha(client, dados_curso, professor):
    """A lista usava `etiquetas`, o componente das tags de tema e palavra-chave:
    texto curto de 13px com 5px de respiro. Dentro de cada etiqueta cabia um botao
    "Remover" de 44px, e o `<li>` nem era flex - o botao saia desalinhado do nome.

    `registros` e o componente que a tela de Pessoas ja usa para o mesmo trabalho:
    uma linha por pessoa, identificacao a esquerda, acao a direita.
    """
    from django.urls import reverse

    # `criar_curso`, e nao a fixture `curso`: e ele que grava o MembroEquipe do
    # responsavel. Com a fixture crua a equipe nasce vazia e a lista mostra o
    # estado vazio, sem linha nenhuma para conferir.
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    html = client.get(reverse("equipe", args=[curso.pk])).content.decode()
    lista = html[html.index("Na equipe") : html.index("Aluno já cadastrado")]
    assert 'class="registros"' in lista
    assert 'class="registro"' in lista
    assert 'class="etiquetas"' not in lista


@pytest.mark.django_db
def test_o_responsavel_aparece_sem_botao_de_remover(client, dados_curso, professor, aluno):
    """`remover_membro` recusa tirar o responsavel da equipe (o curso ficaria sem
    quem revisa). Oferecer o botao para ele seria oferecer um caminho que a regra
    fecha - a pessoa clicaria para ouvir "nao da".

    Os dois lados no mesmo teste, porque e o contraste que descreve a regra: o
    responsavel traz o selo e nenhum botao; o aluno traz o botao.
    """
    from django.urls import reverse

    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    client.force_login(professor)
    html = client.get(reverse("equipe", args=[curso.pk])).content.decode()

    # `[1:]`: o primeiro pedaco e tudo o que vem ANTES da primeira linha, e a
    # barra do topo imprime o nome de quem esta logado - o professor casaria ali,
    # fora da lista. E a mesma armadilha que o helper `autoria()` de
    # test_autoria_e_progresso.py ja documenta.
    linhas = html.split('<li class="registro">')[1:]
    do_responsavel = next(l for l in linhas if professor.nome_completo in l)
    do_aluno = next(l for l in linhas if aluno.nome_completo in l)

    assert "Responsável" in do_responsavel
    assert "Remover" not in do_responsavel
    assert "Remover" in do_aluno


# --- Remover da equipe (Plano 6) ---------------------------------------------


@pytest.mark.django_db
def test_membro_e_removido_da_equipe(curso, professor, aluno):
    membro = services.adicionar_membro(curso, aluno, por=professor)
    services.remover_membro(curso, membro, por=professor)
    assert curso.tem_membro(aluno) is False


@pytest.mark.django_db
def test_remover_professor_sem_nome_produz_mensagem_com_email(client, curso, professor):
    """A mesma lacuna do lado da remocao: `_professores_disponiveis` nao filtra
    por perfil completo, entao um professor sem nome pode ser alocado e depois
    removido, e a mensagem de saida repetia o defeito de A3."""
    from django.urls import reverse

    sem_nome = Usuario.objects.create_user(
        email="semnome@ufsm.br", nome_completo="", papel=Usuario.PROFESSOR, password=None
    )
    membro = services.alocar_professor(curso, sem_nome, por=professor)
    client.force_login(professor)
    resposta = client.post(
        reverse("remover_da_equipe", args=[curso.pk, membro.pk]), follow=True
    )
    assert "semnome@ufsm.br saiu da equipe." in resposta.content.decode()


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
    exige os seis entregaveis aprovados e a ficha completa, e montar tudo isso
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
