import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.contas import services
from apps.contas.models import Usuario


@pytest.mark.django_db
def test_coordenador_promove_professor(professor, coordenador):
    services.promover_a_coordenador(professor, por=coordenador)
    professor.refresh_from_db()
    assert professor.papel == Usuario.COORDENADOR
    assert professor.e_coordenador is True
    assert professor.e_professor is True


@pytest.mark.django_db
def test_coordenador_rebaixa_outro_coordenador(coordenador, outro_coordenador):
    services.rebaixar_a_professor(outro_coordenador, por=coordenador)
    outro_coordenador.refresh_from_db()
    assert outro_coordenador.papel == Usuario.PROFESSOR
    assert outro_coordenador.e_professor is True


@pytest.mark.django_db
def test_ninguem_rebaixa_a_si_mesmo(coordenador, outro_coordenador):
    """Decisão do coordenador. É também a rede de segurança do sistema: o último
    coordenador rebaixando a si mesmo deixaria o IntegraSI sem quem publique
    curso, aceite solicitação ou promova alguém de volta."""
    with pytest.raises(ValidationError):
        services.rebaixar_a_professor(coordenador, por=coordenador)
    coordenador.refresh_from_db()
    assert coordenador.papel == Usuario.COORDENADOR


@pytest.mark.django_db
def test_professor_nao_promove(professor, outro_professor):
    with pytest.raises(PermissionDenied):
        services.promover_a_coordenador(outro_professor, por=professor)


@pytest.mark.django_db
def test_professor_nao_rebaixa(professor, coordenador):
    with pytest.raises(PermissionDenied):
        services.rebaixar_a_professor(coordenador, por=professor)


@pytest.mark.django_db
def test_aluno_nao_vira_coordenador(aluno, coordenador):
    """Promoção é de professor para coordenador.

    A mensagem é afirmada, e não só o tipo: `Usuario.clean` recusaria um aluno
    virando coordenador de qualquer forma, por falta de SIAPE. Sem afirmar o
    texto, apagar a guarda do serviço deixaria o teste verde pela razão errada.
    """
    with pytest.raises(ValidationError) as erro:
        services.promover_a_coordenador(aluno, por=coordenador)
    assert "Só professor vira coordenador." in " ".join(erro.value.messages)


@pytest.mark.django_db
def test_promover_quem_ja_e_coordenador_e_recusado(outro_coordenador, coordenador):
    with pytest.raises(ValidationError):
        services.promover_a_coordenador(outro_coordenador, por=coordenador)


@pytest.mark.django_db
def test_rebaixar_quem_nao_e_coordenador_e_recusado(professor, coordenador):
    with pytest.raises(ValidationError) as erro:
        services.rebaixar_a_professor(professor, por=coordenador)
    assert "não é coordenadora" in " ".join(erro.value.messages)


@pytest.mark.django_db
def test_promocao_da_acesso_ao_admin(professor, coordenador):
    """O nível Admin acompanha o papel. Passa por services, e não por edição do
    campo no Django Admin -- lá não haveria como recusar o auto-rebaixamento."""
    assert professor.is_staff is False
    services.promover_a_coordenador(professor, por=coordenador)
    professor.refresh_from_db()
    assert professor.is_staff is True


@pytest.mark.django_db
def test_rebaixamento_tira_o_acesso_ao_admin(outro_coordenador, coordenador):
    services.rebaixar_a_professor(outro_coordenador, por=coordenador)
    outro_coordenador.refresh_from_db()
    assert outro_coordenador.is_staff is False


@pytest.mark.django_db
def test_tela_de_pessoas_e_so_da_coordenacao(client, professor):
    client.force_login(professor)
    assert client.get(reverse("pessoas")).status_code == 403


@pytest.mark.django_db
def test_aluno_nao_ve_a_tela_de_pessoas(client, aluno):
    client.force_login(aluno)
    assert client.get(reverse("pessoas")).status_code == 403


@pytest.mark.django_db
def test_coordenador_ve_a_tela_de_pessoas(client, coordenador, professor):
    client.force_login(coordenador)
    conteudo = client.get(reverse("pessoas")).content.decode()
    assert professor.nome_completo in conteudo


@pytest.mark.django_db
def test_a_tela_nao_lista_alunos(client, coordenador, aluno):
    """A tela é de professores e coordenação: aluno não aparece, senão o botão de
    promover apareceria para quem não pode ser promovido."""
    client.force_login(coordenador)
    assert aluno.nome_completo not in client.get(reverse("pessoas")).content.decode()


@pytest.mark.django_db
def test_promover_pela_tela(client, coordenador, professor):
    client.force_login(coordenador)
    client.post(reverse("pessoas"), {"usuario": professor.pk, "acao": "PROMOVER"}, follow=True)
    professor.refresh_from_db()
    assert professor.papel == Usuario.COORDENADOR


@pytest.mark.django_db
def test_rebaixar_pela_tela(client, coordenador, outro_coordenador):
    client.force_login(coordenador)
    client.post(
        reverse("pessoas"), {"usuario": outro_coordenador.pk, "acao": "REBAIXAR"}, follow=True
    )
    outro_coordenador.refresh_from_db()
    assert outro_coordenador.papel == Usuario.PROFESSOR


@pytest.mark.django_db
def test_promover_professor_sem_nome_produz_mensagem_com_email(client, coordenador):
    """`f"{alvo.nome_completo} agora é coordenador."` com nome vazio produz
    " agora é coordenador.", sem sujeito. A tela de Pessoas já lista esta conta
    pelo e-mail (`pessoa.nome_completo|default:pessoa.email`); a mensagem de
    sucesso do POST tinha ficado para trás."""
    sem_nome = Usuario.objects.create_user(
        email="semnome@ufsm.br", nome_completo="", papel=Usuario.PROFESSOR, password=None
    )
    client.force_login(coordenador)
    resposta = client.post(
        reverse("pessoas"), {"usuario": sem_nome.pk, "acao": "PROMOVER"}, follow=True
    )
    assert "semnome@ufsm.br agora é coordenador." in resposta.content.decode()


@pytest.mark.django_db
def test_acao_desconhecida_nao_muda_nada(client, coordenador, professor):
    """Sem ramo pega-tudo: um valor inesperado não pode cair na ação destrutiva.
    O mesmo defeito já apareceu duas vezes neste projeto."""
    client.force_login(coordenador)
    resposta = client.post(
        reverse("pessoas"), {"usuario": professor.pk, "acao": "QUALQUER_COISA"}, follow=True
    )
    professor.refresh_from_db()
    assert professor.papel == Usuario.PROFESSOR
    assert "não reconhecida" in resposta.content.decode()


@pytest.mark.django_db
def test_metodo_errado_na_tela_de_pessoas(client, coordenador):
    client.force_login(coordenador)
    assert client.delete(reverse("pessoas")).status_code == 405


@pytest.mark.django_db
def test_os_botoes_dizem_tornar(client, coordenador, professor):
    """"Promover" e "rebaixar" carregavam hierarquia que o sistema nao tem: os
    dois papeis produzem curso, e um deles tambem cuida do catalogo. "Tornar" diz
    o que acontece sem sugerir subida ou queda.

    Os VALORES enviados (`PROMOVER`, `REBAIXAR`) nao mudam: valor gravado ou
    trafegado nao se altera por passada de texto (CLAUDE.md), e trocar os dois
    exigiria mexer no desvio da view sem ganho nenhum.
    """
    # Um SEGUNDO coordenador para o botao de rebaixar aparecer: ninguem rebaixa a
    # si mesmo, entao com um so a tela nunca mostra aquele botao.
    outro = Usuario.objects.create_user(
        email="coord2@ufsm.br", nome_completo="Outro Coordenador",
        cpf="100.000.077-06", siape="9990001", papel=Usuario.COORDENADOR,
    )
    client.force_login(coordenador)
    html = client.get(reverse("pessoas")).content.decode()
    assert outro.nome_completo in html
    assert "Tornar Coordenador" in html
    assert "Tornar Professor" in html
    assert "Promover" not in html
    assert "Rebaixar" not in html
    assert 'value="PROMOVER"' in html
