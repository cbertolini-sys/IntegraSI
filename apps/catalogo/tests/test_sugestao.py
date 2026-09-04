"""A comunidade sugere um curso que ainda nao existe.

O fluxograma da pagina Sobre tinha um laco sem saida: o no "Encontrou um curso
adequado?" so oferecia, no ramo Nao, "ajusta os filtros e procura de novo". Quem
procurava um curso que nao existe girava nos filtros ate desistir, e a
universidade nunca ficava sabendo que a demanda existiu. Este formulario e a
saida que faltava.

As defesas sao as mesmas da solicitacao, e de proposito: mesmo honeypot, mesmo
limite por IP por hora, mesma recusa silenciosa a robo. Formulario publico sem
isso e caixa de spam.
"""

import pytest
from django.urls import reverse

from apps.catalogo.models import SugestaoDeCurso
from apps.notificacoes.models import Notificacao


def dados_validos(**extra):
    return {
        "nome": "Marta Ribeiro",
        "email": "marta@escolamunicipal.exemplo",
        "telefone": "(55) 3333-1010",
        "instituicao": "EMEF Dom Pedro",
        "publico_alvo": "Turmas de 4º e 5º ano",
        "tem_laboratorio": SugestaoDeCurso.NAO,
        "demanda": "Queríamos algo sobre uso seguro de celular, com atividades sem tela.",
        "confirmacao": "",
        **extra,
    }


# --- o envio ------------------------------------------------------------------


@pytest.mark.django_db
def test_visitante_sugere_sem_login(client):
    """Sem `@login_required`: a demanda vem de quem esta de fora."""
    resposta = client.post(reverse("sugerir"), dados_validos(), follow=True)

    assert resposta.status_code == 200
    sugestao = SugestaoDeCurso.objects.get()
    assert sugestao.instituicao == "EMEF Dom Pedro"
    assert sugestao.status == SugestaoDeCurso.RECEBIDA


@pytest.mark.django_db
def test_a_sugestao_guarda_o_que_muda_o_curso_possivel(client):
    """Publico-alvo e laboratorio nao sao enfeite: sao o que decide qual curso da
    para oferecer. Enfiados em texto livre nao viravam filtro nem relatorio."""
    client.post(reverse("sugerir"), dados_validos(), follow=True)

    sugestao = SugestaoDeCurso.objects.get()
    assert sugestao.publico_alvo == "Turmas de 4º e 5º ano"
    assert sugestao.tem_laboratorio == SugestaoDeCurso.NAO
    assert "sem tela" in sugestao.demanda


@pytest.mark.django_db
def test_a_coordenacao_e_avisada_e_o_professor_nao(client, coordenador, professor):
    """So a coordenacao: nao ha curso, logo nao ha professor responsavel a quem
    dar copia. Usa a mesma consulta unificada em `contas.services`."""
    client.post(reverse("sugerir"), dados_validos(), follow=True)

    avisos = Notificacao.objects.filter(evento="SUGESTAO_RECEBIDA")
    destinatarios = set(avisos.values_list("destinatario", flat=True))
    assert destinatarios == {coordenador.email}
    assert professor.email not in destinatarios


@pytest.mark.django_db
def test_o_aviso_traz_o_que_a_coordenacao_precisa_para_decidir(client, coordenador):
    client.post(reverse("sugerir"), dados_validos(), follow=True)

    corpo = Notificacao.objects.get(evento="SUGESTAO_RECEBIDA").corpo
    assert "EMEF Dom Pedro" in corpo
    assert "Turmas de 4º e 5º ano" in corpo
    assert "sem tela" in corpo


# --- as defesas ---------------------------------------------------------------


@pytest.mark.django_db
def test_robo_e_descartado_em_silencio(client):
    """Campo invisivel preenchido: nada e gravado, e a tela responde como se
    tivesse dado certo. Dizer "voce e um robo" ensina o robo a passar."""
    resposta = client.post(
        reverse("sugerir"), dados_validos(confirmacao="sou um robo"), follow=True
    )

    assert resposta.status_code == 200
    assert not SugestaoDeCurso.objects.exists()


@pytest.mark.django_db
def test_limite_por_ip_por_hora(client):
    from apps.catalogo.views import LIMITE_POR_IP_POR_HORA

    for i in range(LIMITE_POR_IP_POR_HORA):
        client.post(reverse("sugerir"), dados_validos(nome=f"Pessoa {i}"), follow=True)
    assert SugestaoDeCurso.objects.count() == LIMITE_POR_IP_POR_HORA

    resposta = client.post(reverse("sugerir"), dados_validos(nome="A mais"), follow=True)

    assert SugestaoDeCurso.objects.count() == LIMITE_POR_IP_POR_HORA
    assert "Muitas sugestões deste endereço" in resposta.content.decode()


@pytest.mark.django_db
def test_a_demanda_e_obrigatoria(client):
    """E o campo que da sentido a sugestao: sem ele sobra um contato sem pedido."""
    resposta = client.post(reverse("sugerir"), dados_validos(demanda=""))

    assert resposta.status_code == 200
    assert not SugestaoDeCurso.objects.exists()


# --- a porta de entrada -------------------------------------------------------


@pytest.mark.django_db
def test_a_busca_vazia_oferece_sugerir(client):
    """O ramo Nao do fluxograma. Sem isto o formulario existe e ninguem acha: quem
    procurou e nao encontrou e exatamente quem tem uma sugestao a dar."""
    html = client.get(reverse("catalogo"), {"busca": "assunto que nao existe"}).content.decode()

    assert reverse("sugerir") in html
