import datetime
import uuid

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.contas import services
from apps.contas.models import ConviteAluno, Usuario
from apps.notificacoes.models import Notificacao


@pytest.fixture
def recem_alocado(db):
    aluno = Usuario.objects.create_user(
        email="novo@acad.ufsm.br", nome_completo="Novo Aluno",
        cpf=None, papel=Usuario.ALUNO, password=None,
    )
    aluno.set_unusable_password()
    aluno.save(update_fields=["password"])
    return aluno


def perfil():
    return {"cpf": "071.620.218-24", "matricula": "201910101", "telefone": "(55) 99999-1234"}


@pytest.mark.django_db
def test_convite_dura_sete_dias(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    esperado = timezone.now() + datetime.timedelta(days=7)
    assert abs((convite.expira_em - esperado).total_seconds()) < 60
    assert convite.valido is True


@pytest.mark.django_db
def test_convite_avisa_o_aluno_por_e_mail(recem_alocado, professor):
    services.convidar(recem_alocado, por=professor)
    fila = Notificacao.objects.filter(evento="CONVITE_ALUNO", destinatario=recem_alocado.email)
    assert fila.count() == 1


@pytest.mark.django_db
def test_o_e_mail_leva_o_token_e_nao_uma_senha(recem_alocado, professor):
    """Token de uso único, e não senha temporária: a fila de notificações fica
    gravada no banco, e uma senha em texto no corpo sobreviveria ali, legível por
    quem tem acesso ao Admin."""
    convite = services.convidar(recem_alocado, por=professor)
    corpo = Notificacao.objects.get(evento="CONVITE_ALUNO").corpo
    assert str(convite.token) in corpo
    assert recem_alocado.password not in corpo


@pytest.mark.django_db
def test_consumir_completa_o_perfil_e_define_a_senha(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    aluno = services.consumir_convite(convite.token, senha="uma-senha-de-verdade-123", **perfil())
    aluno.refresh_from_db()
    assert aluno.perfil_completo is True
    assert aluno.check_password("uma-senha-de-verdade-123")


@pytest.mark.django_db
def test_convite_e_de_uso_unico(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    services.consumir_convite(convite.token, senha="uma-senha-de-verdade-123", **perfil())
    with pytest.raises(ValidationError):
        services.consumir_convite(convite.token, senha="outra-senha-qualquer-456", **perfil())


@pytest.mark.django_db
def test_convite_vencido_e_recusado(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    ConviteAluno.objects.filter(pk=convite.pk).update(
        expira_em=timezone.now() - datetime.timedelta(minutes=1)
    )
    with pytest.raises(ValidationError):
        services.consumir_convite(convite.token, senha="uma-senha-de-verdade-123", **perfil())


@pytest.mark.django_db
def test_token_inexistente_e_recusado(db):
    with pytest.raises(ValidationError):
        services.consumir_convite(uuid.uuid4(), senha="uma-senha-de-verdade-123", **perfil())


@pytest.mark.django_db
def test_reenviar_invalida_o_convite_anterior(recem_alocado, professor):
    """Regra 3: o professor reenvia. O convite antigo morre no reenvio -- dois
    links válidos ao mesmo tempo dobram a janela em que um token vazado serve."""
    primeiro = services.convidar(recem_alocado, por=professor)
    segundo = services.convidar(recem_alocado, por=professor)
    primeiro.refresh_from_db()
    assert primeiro.valido is False
    assert segundo.valido is True


@pytest.mark.django_db
def test_o_token_antigo_deixa_de_funcionar_apos_reenvio(recem_alocado, professor):
    """O `valido` do teste anterior é uma propriedade; esta é a consequência que
    importa -- o link do primeiro e-mail não abre mais nada."""
    primeiro = services.convidar(recem_alocado, por=professor)
    services.convidar(recem_alocado, por=professor)
    with pytest.raises(ValidationError):
        services.consumir_convite(primeiro.token, senha="uma-senha-de-verdade-123", **perfil())


@pytest.mark.django_db
def test_consumir_recusa_cpf_invalido(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    dados = perfil()
    dados["cpf"] = "111.111.111-11"
    with pytest.raises(ValidationError):
        services.consumir_convite(convite.token, senha="uma-senha-de-verdade-123", **dados)
    recem_alocado.refresh_from_db()
    assert recem_alocado.perfil_completo is False


@pytest.mark.django_db
def test_consumir_recusa_senha_fraca(recem_alocado, professor):
    convite = services.convidar(recem_alocado, por=professor)
    with pytest.raises(ValidationError):
        services.consumir_convite(convite.token, senha="123", **perfil())


@pytest.mark.django_db
def test_perfil_invalido_nao_gasta_o_convite(recem_alocado, professor):
    """CPF de outra pessoa: recusado, e o convite continua servindo.

    Este NAO e um teste de atomicidade -- a colisao estoura no `full_clean()`
    antes de qualquer escrita, entao ele passa com ou sem `@transaction.atomic`
    (conferido por delecao). O que ele prende e a regra de negocio: perfil
    invalido nao queima o link.
    """
    Usuario.objects.create_user(
        email="dono.do.cpf@acad.ufsm.br", nome_completo="Dono do CPF",
        cpf="071.620.218-24", papel=Usuario.ALUNO, matricula="209999999", password=None,
    )
    convite = services.convidar(recem_alocado, por=professor)
    with pytest.raises(ValidationError):
        services.consumir_convite(convite.token, senha="uma-senha-de-verdade-123", **perfil())
    convite.refresh_from_db()
    recem_alocado.refresh_from_db()
    assert convite.usado_em is None
    assert recem_alocado.perfil_completo is False
    assert recem_alocado.has_usable_password() is False


@pytest.mark.django_db
def test_consumir_e_atomico(recem_alocado, professor, monkeypatch):
    """Atomicidade de verdade: a falha vem DEPOIS de o usuario ja ter sido
    gravado, no `save()` do convite.

    Sem `@transaction.atomic`, o aluno ficaria com senha definida e perfil
    completo enquanto o convite seguisse por usar -- um link ainda valido para
    uma conta ja ativa, que qualquer pessoa com o e-mail antigo poderia abrir
    para trocar a senha.

    A primeira versao deste teste forcava colisao de CPF e nao provava nada: o
    erro nascia no `full_clean()`, antes de qualquer escrita, e a mutacao do
    decorador sobrevivia a suite inteira.
    """
    from apps.contas.models_convite import ConviteAluno as Modelo

    convite = services.convidar(recem_alocado, por=professor)
    original = Modelo.save

    def falha_ao_gastar(self, *args, **kwargs):
        if kwargs.get("update_fields") == ["usado_em"]:
            raise RuntimeError("banco caiu ao marcar o convite como usado")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Modelo, "save", falha_ao_gastar)

    with pytest.raises(RuntimeError):
        services.consumir_convite(convite.token, senha="uma-senha-de-verdade-123", **perfil())

    monkeypatch.undo()
    recem_alocado.refresh_from_db()
    convite.refresh_from_db()
    assert recem_alocado.perfil_completo is False
    assert recem_alocado.has_usable_password() is False
    assert convite.usado_em is None


@pytest.mark.django_db
def test_convidar_e_atomico(recem_alocado, professor, monkeypatch):
    """O convite e o aviso nascem juntos ou nao nascem.

    Sem `@transaction.atomic`, uma falha ao enfileirar deixaria um convite
    gravado que ninguem sabe que existe: o aluno nunca recebe o link, e o
    professor ve na tela que "o convite foi enviado". Pior no reenvio, onde o
    convite anterior ja foi cancelado -- a pessoa ficaria com dois links mortos.
    """
    from apps.contas import services as servicos

    def explode(*args, **kwargs):
        raise RuntimeError("fila fora do ar")

    anterior = services.convidar(recem_alocado, por=professor)
    monkeypatch.setattr(servicos, "enfileirar", explode)

    with pytest.raises(RuntimeError):
        services.convidar(recem_alocado, por=professor)

    monkeypatch.undo()
    anterior.refresh_from_db()
    assert ConviteAluno.objects.filter(usuario=recem_alocado).count() == 1
    assert anterior.valido is True, "o convite anterior nao pode ter sido cancelado a toa"
