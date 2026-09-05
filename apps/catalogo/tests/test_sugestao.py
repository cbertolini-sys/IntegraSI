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


# --- a tela --------------------------------------------------------------------


@pytest.mark.django_db
def test_a_tela_usa_o_desenho_de_campo_do_projeto(client):
    """`_campo.html`, e nao o `as_p` do Django.

    Dele vem o `.campo`, o rotulo com o gatilho de ajuda e o balao. Com `as_p` a
    ajuda vira parágrafo solto sob cada campo, o radio de laboratório sai como
    lista sem desenho, e a tela deixa de se parecer com o resto do sistema. A
    afirmação é sobre o que o `_campo.html` PRODUZ, e não sobre o `{% include %}`
    estar escrito: trocar a inclusão por `as_p` tem que reprovar.
    """
    html = client.get(reverse("sugerir")).content.decode()

    assert 'class="campo' in html
    assert 'class="ajuda-campo"' in html
    assert "<p><label" not in html, "voltou para o as_p do Django"


@pytest.mark.django_db
def test_a_tela_sabe_voltar_no_lugar_de_sempre(client):
    """Pagina publica e folha: sem a volta, so o botao do navegador sai dela.

    E a volta fica ONDE ELA FICA no resto do sistema: dentro do `.acoes` da
    `.cabecalho-pagina`, a direita do titulo. A primeira versao desta tela
    inventou um `.voltar-topo` proprio, num paragrafo acima do `<h1>`, e ficou
    diferente de todas as outras - foi visto olhando a tela, com a suite verde.

    O recorte pelo `.acoes` e o que faz a afirmacao ser sobre o LUGAR: procurar o
    link na pagina inteira passaria verde com ele solto em qualquer canto.
    """
    html = client.get(reverse("sugerir")).content.decode()
    inicio = html.index('class="acoes"')
    acoes = html[inicio : html.index("</div>", inicio)]

    assert f'href="{reverse("catalogo")}"' in acoes, acoes
    assert "Voltar ao catálogo" in acoes


@pytest.mark.django_db
def test_o_laboratorio_e_uma_lista_com_as_tres_opcoes(client):
    """Lista, e nao radio: sao tres opções curtas no meio de um formulário de
    campos de uma linha, e o radio empilhava três linhas quebrando o ritmo da
    coluna.

    A opção vazia fica, e com rótulo de verdade: `---------` é o que o Django põe
    sozinho, e num formulário público lido por quem nunca viu o sistema isso não
    diz nada. Ela precisa existir para a escolha ser deliberada, e não a primeira
    opção por omissão.
    """
    html = client.get(reverse("sugerir")).content.decode()
    inicio = html.index('name="tem_laboratorio"')
    campo = html[html.rindex("<select", 0, inicio) : html.index("</select>", inicio)]

    assert "---------" not in campo, campo
    assert "Selecione" in campo
    for rotulo in ["Sim", "Não", "Não sei informar"]:
        assert f">{rotulo}</option>" in campo, rotulo
