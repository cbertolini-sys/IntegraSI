"""A tela "Meu perfil": ver e corrigir os próprios dados.

Até aqui os dados pessoais entravam uma vez, na tela do convite, e depois só a
coordenação os alcançava, pelo Django Admin. Quem errasse o telefone ou casasse e
mudasse de nome não tinha para onde ir.

O CPF é o caso especial. A regra do projeto (CLAUDE.md, Dados pessoais) é que ele
não aparece fora do Admin, e mascarado até lá: esta tela mostra a máscara, nunca
o número, e o campo de correção nasce SEMPRE vazio. Em branco, mantém o que está
gravado. É o que permite corrigir sem imprimir o documento numa página, num
cache de navegador ou num log de acesso.
"""

import pytest
from django.urls import reverse

from apps.contas.forms import PerfilForm
from apps.contas.models import Usuario


def _abre(client, pessoa):
    client.force_login(pessoa)
    return client.get(reverse("perfil")).content.decode()


# --- quem entra ---------------------------------------------------------------


@pytest.mark.django_db
def test_visitante_nao_alcanca_o_perfil(client):
    resposta = client.get(reverse("perfil"))
    assert resposta.status_code == 302
    assert reverse("login") in resposta.url


@pytest.mark.django_db
def test_a_tela_mostra_quem_a_pessoa_e(client, professor):
    html = _abre(client, professor)
    assert professor.nome_completo in html
    assert professor.email in html
    assert "Professor" in html


# --- o CPF --------------------------------------------------------------------


@pytest.mark.django_db
def test_o_cpf_aparece_mascarado_e_nunca_inteiro(client, professor):
    html = _abre(client, professor)
    assert "***.***.789-09" in html
    # Nem com pontuação nem só os dígitos: o valor cru não pode chegar ao HTML,
    # em forma nenhuma.
    assert "123.456.789-09" not in html
    assert "12345678909" not in html


@pytest.mark.django_db
def test_o_campo_de_cpf_nasce_vazio(client, professor):
    """Interpolar o CPF gravado no `value` do campo o imprimiria na página e no
    cache do navegador, que é exatamente o que a máscara evita."""
    html = _abre(client, professor)
    assert 'name="cpf"' in html
    assert 'value="123.456.789-09"' not in html
    assert 'value="12345678909"' not in html


@pytest.mark.django_db
def test_cpf_em_branco_mantem_o_que_estava(client, professor):
    client.force_login(professor)
    client.post(
        reverse("perfil"),
        {"acao": "DADOS", "nome_completo": "Bruno Barros", "siape": "1234567",
         "telefone": "(55) 98888-0000", "cpf": ""},
    )
    professor.refresh_from_db()
    assert professor.cpf == "12345678909"


@pytest.mark.django_db
def test_cpf_novo_e_valido_substitui(client, professor):
    client.force_login(professor)
    client.post(
        reverse("perfil"),
        {"acao": "DADOS", "nome_completo": "Bruno Barros", "siape": "1234567",
         "telefone": "(55) 98888-0000", "cpf": "111.444.777-35"},
    )
    professor.refresh_from_db()
    assert professor.cpf == "11144477735"


@pytest.mark.django_db
def test_cpf_invalido_e_recusado_no_proprio_campo(client, professor):
    """No campo, e não como erro geral.

    `Usuario.clean()` também recusa o CPF inválido, então "a gravação não
    aconteceu" não distingue as duas guardas: apagar a do formulário deixaria o
    modelo recusando igual e este teste verde. O que só a guarda do formulário
    produz é o erro pendurado no campo `cpf`, onde a pessoa o vê ao lado do que
    digitou, em vez de uma frase solta no topo da tela.
    """
    client.force_login(professor)
    resposta = client.post(
        reverse("perfil"),
        {"acao": "DADOS", "nome_completo": "Bruno Barros", "siape": "1234567",
         "telefone": "(55) 98888-0000", "cpf": "111.111.111-11"},
    )
    assert resposta.status_code == 200
    assert "cpf" in resposta.context["form"].errors
    professor.refresh_from_db()
    assert professor.cpf == "12345678909"


# --- os campos de cada papel --------------------------------------------------


@pytest.mark.django_db
def test_o_professor_ve_siape_e_nao_matricula(client, professor):
    html = _abre(client, professor)
    assert 'name="siape"' in html
    assert 'name="matricula"' not in html


@pytest.mark.django_db
def test_o_aluno_ve_matricula_e_nao_siape(client, aluno):
    html = _abre(client, aluno)
    assert 'name="matricula"' in html
    assert 'name="siape"' not in html


# --- o que a pessoa pode mudar ------------------------------------------------


@pytest.mark.django_db
def test_a_pessoa_corrige_nome_e_telefone(client, aluno):
    client.force_login(aluno)
    resposta = client.post(
        reverse("perfil"),
        {"acao": "DADOS", "nome_completo": "Ana Alves Silva", "matricula": "201910101",
         "telefone": "(55) 97777-1111", "cpf": ""},
        follow=True,
    )
    assert resposta.status_code == 200
    aluno.refresh_from_db()
    assert aluno.nome_completo == "Ana Alves Silva"
    assert aluno.telefone == "(55) 97777-1111"


@pytest.mark.django_db
def test_a_pessoa_nao_muda_o_proprio_papel(client, aluno):
    """O papel passa por `contas.services`, nunca por edição de campo: senão
    qualquer pessoa logada viraria coordenador por um campo escondido."""
    client.force_login(aluno)
    client.post(
        reverse("perfil"),
        {"acao": "DADOS", "nome_completo": "Ana Alves", "matricula": "201910101",
         "telefone": "(55) 97777-1111", "cpf": "",
         "papel": Usuario.COORDENADOR, "is_superuser": "on", "is_staff": "on"},
    )
    aluno.refresh_from_db()
    assert aluno.papel == Usuario.ALUNO
    assert aluno.is_superuser is False
    assert aluno.is_staff is False


def test_a_cerca_do_formulario_nao_alcanca_papel_nem_privilegio():
    """`Meta.fields` isolado do corte por papel.

    O `__init__` também poda campos, e as duas guardas escondem uma à outra num
    teste de POST: apagar qualquer uma delas deixa a outra barrando o `papel`, e
    o teste segue verde. `base_fields` é montado a partir da `Meta`, na classe,
    antes de `__init__` rodar - é onde esta guarda responde sozinha.
    """
    proibidos = {"papel", "is_superuser", "is_staff", "email", "password",
                 "user_permissions", "groups", "is_active"}
    assert proibidos.isdisjoint(PerfilForm.base_fields)


@pytest.mark.django_db
def test_o_corte_por_papel_nao_deixa_campo_sobrando(aluno, professor):
    """A outra metade da cerca, também sozinha: depois do `__init__`, restam
    exatamente os campos daquele papel."""
    assert set(PerfilForm(instance=aluno).fields) == {
        "nome_completo", "cpf", "matricula", "telefone"
    }
    assert set(PerfilForm(instance=professor).fields) == {
        "nome_completo", "cpf", "siape", "telefone"
    }


@pytest.mark.django_db
def test_a_pessoa_nao_muda_o_proprio_email(client, aluno):
    """O e-mail é a credencial de acesso. Trocá-lo sozinho é trocar de conta."""
    client.force_login(aluno)
    client.post(
        reverse("perfil"),
        {"acao": "DADOS", "nome_completo": "Ana Alves", "matricula": "201910101",
         "telefone": "(55) 97777-1111", "cpf": "", "email": "outra@ufsm.br"},
    )
    aluno.refresh_from_db()
    assert aluno.email == "aluno@ufsm.br"


@pytest.mark.django_db
def test_ninguem_edita_outra_pessoa(client, aluno, professor):
    """A instância editada vem de `request.user`, e não do POST.

    A carga é a que o formulário DO PROFESSOR aceitaria inteira, com o SIAPE dele
    junto: uma carga inválida faria o teste passar por o formulário ter sido
    recusado, e não por a instância estar presa ao usuário da sessão. É a
    diferença entre provar a regra e provar um acidente.
    """
    client.force_login(aluno)
    client.post(
        reverse("perfil"),
        {"acao": "DADOS", "nome_completo": "Invadido", "siape": "1234567",
         "matricula": "201910101", "telefone": "(55) 97777-1111", "cpf": "",
         "id": professor.pk, "pk": professor.pk, "usuario": professor.pk},
    )
    professor.refresh_from_db()
    assert professor.nome_completo == "Bruno Barros"
    aluno.refresh_from_db()
    assert aluno.nome_completo == "Invadido"


# --- a senha ------------------------------------------------------------------


@pytest.mark.django_db
def test_a_pessoa_troca_a_propria_senha(client, professor):
    client.force_login(professor)
    resposta = client.post(
        reverse("perfil"),
        {"acao": "SENHA", "old_password": "senha-de-teste-123",
         "new_password1": "outra-senha-boa-456", "new_password2": "outra-senha-boa-456"},
        follow=True,
    )
    assert resposta.status_code == 200
    professor.refresh_from_db()
    assert professor.check_password("outra-senha-boa-456")


@pytest.mark.django_db
def test_trocar_a_senha_nao_derruba_a_sessao(client, professor):
    """Sem `update_session_auth_hash`, o Django invalida a sessão junto com o hash
    antigo e a pessoa é deslogada no instante em que acerta a troca."""
    client.force_login(professor)
    client.post(
        reverse("perfil"),
        {"acao": "SENHA", "old_password": "senha-de-teste-123",
         "new_password1": "outra-senha-boa-456", "new_password2": "outra-senha-boa-456"},
    )
    assert client.get(reverse("perfil")).status_code == 200


@pytest.mark.django_db
def test_senha_atual_errada_nao_troca(client, professor):
    client.force_login(professor)
    client.post(
        reverse("perfil"),
        {"acao": "SENHA", "old_password": "chute-errado",
         "new_password1": "outra-senha-boa-456", "new_password2": "outra-senha-boa-456"},
    )
    professor.refresh_from_db()
    assert professor.check_password("senha-de-teste-123")


# --- a porta no cabeçalho -----------------------------------------------------


@pytest.mark.django_db
def test_o_cabecalho_leva_ao_perfil(client, professor):
    client.force_login(professor)
    html = client.get(reverse("painel")).content.decode()
    assert reverse("perfil") in html


@pytest.mark.django_db
def test_o_visitante_nao_ve_a_porta(client):
    html = client.get(reverse("catalogo")).content.decode()
    assert reverse("perfil") not in html


@pytest.mark.django_db
def test_a_tela_diz_quem_troca_o_e_mail(client, professor):
    """O e-mail é a credencial e não se edita aqui. Sem dizer isso, a pessoa
    procura o campo, não acha, e conclui que a tela está quebrada."""
    html = _abre(client, professor)
    assert "Só a coordenação troca." in html
