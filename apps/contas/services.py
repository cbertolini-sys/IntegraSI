from django.contrib.auth.password_validation import validate_password
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.contas.models import ConviteAluno, Usuario
from apps.notificacoes.services import enfileirar

# Sem saudacao pelo nome: a conta do aluno tambem nasce so com o e-mail, entao
# nao ha nome para saudar ate ele mesmo escrever o dele no primeiro acesso.
CORPO_CONVITE = """Olá.

{quem} incluiu você na equipe de produção de um curso de extensão no IntegraSI,
o sistema do curso de Sistemas de Informação da UFSM em Frederico Westphalen.

Para entrar pela primeira vez, abra o endereço abaixo. Você vai criar sua senha e
completar o cadastro com nome, CPF, matrícula e telefone.

{url}

O link vale por 7 dias e só pode ser usado uma vez. Se ele vencer, peça a
{quem} para enviar outro.
"""

# O convite do professor e outro texto porque quem o cadastra e a coordenacao, e
# nao um professor montando equipe: nao ha curso que o inclua, e os campos que ele
# preenche sao CPF e SIAPE, nao matricula e telefone.
CORPO_CONVITE_PROFESSOR = """Olá.

{quem} cadastrou você como professor no IntegraSI, o sistema de produção de cursos
de extensão do curso de Sistemas de Informação da UFSM em Frederico Westphalen.

Para entrar pela primeira vez, abra o endereço abaixo. Você vai criar sua senha e
completar o cadastro com nome, CPF e SIAPE.

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
    url = f"{base_url}/convite/{convite.token}/"
    if usuario.e_aluno:
        corpo = CORPO_CONVITE.format(quem=por.nome_completo, url=url)
    else:
        corpo = CORPO_CONVITE_PROFESSOR.format(quem=por.nome_completo, url=url)
    enfileirar(
        evento="CONVITE_ALUNO",
        destinatarios=[usuario.email],
        assunto="Seu acesso ao IntegraSI",
        corpo=corpo,
    )
    return convite


@transaction.atomic
def criar_professor(email, por, base_url=""):
    """Cria a conta de um professor com o e-mail, e mais nada.

    So a coordenacao: professor nao cadastra professor (decisao do produto). O
    resto - nome, CPF e SIAPE - vem no primeiro acesso, como ja acontecia com o
    aluno: quem exige os campos e aquela tela, e nao o modelo.

    Conta e convite nascem juntos, pelo mesmo motivo de `alocar_aluno`: uma conta
    sem convite fica inalcancavel, e o e-mail fica queimado porque a segunda
    tentativa bate na recusa de e-mail ja cadastrado.
    """
    _garante_coordenacao(por, "Somente a coordenação cadastra professor.")
    email = (email or "").strip().lower()
    if not email:
        raise ValidationError("Informe o e-mail do professor.")
    if Usuario.objects.filter(email__iexact=email).exists():
        raise ValidationError("Já existe conta com este e-mail.")

    # `password=None` deixa a senha inutilizavel: so o convite abre a conta.
    professor = Usuario.objects.create_user(
        email=email, nome_completo="", papel=Usuario.PROFESSOR, password=None
    )
    convidar(professor, por=por, base_url=base_url)
    return professor


@transaction.atomic
def consumir_convite(token, senha, cpf, matricula, telefone, nome=None, siape=None):
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

    if nome is not None:
        usuario.nome_completo = nome
    usuario.cpf = cpf
    # Matricula e do aluno, SIAPE e do professor: cada tela manda o seu, e o
    # outro chega None. Gravar os dois cegamente violaria o `clean()`, que recusa
    # matricula em professor e SIAPE em aluno.
    if matricula is not None:
        usuario.matricula = matricula
    if siape is not None:
        usuario.siape = siape
    usuario.telefone = telefone
    usuario.set_password(senha)
    usuario.save()

    convite.usado_em = timezone.now()
    convite.save(update_fields=["usado_em"])
    return usuario


def emails_da_coordenacao():
    """Para quem vai o aviso que a coordenacao precisa ver.

    Publica e aqui, e nao repetida em cada chamador. Estava escrita duas vezes,
    identica, em `cursos.services` (submissao de curso) e `catalogo.views`
    (solicitacao da comunidade). Duas copias iguais nao quebram nada enquanto a
    regra nao muda, e esta regra ja mostrou que vai mudar: em 04/09 um coordenador
    com endereco inexistente gerou devolucao a cada aviso. "Excluir coordenador
    sem endereco entregavel" e o tipo de ajuste que se faz num arquivo e se
    esquece no outro.

    `is_active` faz parte da regra: desativar a conta e o jeito de tirar alguem da
    lista de avisos sem apagar o historico dele.
    """
    return list(
        Usuario.objects.filter(papel=Usuario.COORDENADOR, is_active=True).values_list(
            "email", flat=True
        )
    )


def _garante_coordenacao(por, mensagem):
    """Checagem local, e não `cursos.permissions.pode_publicar`.

    Duas razões. A dependência do projeto é de mão única -- `cursos` conhece
    `contas`, e o contrário fecharia ciclo com o import de `alocar_aluno`. E a
    regra é outra: `pode_publicar` responde "quem leva um curso ao catálogo";
    aqui a pergunta é "quem administra pessoas". Coincidem hoje e podem divergir.
    """
    from django.core.exceptions import PermissionDenied

    if por is None or not por.e_coordenador:
        raise PermissionDenied(mensagem)


@transaction.atomic
def promover_a_coordenador(usuario, por):
    """Dá nível de acesso Admin a um professor (regra 1 do Plano 5)."""
    _garante_coordenacao(por, "Somente a coordenação promove.")
    if not usuario.e_somente_professor:
        raise ValidationError("Só professor vira coordenador.")
    usuario.papel = Usuario.COORDENADOR
    usuario.is_staff = True
    # update_fields pula o full_clean pela guarda do modelo, e aqui e o que se
    # quer: os campos mudados sao exatamente dois, e o objeto ja era valido.
    usuario.save(update_fields=["papel", "is_staff"])
    return usuario


@transaction.atomic
def rebaixar_a_professor(usuario, por):
    """Tira o nível Admin, deixando a pessoa como professor.

    Ninguém rebaixa a si mesmo: além da decisão registrada no Plano 5, é o que
    impede o último coordenador de deixar o sistema sem quem publique curso,
    aceite solicitação ou promova alguém de volta.
    """
    _garante_coordenacao(por, "Somente a coordenação rebaixa.")
    if usuario.pk == por.pk:
        raise ValidationError("Você não pode rebaixar a si mesmo.")
    if not usuario.e_coordenador:
        raise ValidationError("Esta pessoa não é coordenadora.")
    usuario.papel = Usuario.PROFESSOR
    usuario.is_staff = False
    usuario.save(update_fields=["papel", "is_staff"])
    return usuario


@dataclass(frozen=True)
class Exclusao:
    """O que aconteceu com a conta, e por que.

    Devolvido em vez de levantado: desativar nao e erro, e o caminho normal para
    quem produziu alguma coisa. Quem chama precisa da diferenca para escrever a
    mensagem certa, e `motivos` e o que transforma "não foi possível excluir" em
    algo que a pessoa entende.
    """

    apagada: bool
    motivos: tuple


def _o_que_prende(usuario):
    """O que essa conta deixaria orfao, LIDO DAS RELACOES DO MODELO.

    Nao e uma lista de nomes de propósito. Sao oito relacoes PROTECT apontando
    para `Usuario` hoje, e a regra pedida citava duas (equipe e responsavel).
    Quem so revisou um entregavel, ou so moveu um curso no fluxo, tambem prende a
    conta - e apagar mesmo assim estouraria `ProtectedError`, um 500 na cara de
    quem clicou.

    Lendo do modelo, um vinculo novo entra na conta sozinho. Escrito a mao, o
    proximo `PROTECT` que alguem acrescentar so apareceria em producao.

    E tambem por isto que `contas` continua sem importar `cursos`: a introspeccao
    nao precisa conhecer nenhum dos modelos que apontam para ca.
    """
    prendem = []
    for relacao in usuario._meta.related_objects:
        if getattr(relacao, "on_delete", None) is not models.PROTECT:
            continue
        quantos = relacao.related_model._default_manager.filter(
            **{relacao.field.name: usuario}
        ).count()
        if quantos:
            nome = relacao.related_model._meta.verbose_name_plural
            prendem.append(f"{quantos} {nome}")
    return tuple(prendem)


@transaction.atomic
def excluir_pessoa(usuario, por):
    """Apaga a conta, ou desativa quando ela deixou rastro de producao.

    Uma acao so na tela, e a decisao aqui: quem clica nao tem como saber se
    aquela pessoa revisou um entregavel dois semestres atras, e obrigar a
    descobrir antes de escolher o botao seria transferir o trabalho do sistema
    para a pessoa.
    """
    _garante_coordenacao(por, "Somente a coordenação exclui pessoas.")
    if usuario.pk == por.pk:
        # Mesma razao do rebaixamento: o Admin nao tem como recusar, e uma
        # coordenacao que se apaga deixa o sistema sem quem publique curso.
        raise ValidationError("Você não pode excluir a si mesmo.")
    if usuario.e_coordenador:
        outros = Usuario.objects.filter(
            papel=Usuario.COORDENADOR, is_active=True
        ).exclude(pk=usuario.pk)
        if not outros.exists():
            raise ValidationError(
                "Esta é a última coordenação ativa. Sem ela ninguém publica curso, "
                "aceita solicitação ou promove alguém de volta."
            )

    motivos = _o_que_prende(usuario)
    if motivos:
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        return Exclusao(apagada=False, motivos=motivos)

    usuario.delete()
    return Exclusao(apagada=True, motivos=())


@transaction.atomic
def reativar_pessoa(usuario, por):
    """Devolve o acesso a quem foi desativado. Sem isto, um clique errado seria
    permanente e so o Admin destravaria."""
    _garante_coordenacao(por, "Somente a coordenação reativa pessoas.")
    usuario.is_active = True
    usuario.save(update_fields=["is_active"])
    return usuario
