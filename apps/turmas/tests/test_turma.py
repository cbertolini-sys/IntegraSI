import datetime

import pytest
from django.apps import apps as registro_de_apps
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import ProtectedError
from django.test import RequestFactory
from django.urls import reverse

from apps.catalogo.models import Solicitacao
from apps.notificacoes.models import Notificacao
from apps.turmas import services
from apps.turmas.admin import TurmaAdmin
from apps.turmas.models import Participante, Turma


def dados_turma():
    return {
        "data_inicio": datetime.date(2027, 3, 1),
        "data_fim": datetime.date(2027, 3, 30),
        "local": "EMEF São José",
        "vagas": 25,
    }


def explode(*args, **kwargs):
    """Falha depois que tudo já foi gravado, para exercitar o rollback."""
    raise RuntimeError("SMTP fora do ar")


# --- aceitar_solicitacao -----------------------------------------------------


@pytest.mark.django_db
def test_aceitar_cria_a_turma_com_professor(solicitacao, professor, coordenador):
    turma = services.aceitar_solicitacao(
        solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
    )
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.ACEITA
    assert turma.professor == professor
    assert turma.curso == solicitacao.curso
    assert turma.status == Turma.AGENDADA


@pytest.mark.django_db
def test_aceitar_responde_ao_solicitante(solicitacao, professor, coordenador):
    services.aceitar_solicitacao(
        solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
    )
    # Filtra pelo evento: a fixture curso_publicado já enfileira notificações só
    # de percorrer o ciclo de vida do curso, e sem o filtro o teste passaria mesmo
    # que o serviço nunca chamasse enfileirar (lição do Task 6).
    assert Notificacao.objects.filter(
        evento="SOLICITACAO_ACEITA", destinatario=solicitacao.email
    ).exists()


@pytest.mark.django_db
def test_aceitar_grava_a_resposta_na_solicitacao(solicitacao, professor, coordenador):
    services.aceitar_solicitacao(
        solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
    )
    solicitacao.refresh_from_db()
    assert professor.nome_completo in solicitacao.resposta
    assert "01/03/2027" in solicitacao.resposta


@pytest.mark.django_db
def test_aceitar_sem_professor_e_impossivel(solicitacao, coordenador):
    with pytest.raises(TypeError):
        services.aceitar_solicitacao(solicitacao, dados_turma=dados_turma(), por=coordenador)


@pytest.mark.django_db
def test_quem_nao_e_professor_nao_conduz_turma(solicitacao, aluno, coordenador):
    with pytest.raises(ValidationError):
        services.aceitar_solicitacao(
            solicitacao, professor=aluno, dados_turma=dados_turma(), por=coordenador
        )


@pytest.mark.django_db
def test_professor_desativado_nao_conduz_turma(solicitacao, outro_professor, coordenador):
    """Desativar a conta é como este sistema desliga alguém (Usuario não é
    apagado, por causa dos PROTECT). Turma.clean não olhava is_active, então uma
    turma podia ser designada a quem não entra mais no sistema - e o professor
    designado é justamente quem passa a enxergar os participantes (spec 7.2, 10).

    outro_professor, e não `professor`: `professor` é o responsável do curso
    publicado da fixture, e desativá-lo mexeria no cenário por outro lado.
    e_professor continua verdadeiro aqui de propósito, para que só a guarda de
    is_active possa recusar.
    """
    outro_professor.is_active = False
    outro_professor.save()
    assert outro_professor.e_professor
    with pytest.raises(ValidationError):
        services.aceitar_solicitacao(
            solicitacao, professor=outro_professor, dados_turma=dados_turma(), por=coordenador
        )
    assert Turma.objects.count() == 0
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA


@pytest.mark.django_db
def test_professor_desativado_fica_fora_do_formulario_de_turma(outro_professor):
    """A tela não é a guarda (essa é Turma.clean), mas oferecer no select alguém
    que o model vai recusar é um erro de apresentação garantido.

    Só a metade `is_active` do queryset: a metade `papel` é do teste irmão
    abaixo. Uma asserção única sobre o queryset passaria com qualquer uma das
    duas apagada - foi o que a re-revisão pegou nesta própria correção."""
    from apps.turmas.forms import TurmaForm

    escolhas = TurmaForm().fields["professor"].queryset
    assert outro_professor in escolhas
    outro_professor.is_active = False
    outro_professor.save()
    assert outro_professor not in TurmaForm().fields["professor"].queryset


@pytest.mark.django_db
def test_quem_nao_e_professor_fica_fora_do_formulario_de_turma(aluno, outro_professor):
    """A outra metade do mesmo queryset. O aluno está ativo de propósito: assim
    só o filtro por `papel` pode excluí-lo, e apagar `is_active=True` não derruba
    este teste (nem o daqui de cima derruba por causa do `papel`)."""
    from apps.turmas.forms import TurmaForm

    assert aluno.is_active
    escolhas = TurmaForm().fields["professor"].queryset
    assert outro_professor in escolhas
    assert aluno not in escolhas


@pytest.mark.django_db
def test_aluno_nao_aceita_solicitacao(solicitacao, professor, aluno):
    with pytest.raises(PermissionDenied):
        services.aceitar_solicitacao(
            solicitacao, professor=professor, dados_turma=dados_turma(), por=aluno
        )


@pytest.mark.django_db
def test_professor_nao_aceita_solicitacao(solicitacao, professor):
    # pode_publicar é do coordenador: o portão entre catálogo e agenda é decisão
    # institucional, não pedagógica (spec 5, 11).
    with pytest.raises(PermissionDenied):
        services.aceitar_solicitacao(
            solicitacao, professor=professor, dados_turma=dados_turma(), por=professor
        )


@pytest.mark.django_db
def test_aceitar_duas_vezes_e_recusado(solicitacao, professor, coordenador):
    """Atenção: este teste passa mesmo com a guarda de "já respondida" apagada,
    porque a segunda tentativa esbarra no validate_unique() do OneToOne de
    Turma.solicitacao e levanta ValidationError por outro motivo. Quem prende a
    guarda de verdade é o irmão test_aceitar_solicitacao_ja_recusada_e_recusado,
    onde nenhuma turma chega a ser criada. Mantido como regressão do caminho mais
    óbvio, não como prova da regra (achado da revisão)."""
    services.aceitar_solicitacao(
        solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
    )
    with pytest.raises(ValidationError):
        services.aceitar_solicitacao(
            solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
        )


@pytest.mark.django_db
def test_aceitar_solicitacao_ja_recusada_e_recusado(solicitacao, professor, coordenador):
    services.recusar_solicitacao(solicitacao, por=coordenador, resposta="Sem equipe em 2027.")
    with pytest.raises(ValidationError):
        services.aceitar_solicitacao(
            solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
        )


@pytest.mark.django_db
def test_fim_antes_do_inicio_e_recusado(solicitacao, professor, coordenador):
    """Prende a regra de datas de Turma.clean(), não a atomicidade: o
    ValidationError sai de full_clean() antes de qualquer INSERT, então nada
    aqui exercitaria o rollback. A atomicidade é do teste seguinte."""
    dados = dados_turma()
    dados["data_fim"] = datetime.date(2027, 1, 1)  # antes do início
    with pytest.raises(ValidationError):
        services.aceitar_solicitacao(
            solicitacao, professor=professor, dados_turma=dados, por=coordenador
        )
    assert Turma.objects.count() == 0


@pytest.mark.django_db
def test_aceitar_desfaz_tudo_quando_a_notificacao_falha(
    solicitacao, professor, coordenador, monkeypatch
):
    """Atomicidade de verdade: a falha acontece DEPOIS de a turma ter sido criada
    e de a solicitação já estar ACEITA no banco. Sem @transaction.atomic, os dois
    ficariam gravados."""
    monkeypatch.setattr("apps.turmas.services.enfileirar", explode)
    with pytest.raises(RuntimeError):
        services.aceitar_solicitacao(
            solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
        )
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA
    assert Turma.objects.count() == 0


# --- recusar_solicitacao -----------------------------------------------------


@pytest.mark.django_db
def test_recusar_registra_a_resposta(solicitacao, coordenador):
    services.recusar_solicitacao(
        solicitacao, por=coordenador, resposta="Sem equipe disponível em 2027."
    )
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECUSADA
    assert solicitacao.resposta == "Sem equipe disponível em 2027."
    assert Notificacao.objects.filter(
        evento="SOLICITACAO_RECUSADA", destinatario=solicitacao.email
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("resposta", ["", "   ", None])
def test_recusar_exige_resposta_escrita(solicitacao, coordenador, resposta):
    with pytest.raises(ValidationError):
        services.recusar_solicitacao(solicitacao, por=coordenador, resposta=resposta)
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA


@pytest.mark.django_db
def test_aluno_nao_recusa_solicitacao(solicitacao, aluno):
    with pytest.raises(PermissionDenied):
        services.recusar_solicitacao(solicitacao, por=aluno, resposta="Não dá.")


@pytest.mark.django_db
def test_professor_nao_recusa_solicitacao(solicitacao, professor):
    """Espelha test_professor_nao_aceita_solicitacao. Sem este teste, afrouxar a
    guarda de recusar_solicitacao para "coordenação OU professor" passava pela
    suíte inteira, enquanto a mutação idêntica em aceitar_solicitacao falhava - a
    assimetria estava nos testes, não no código (achado da revisão)."""
    with pytest.raises(PermissionDenied):
        services.recusar_solicitacao(solicitacao, por=professor, resposta="Sem equipe.")


@pytest.mark.django_db
def test_recusar_duas_vezes_e_recusado(solicitacao, coordenador):
    services.recusar_solicitacao(solicitacao, por=coordenador, resposta="Sem equipe.")
    with pytest.raises(ValidationError):
        services.recusar_solicitacao(solicitacao, por=coordenador, resposta="Sem equipe.")


@pytest.mark.django_db
def test_recusar_desfaz_tudo_quando_a_notificacao_falha(solicitacao, coordenador, monkeypatch):
    monkeypatch.setattr("apps.turmas.services.enfileirar", explode)
    with pytest.raises(RuntimeError):
        services.recusar_solicitacao(solicitacao, por=coordenador, resposta="Sem equipe.")
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA
    assert solicitacao.resposta == ""


# --- modelos -----------------------------------------------------------------


@pytest.mark.django_db
def test_participante_e_vinculado_a_turma(solicitacao, professor, coordenador):
    turma = services.aceitar_solicitacao(
        solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
    )
    Participante.objects.create(turma=turma, nome="Maria", email="maria@exemplo.br")
    assert turma.participantes.count() == 1


@pytest.mark.django_db
def test_apagar_turma_leva_os_participantes_junto(curso_publicado, professor):
    """Participante.turma é CASCADE, não PROTECT: o participante é dado pessoal de
    terceiro externo (spec 10) e não tem vida própria fora da turma - apagar a
    turma tem de levar a lista embora, não travar na chave estrangeira."""
    turma = Turma.objects.create(curso=curso_publicado, professor=professor, **dados_turma())
    Participante.objects.create(turma=turma, nome="Maria", email="maria@exemplo.br")
    turma.delete()
    assert Participante.objects.count() == 0


@pytest.mark.django_db
def test_curso_com_turma_nao_pode_ser_apagado(curso_publicado, professor):
    # Turma criada sem solicitação de propósito: a Solicitacao também é PROTECT
    # sobre o curso, e com ela no cenário o ProtectedError apareceria mesmo que
    # Turma.curso fosse CASCADE - o teste não prenderia nada.
    Turma.objects.create(curso=curso_publicado, professor=professor, **dados_turma())
    with pytest.raises(ProtectedError):
        curso_publicado.delete()


@pytest.mark.django_db
def test_solicitacao_com_turma_nao_pode_ser_apagada(solicitacao, professor, coordenador):
    services.aceitar_solicitacao(
        solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
    )
    with pytest.raises(ProtectedError):
        solicitacao.delete()


@pytest.mark.django_db
def test_professor_com_turma_nao_pode_ser_apagado(curso_publicado, outro_professor):
    # outro_professor, e não professor: professor é o responsável do curso e já
    # tem outras relações PROTECT, que mascarariam a deste FK.
    Turma.objects.create(curso=curso_publicado, professor=outro_professor, **dados_turma())
    with pytest.raises(ProtectedError):
        outro_professor.delete()


@pytest.mark.django_db
def test_uma_solicitacao_gera_uma_turma_so(solicitacao, professor, coordenador):
    services.aceitar_solicitacao(
        solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador
    )
    with pytest.raises(ValidationError):
        Turma.objects.create(
            curso=solicitacao.curso, solicitacao=solicitacao, professor=professor, **dados_turma()
        )


@pytest.mark.django_db
def test_turma_sem_solicitacao_e_de_primeira_classe(curso_publicado, professor):
    turma = Turma.objects.create(curso=curso_publicado, professor=professor, **dados_turma())
    assert turma.solicitacao is None


@pytest.mark.django_db
def test_save_de_turma_valida_o_objeto(curso_publicado, aluno):
    turma = Turma(curso=curso_publicado, professor=aluno, **dados_turma())
    with pytest.raises(ValidationError):
        turma.save()


@pytest.mark.django_db
def test_save_de_turma_com_update_fields_nao_revalida(curso_publicado, professor):
    """Guarda de update_fields (CLAUDE.md): escrita direcionada num objeto já
    persistido não revalida o objeto inteiro. Sem o guarda, o full_clean tropeça
    no campo intocado e a gravação do campo pedido falha."""
    turma = Turma.objects.create(curso=curso_publicado, professor=professor, **dados_turma())
    turma.data_fim = datetime.date(2020, 1, 1)  # inválido, e fora de update_fields
    turma.local = "Escola Nova"
    turma.save(update_fields=["local"])
    turma.refresh_from_db()
    assert turma.local == "Escola Nova"
    assert turma.data_fim == dados_turma()["data_fim"]


@pytest.mark.django_db
def test_save_de_participante_valida_o_objeto(curso_publicado, professor):
    turma = Turma.objects.create(curso=curso_publicado, professor=professor, **dados_turma())
    with pytest.raises(ValidationError):
        Participante.objects.create(turma=turma, nome="Maria", email="nao-e-um-email")


@pytest.mark.django_db
def test_save_de_participante_com_update_fields_nao_revalida(curso_publicado, professor):
    turma = Turma.objects.create(curso=curso_publicado, professor=professor, **dados_turma())
    participante = Participante.objects.create(turma=turma, nome="Maria")
    participante.email = "nao-e-um-email"
    participante.nome = "Maria Silva"
    participante.save(update_fields=["nome"])
    participante.refresh_from_db()
    assert participante.nome == "Maria Silva"
    assert participante.email == ""


def test_rotulos_acentuados_e_valores_sem_acento():
    """Texto ao usuário em português acentuado; valor gravado sem acento e nunca
    alterado por passada de texto (CLAUDE.md)."""
    rotulos = dict(Turma.SITUACOES)
    assert rotulos[Turma.CONCLUIDA] == "Concluída"
    assert Turma._meta.get_field("status").verbose_name == "situação"
    assert Turma._meta.get_field("observacoes").verbose_name == "observações"
    assert Turma._meta.get_field("solicitacao").verbose_name == "solicitação de origem"
    assert [valor for valor, _ in Turma.SITUACOES] == [
        "AGENDADA", "EM_ANDAMENTO", "CONCLUIDA", "CANCELADA"
    ]
    # Participante não tem nenhum rótulo com acento hoje - todos os nomes dos
    # campos dele são palavras sem acento em português. As asserções abaixo
    # existem para que renomear qualquer um deles para uma forma errada (ou para
    # inglês) apareça, não porque haja acento a defender aqui (achado da revisão:
    # o teste ignorava Participante por completo).
    assert Participante._meta.verbose_name == "participante"
    assert Participante._meta.verbose_name_plural == "participantes"
    assert Participante._meta.get_field("email").verbose_name == "e-mail"
    assert Participante._meta.get_field("telefone").verbose_name == "telefone"
    assert Participante._meta.get_field("criado_em").verbose_name == "criado em"


# Radicais, não nomes exatos: a versão anterior deste teste comparava contra seis
# nomes fechados e deixava passar frequencia_percentual, nota_final e
# certificado_emitido_em - três campos do módulo de execução atravessando a cerca
# da spec 1.1 em silêncio (achado da revisão). Casar por substring erra para o
# lado estrito de propósito: um campo futuro chamado "anotacoes" bateria em
# "nota" e precisaria ser renomeado ou o radical, afrouxado conscientemente.
RADICAIS_DO_MODULO_DE_EXECUCAO = ("frequencia", "presenca", "nota", "certificado", "avaliacao")


def test_nenhum_model_do_app_tem_campo_do_modulo_de_execucao():
    """Fronteira do módulo de execução (spec 1.1): frequência, avaliação e
    certificado são de outro módulo. Varre todos os models do app, não um par
    fixo - um model novo nasce dentro da cerca, não fora dela."""
    infratores = [
        f"{model.__name__}.{campo.name}"
        for model in registro_de_apps.get_app_config("turmas").get_models()
        for campo in model._meta.get_fields()
        if any(radical in campo.name.lower() for radical in RADICAIS_DO_MODULO_DE_EXECUCAO)
    ]
    assert infratores == []


def test_a_cerca_da_fronteira_enxerga_todos_os_models_do_app():
    """O teste acima só vale se a varredura realmente alcançar os models. Sem
    isto, um get_models() vazio o deixaria verde para sempre."""
    varridos = {m.__name__ for m in registro_de_apps.get_app_config("turmas").get_models()}
    assert {"Turma", "Participante"} <= varridos


# --- admin: dado pessoal de terceiro (spec 10) -------------------------------


def _requisicao(usuario):
    requisicao = RequestFactory().get("/admin/turmas/turma/")
    requisicao.user = usuario
    return requisicao


@pytest.fixture
def duas_turmas(curso_publicado, professor, outro_professor):
    minha = Turma.objects.create(curso=curso_publicado, professor=professor, **dados_turma())
    alheia = Turma.objects.create(curso=curso_publicado, professor=outro_professor, **dados_turma())
    Participante.objects.create(turma=minha, nome="Maria", email="maria@exemplo.br")
    Participante.objects.create(turma=alheia, nome="João", email="joao@exemplo.br")
    return minha, alheia


@pytest.mark.django_db
def test_professor_nao_ve_turma_alheia(duas_turmas, professor):
    minha, alheia = duas_turmas
    visiveis = TurmaAdmin(Turma, AdminSite()).get_queryset(_requisicao(professor))
    assert list(visiveis) == [minha]
    assert alheia not in visiveis


def _da_acesso_ao_admin(usuario):
    """Habilita o usuário no Admin com as permissões de turma e participante.
    Nenhuma delas é o recorte por professor - o recorte é do get_queryset, e é
    justamente isso que o teste abaixo precisa exercitar sem que a permissão do
    Django o esconda antes."""
    usuario.is_staff = True
    usuario.save()
    usuario.user_permissions.add(
        *Permission.objects.filter(
            codename__in=[
                "view_turma", "change_turma", "view_participante", "change_participante",
            ]
        )
    )
    return usuario


@pytest.mark.django_db
def test_professor_nao_ve_participante_de_turma_alheia(client, duas_turmas, professor):
    """O participante é dado pessoal de terceiro externo (spec 10): esconder a
    turma alheia é o que esconde a lista de participantes dela.

    Passa por uma requisição de verdade ao /admin/, não por um queryset montado
    aqui: a versão anterior calculava Participante.objects.filter(turma__in=...)
    dentro do próprio teste e portanto só afirmava sobre a própria aritmética,
    sem tocar em nenhuma linha de código de participante (achado da revisão).
    A revisão também estabeleceu que o único ponto que vaza é
    TurmaAdmin.get_queryset - o formset do inline refiltra pelo pai - e é por ele
    que este teste entra, via get_object da tela de alteração.
    """
    minha, alheia = duas_turmas
    client.force_login(_da_acesso_ao_admin(professor))

    # Controle positivo: na turma dele, o participante dele aparece de verdade.
    pagina_minha = client.get(reverse("admin:turmas_turma_change", args=[minha.pk]))
    assert pagina_minha.status_code == 200
    assert "Maria" in pagina_minha.content.decode()

    # E a turma alheia não abre - nem o nome do participante dela escapa.
    pagina_alheia = client.get(
        reverse("admin:turmas_turma_change", args=[alheia.pk]), follow=True
    )
    assert "João" not in pagina_alheia.content.decode()


@pytest.mark.django_db
def test_coordenador_ve_todas_as_turmas(duas_turmas, coordenador):
    visiveis = TurmaAdmin(Turma, AdminSite()).get_queryset(_requisicao(coordenador))
    assert set(visiveis) == set(duas_turmas)


@pytest.mark.django_db
def test_participante_nao_tem_porta_propria_no_admin():
    """Registrado só como inline de TurmaAdmin: uma tela própria de Participante
    daria ao professor a lista inteira, contornando o recorte por turma."""
    assert Participante not in admin.site._registry


@pytest.mark.django_db
def test_coordenador_pode_ser_designado_para_conduzir_turma(solicitacao, coordenador):
    """Regra 1 do Plano 5: o coordenador e professor, e `Turma.clean` o aceita.

    A designacao pelo servico e o que importa -- e o caminho que o Plano 3 ja
    usava para o professor.
    """
    turma = services.aceitar_solicitacao(
        solicitacao, professor=coordenador, dados_turma=dados_turma(), por=coordenador
    )
    assert turma.professor == coordenador


@pytest.mark.django_db
def test_o_formulario_de_turma_oferece_o_coordenador(coordenador, professor):
    """A guarda e do modelo; esta e a conveniencia da tela. Sem este teste, o
    queryset do formulario pode voltar a filtrar so PROFESSOR e ficar mais estrito
    que `Turma.clean` -- a coordenacao nao conseguiria designar a si mesma, e nada
    acusaria (a mutacao sobreviveu a suite inteira na Task 1 do Plano 5).
    """
    from apps.turmas.forms import TurmaForm

    oferecidos = set(TurmaForm().fields["professor"].queryset)
    assert coordenador in oferecidos
    assert professor in oferecidos


@pytest.mark.django_db
def test_o_formulario_de_turma_nao_oferece_aluno(aluno):
    from apps.turmas.forms import TurmaForm

    assert aluno not in set(TurmaForm().fields["professor"].queryset)
