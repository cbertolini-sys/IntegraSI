from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.contas.models import ConviteAluno
from apps.notificacoes.services import enfileirar

CORPO_CONVITE = """Olá, {nome}.

{quem} incluiu você na equipe de produção de um curso de extensão no IntegraSI,
o sistema do curso de Sistemas de Informação da UFSM em Frederico Westphalen.

Para entrar pela primeira vez, abra o endereço abaixo. Você vai criar sua senha e
completar o cadastro com CPF, matrícula e telefone.

{url}

O link vale por 7 dias e só pode ser usado uma vez. Se ele vencer, peça a
{quem} para enviar outro.
"""


@transaction.atomic
def convidar(usuario, por, base_url=""):
    """Cria o convite de primeiro acesso e enfileira o e-mail.

    Invalida os convites anteriores da mesma pessoa: dois links válidos ao mesmo
    tempo dobram a janela em que um token vazado ainda serve.

    O e-mail sai pela fila de `notificacoes`, como todo o resto do sistema: SMTP
    fora do ar não pode derrubar a alocação de um aluno (spec 9).
    """
    ConviteAluno.objects.filter(
        usuario=usuario, usado_em__isnull=True, cancelado_em__isnull=True
    ).update(cancelado_em=timezone.now())

    convite = ConviteAluno.objects.create(
        usuario=usuario, criado_por=por, expira_em=timezone.now() + ConviteAluno.PRAZO
    )
    enfileirar(
        evento="CONVITE_ALUNO",
        destinatarios=[usuario.email],
        assunto="Seu acesso ao IntegraSI",
        corpo=CORPO_CONVITE.format(
            nome=usuario.nome_completo,
            quem=por.nome_completo,
            url=f"{base_url}/convite/{convite.token}/",
        ),
    )
    return convite


@transaction.atomic
def consumir_convite(token, senha, cpf, matricula, telefone):
    """Completa o perfil e define a senha, gastando o convite.

    Tudo numa transação: uma senha recusada, ou um CPF que colida com o de outra
    pessoa, não pode deixar o convite marcado como usado -- a pessoa ficaria sem
    link e sem conta utilizável, e só a coordenação a destravaria.
    """
    convite = ConviteAluno.objects.select_for_update().filter(token=token).first()
    if convite is None or not convite.valido:
        raise ValidationError("Este convite não vale mais. Peça outro ao professor.")

    usuario = convite.usuario
    validate_password(senha, usuario)

    usuario.cpf = cpf
    usuario.matricula = matricula
    usuario.telefone = telefone
    usuario.set_password(senha)
    usuario.save()

    convite.usado_em = timezone.now()
    convite.save(update_fields=["usado_em"])
    return usuario
