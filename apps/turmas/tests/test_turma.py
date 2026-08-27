import datetime

import pytest
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import ProtectedError
from django.test import RequestFactory

from apps.catalogo.models import Solicitacao
from apps.cursos import services as servicos_curso
from apps.cursos.choices import StatusEntregavel
from apps.notificacoes.models import Notificacao
from apps.turmas import services
from apps.turmas.admin import TurmaAdmin
from apps.turmas.models import Participante, Turma


@pytest.fixture
def curso_publicado(dados_curso, outro_aluno, professor, coordenador):
    # adicionar_membro tira o curso de RASCUNHO para EM_PRODUCAO; sem isso
    # submeter_ao_coordenador recusa por status, não pelos entregáveis (mesma
    # lacuna já documentada nos conftests de catalogo).
    curso = servicos_curso.criar_curso(**dados_curso)
    servicos_curso.adicionar_membro(curso, outro_aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    servicos_curso.submeter_ao_coordenador(curso, por=professor)
    servicos_curso.publicar_curso(curso, por=coordenador)
    return curso


@pytest.fixture
def solicitacao(curso_publicado):
    return Solicitacao.objects.create(
        curso=curso_publicado, nome="Escola São José", email="direcao@escola.exemplo.br",
        num_participantes=25, instituicao="EMEF São José",
    )


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


def test_turma_nao_tem_campo_de_frequencia_nem_certificado():
    """Fronteira do módulo de execução (spec 1.1): se um destes campos aparecer,
    a fronteira foi atravessada sem querer."""
    campos = {c.name for c in Turma._meta.get_fields()} | {
        c.name for c in Participante._meta.get_fields()
    }
    proibidos = {"frequencia", "presenca", "nota", "certificado", "certificado_emitido", "avaliacao"}
    assert campos & proibidos == set()


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


@pytest.mark.django_db
def test_professor_nao_ve_participante_de_turma_alheia(duas_turmas, professor):
    """O participante é dado pessoal de terceiro externo (spec 10): esconder a
    turma alheia é o que esconde a lista de participantes dela."""
    visiveis = TurmaAdmin(Turma, AdminSite()).get_queryset(_requisicao(professor))
    nomes = set(
        Participante.objects.filter(turma__in=visiveis).values_list("nome", flat=True)
    )
    assert nomes == {"Maria"}


@pytest.mark.django_db
def test_coordenador_ve_todas_as_turmas(duas_turmas, coordenador):
    visiveis = TurmaAdmin(Turma, AdminSite()).get_queryset(_requisicao(coordenador))
    assert set(visiveis) == set(duas_turmas)


@pytest.mark.django_db
def test_participante_nao_tem_porta_propria_no_admin():
    """Registrado só como inline de TurmaAdmin: uma tela própria de Participante
    daria ao professor a lista inteira, contornando o recorte por turma."""
    assert Participante not in admin.site._registry
