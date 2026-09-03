"""A coordenacao cadastra professor, e ele completa o proprio cadastro.

Ate agora nao havia caminho na interface: professor nascia so pelo
`manage.py criar_coordenador` ou pelo Django Admin. E o modelo nao deixava criar
um so com e-mail, porque exigia CPF e SIAPE ja no cadastro.

A decisao do produto: a coordenacao digita SO o e-mail, e a pessoa informa nome,
CPF e SIAPE no primeiro acesso - o mesmo arranjo que o aluno ja tinha, onde quem
exige os campos e a tela, e nao o modelo.

Aluno continua nascendo pela equipe, ao ser alocado num curso: conta de aluno sem
curso ficaria com convite e sem trabalho.
"""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.contas import services
from apps.contas.models import ConviteAluno, Usuario
from apps.notificacoes.models import Notificacao


# --- o cadastro ---------------------------------------------------------------


@pytest.mark.django_db
def test_a_coordenacao_cadastra_professor_so_com_o_email(coordenador):
    pessoa = services.criar_professor("novo.prof@ufsm.br", por=coordenador)

    assert pessoa.papel == Usuario.PROFESSOR
    assert pessoa.nome_completo == ""
    assert pessoa.cpf is None
    assert pessoa.siape is None
    assert not pessoa.perfil_completo
    # Sem senha utilizavel: so o convite abre a conta.
    assert not pessoa.has_usable_password()
    assert pessoa.convites.filter(usado_em__isnull=True).count() == 1
    # O e-mail sai pela fila, como todo o resto: SMTP fora do ar nao pode
    # derrubar o cadastro.
    assert Notificacao.objects.filter(destinatario="novo.prof@ufsm.br").count() == 1


@pytest.mark.django_db
def test_so_a_coordenacao_cadastra(professor, aluno):
    for quem in (professor, aluno):
        with pytest.raises(PermissionDenied):
            services.criar_professor("outro@ufsm.br", por=quem)
    assert not Usuario.objects.filter(email="outro@ufsm.br").exists()


@pytest.mark.django_db
def test_email_ja_cadastrado_e_recusado(coordenador, professor):
    with pytest.raises(ValidationError, match="conta"):
        services.criar_professor(professor.email, por=coordenador)


@pytest.mark.django_db
def test_email_vazio_e_recusado(coordenador):
    with pytest.raises(ValidationError, match="e-mail"):
        services.criar_professor("   ", por=coordenador)


# --- o primeiro acesso dele ---------------------------------------------------


@pytest.fixture
def convite_de_professor(coordenador):
    pessoa = services.criar_professor("novo.prof@ufsm.br", por=coordenador)
    return pessoa.convites.get()


@pytest.mark.django_db
def test_a_tela_pede_nome_cpf_e_siape(client, convite_de_professor):
    """E nao matricula, que e do aluno."""
    html = client.get(
        reverse("primeiro_acesso", args=[convite_de_professor.token])
    ).content.decode()
    for campo in ("nome_completo", "cpf", "siape"):
        assert f'name="{campo}"' in html, campo
    assert 'name="matricula"' not in html


@pytest.mark.django_db
def test_a_tela_do_aluno_continua_pedindo_matricula(client, aluno, professor):
    from apps.contas.services import convidar

    convite = convidar(aluno, por=professor, base_url="http://x")
    html = client.get(reverse("primeiro_acesso", args=[convite.token])).content.decode()
    assert 'name="matricula"' in html
    assert 'name="siape"' not in html


@pytest.mark.django_db
def test_o_professor_completa_e_entra(client, convite_de_professor):
    resposta = client.post(
        reverse("primeiro_acesso", args=[convite_de_professor.token]),
        {
            "nome_completo": "Novo Professor",
            "cpf": "100.000.077-06",
            "siape": "9990002",
            "telefone": "(55) 99999-0000",
            "senha": "senha-de-teste-123",
            "confirmacao": "senha-de-teste-123",
        },
        follow=True,
    )
    assert resposta.status_code == 200
    pessoa = Usuario.objects.get(email="novo.prof@ufsm.br")
    assert pessoa.nome_completo == "Novo Professor"
    assert pessoa.perfil_completo
    assert pessoa.check_password("senha-de-teste-123")
    assert ConviteAluno.objects.get(pk=convite_de_professor.pk).usado_em is not None


@pytest.mark.django_db
def test_enquanto_nao_completa_ele_fica_preso_na_propria_tela(
    client, convite_de_professor
):
    """O middleware ja fazia isso com o aluno; vale igual aqui porque
    `perfil_completo` de professor ja era `cpf and siape`."""
    pessoa = convite_de_professor.usuario
    client.force_login(pessoa)
    resposta = client.get(reverse("painel"))
    assert resposta.status_code == 302
    assert str(convite_de_professor.token) in resposta.url


# --- a tela de pessoas --------------------------------------------------------


@pytest.mark.django_db
def test_a_tela_de_pessoas_cadastra(client, coordenador):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("pessoas"), {"acao": "CRIAR_PROFESSOR", "email": "prof.novo@ufsm.br"},
        follow=True,
    )
    assert resposta.status_code == 200
    assert Usuario.objects.filter(email="prof.novo@ufsm.br", papel=Usuario.PROFESSOR).exists()


@pytest.mark.django_db
def test_a_tela_nao_cadastra_aluno(client, coordenador):
    """Aluno continua nascendo pela equipe: conta de aluno sem curso ficaria com
    convite e sem trabalho, e a tela de pessoas nem lista alunos."""
    client.force_login(coordenador)
    resposta = client.post(
        reverse("pessoas"), {"acao": "CRIAR_ALUNO", "email": "aluno.solto@acad.ufsm.br"},
        follow=True,
    )
    assert resposta.status_code == 200
    assert not Usuario.objects.filter(email="aluno.solto@acad.ufsm.br").exists()


@pytest.mark.django_db
def test_a_explicacao_usa_o_mesmo_termo_do_resto_da_interface(client, coordenador):
    """A interface inteira diz "aluno", inclusive o rótulo de `Usuario.PAPEIS`
    que o painel e o perfil imprimem. Esta frase chegou a dizer "Estudante" por
    uma passada de texto que padronizou no termo errado."""
    client.force_login(coordenador)
    html = client.get(reverse("pessoas")).content.decode()
    assert "Aluno não se cadastra por aqui" in html
