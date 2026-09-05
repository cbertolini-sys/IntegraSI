"""A coordenacao responde as sugestoes de curso.

Mais simples que responder uma solicitacao, e por um motivo de dominio: aceitar
uma solicitacao cria turma de um curso pronto, e aceitar uma sugestao nao cria
nada. Ela diz "vamos produzir isto", e a producao comeca depois, quando um
professor abre a proposta. Por isso nao ha formulario de turma aqui, e por isso a
resposta escrita e obrigatoria nos dois desfechos: e a unica coisa que a pessoa
que sugeriu vai receber.
"""

import re

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.catalogo.models import SugestaoDeCurso
from apps.notificacoes.models import Notificacao
from apps.turmas import services


@pytest.fixture
def sugestao(db):
    return SugestaoDeCurso.objects.create(
        nome="Marta Ribeiro",
        email="marta@escolamunicipal.exemplo",
        instituicao="EMEF Dom Pedro",
        publico_alvo="Turmas de 4º e 5º ano",
        tem_laboratorio=SugestaoDeCurso.NAO,
        demanda="Uso seguro de celular, com atividades sem tela.",
    )


# --- os servicos --------------------------------------------------------------


@pytest.mark.django_db
def test_a_coordenacao_aceita_e_quem_sugeriu_e_avisado(sugestao, coordenador):
    services.aceitar_sugestao(sugestao, por=coordenador, resposta="Vamos produzir este curso.")
    sugestao.refresh_from_db()

    assert sugestao.status == SugestaoDeCurso.ACEITA
    aviso = Notificacao.objects.get(evento="SUGESTAO_ACEITA")
    assert aviso.destinatario == "marta@escolamunicipal.exemplo"
    assert "Vamos produzir este curso." in aviso.corpo


@pytest.mark.django_db
def test_a_coordenacao_recusa_com_justificativa(sugestao, coordenador):
    services.recusar_sugestao(sugestao, por=coordenador, resposta="Não temos equipe este semestre.")
    sugestao.refresh_from_db()

    assert sugestao.status == SugestaoDeCurso.RECUSADA
    aviso = Notificacao.objects.get(evento="SUGESTAO_RECUSADA")
    assert "Não temos equipe" in aviso.corpo


@pytest.mark.django_db
@pytest.mark.parametrize("servico", ["aceitar_sugestao", "recusar_sugestao"])
def test_a_resposta_escrita_e_obrigatoria_nos_dois_desfechos(sugestao, coordenador, servico):
    """Aceitar uma solicitacao gera o texto sozinho, a partir da turma. Aqui nao
    ha turma nem curso: a resposta escrita e tudo o que a pessoa recebe, e uma
    aceitacao muda sem texto chegaria como um e-mail vazio."""
    with pytest.raises(ValidationError):
        getattr(services, servico)(sugestao, por=coordenador, resposta="   ")


@pytest.mark.django_db
@pytest.mark.parametrize("servico", ["aceitar_sugestao", "recusar_sugestao"])
def test_professor_nao_responde_sugestao(sugestao, professor, servico):
    """Decisao do produto, confirmada por você: so a coordenacao. Nao ha professor
    responsavel, porque nao ha curso."""
    with pytest.raises(PermissionDenied):
        getattr(services, servico)(sugestao, por=professor, resposta="Pode ser.")


@pytest.mark.django_db
def test_nao_se_responde_duas_vezes(sugestao, coordenador):
    services.aceitar_sugestao(sugestao, por=coordenador, resposta="Vamos produzir.")

    with pytest.raises(ValidationError):
        services.recusar_sugestao(sugestao, por=coordenador, resposta="Mudei de ideia.")


# --- a tela -------------------------------------------------------------------


@pytest.mark.django_db
def test_a_lista_mostra_a_sugestao_pendente(client, sugestao, coordenador):
    client.force_login(coordenador)
    html = client.get(reverse("sugestoes")).content.decode()

    assert "EMEF Dom Pedro" in html
    assert "Turmas de 4º e 5º ano" in html


@pytest.mark.django_db
def test_a_lista_de_sugestoes_e_so_da_coordenacao(client, sugestao, professor):
    """Guarda propria da view, e nao so a do servico: o GET nao chama servico
    nenhum, entao e o unico caminho que a prende sozinha."""
    client.force_login(professor)

    assert client.get(reverse("sugestoes")).status_code == 403


@pytest.mark.django_db
def test_a_coordenacao_responde_pela_tela(client, sugestao, coordenador):
    client.force_login(coordenador)

    client.post(
        reverse("responder_sugestao", args=[sugestao.pk]),
        {"decisao": "ACEITAR", "resposta": "Entrou na fila de produção."},
        follow=True,
    )
    sugestao.refresh_from_db()

    assert sugestao.status == SugestaoDeCurso.ACEITA
    assert Notificacao.objects.filter(evento="SUGESTAO_ACEITA").exists()


# --- a porta e o conteudo da lista --------------------------------------------


@pytest.mark.django_db
def test_o_painel_conta_todas_as_sugestoes_e_nao_so_as_pendentes(
    client, sugestao, coordenador
):
    """O cartao diz "Sugestões recebidas", entao conta as recebidas.

    Os outros cartoes da coordenacao contam trabalho a fazer ("Aguardando
    aprovação", "Solicitações a responder"), e este poderia seguir o mesmo padrao.
    Segue o de "Cursos no catálogo", que e inventario, porque a porta que ele abre
    e a lista inteira do que a comunidade pediu - e um numero que zera quando a
    ultima e respondida esconderia justamente o historico que da valor a essa
    tela.
    """
    services.aceitar_sugestao(sugestao, por=coordenador, resposta="Vamos produzir.")

    client.force_login(coordenador)
    html = client.get(reverse("painel")).content.decode()
    inicio = html.index("Sugestões recebidas")
    cartao = html[max(0, inicio - 400) : inicio + 200]

    assert "Sugestões a responder" not in html
    assert ">1<" in cartao, "a sugestão respondida sumiu da contagem"


@pytest.mark.django_db
def test_a_lista_mostra_o_que_foi_sugerido_e_nao_so_quem_sugeriu(
    client, sugestao, coordenador
):
    """A lista abria com o nome da instituição, e o que a pessoa pediu ficava de
    fora. Quem coordena olha essa tela para decidir QUAL curso produzir, e para
    isso precisa ver a demanda: a instituição é contexto, não é o assunto.

    Nao ha campo de titulo, e nao deve haver: quem sugere descreve uma
    necessidade, e obrigar a resumi-la num titulo antes de contar qual e faria a
    pessoa inventar um rotulo em vez de explicar o problema.
    """
    client.force_login(coordenador)
    html = client.get(reverse("sugestoes")).content.decode()
    inicio = html.index("A responder")
    fim = html.index("Já respondidas")
    registro = html[inicio:fim]
    titulo = re.search(r"<h3>.*?</h3>", registro, re.S).group(0)

    assert "celular" in titulo, titulo
    # A instituicao continua na tela, como contexto.
    assert "EMEF Dom Pedro" in registro


@pytest.mark.django_db
def test_o_detalhe_mostra_tudo_o_que_a_pessoa_preencheu(client, sugestao, coordenador):
    """Campo que a pessoa preencheu e a tela nao mostra e trabalho perdido dos
    dois lados. Afirmado campo a campo, e nao por amostragem: acrescentar campo ao
    modelo e esquecer a tela e o defeito que este teste existe para pegar."""
    client.force_login(coordenador)
    html = client.get(reverse("responder_sugestao", args=[sugestao.pk])).content.decode()

    for valor in [
        sugestao.nome,
        sugestao.instituicao,
        sugestao.email,
        sugestao.publico_alvo,
        sugestao.demanda,
        sugestao.get_tem_laboratorio_display(),
    ]:
        assert valor in html, valor
