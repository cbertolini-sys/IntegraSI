"""Alocar um aluno que ja tem conta, escolhendo-o de uma lista.

`alocar_aluno` recusa e-mail ja cadastrado de proposito: um endereco digitado
errado poria a pessoa errada numa equipe, e o professor nao teria como perceber.
A mensagem mandava "peça à coordenação para vincular a conta existente" - e nao
havia por onde. Escolher de uma lista fecha isso pelo outro lado: nao ha o que
digitar errado.

Um aluno trabalha em mais de um curso ao longo do curso de graduacao, entao este
e o caminho normal a partir do segundo curso, nao a excecao.
"""

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.contas.models import Usuario
from apps.cursos import services


@pytest.fixture
def curso(dados_curso):
    return services.criar_curso(**dados_curso)


# --- o servico ----------------------------------------------------------------


@pytest.mark.django_db
def test_aloca_sem_criar_conta_e_sem_convite(curso, professor, aluno):
    """A conta ja existe e ja foi ativada uma vez: mandar primeiro acesso de novo
    seria convite que nao serve para nada, como em `alocar_professor`."""
    contas_antes = Usuario.objects.count()
    mail.outbox.clear()

    membro = services.alocar_aluno_existente(curso, aluno, por=professor)

    assert membro.pessoa == aluno
    assert curso.tem_membro(aluno)
    assert Usuario.objects.count() == contas_antes
    assert mail.outbox == []
    assert aluno.convites.count() == 0


@pytest.mark.django_db
def test_o_mesmo_aluno_entra_em_dois_cursos(dados_curso, professor, aluno):
    """O ponto do pedido: a equipe de um curso nao exclui a de outro."""
    primeiro = services.criar_curso(**dados_curso)
    segundo = services.criar_curso(**dados_curso)
    services.alocar_aluno_existente(primeiro, aluno, por=professor)
    services.alocar_aluno_existente(segundo, aluno, por=professor)
    assert primeiro.tem_membro(aluno)
    assert segundo.tem_membro(aluno)


@pytest.mark.django_db
def test_recusa_quem_nao_e_aluno(curso, professor, outro_professor):
    """O pk vem do formulario: um professor escolhido por aqui entraria pela porta
    errada, sem passar por `alocar_professor`. Mesma guarda que aquele tem, no
    sentido inverso."""
    with pytest.raises(ValidationError, match="estudante"):
        services.alocar_aluno_existente(curso, outro_professor, por=professor)
    assert not curso.tem_membro(outro_professor)


@pytest.mark.django_db
def test_recusa_selecao_vazia(curso, professor):
    """O select pode chegar vazio; sem esta guarda o None seguiria para
    `adicionar_membro` e viraria 500 em vez de mensagem."""
    with pytest.raises(ValidationError, match="estudante"):
        services.alocar_aluno_existente(curso, None, por=professor)


@pytest.mark.django_db
def test_so_quem_gere_a_equipe_aloca(curso, aluno, outro_aluno):
    from django.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        services.alocar_aluno_existente(curso, outro_aluno, por=aluno)


# --- a tela -------------------------------------------------------------------


@pytest.mark.django_db
def test_a_tela_oferece_os_alunos_cadastrados(client, curso, professor, aluno):
    client.force_login(professor)
    resposta = client.get(reverse("equipe", args=[curso.pk]))
    assert aluno in resposta.context["form_aluno_existente"].fields["aluno"].queryset
    assert 'name="aluno"' in resposta.content.decode()


@pytest.mark.django_db
def test_quem_ja_esta_na_equipe_sai_da_lista(client, curso, professor, aluno):
    """Oferecer quem ja esta dentro so daria erro de unicidade - o select de
    professores ja tinha aprendido isso."""
    services.adicionar_membro(curso, aluno, por=professor)
    client.force_login(professor)
    resposta = client.get(reverse("equipe", args=[curso.pk]))
    assert aluno not in resposta.context["form_aluno_existente"].fields["aluno"].queryset


@pytest.mark.django_db
def test_a_lista_nao_traz_professores(client, curso, professor, outro_professor, aluno):
    """Sao duas listas na tela, cada uma com o seu papel. Misturadas, a escolha
    entra pela porta errada."""
    client.force_login(professor)
    resposta = client.get(reverse("equipe", args=[curso.pk]))
    alunos = resposta.context["form_aluno_existente"].fields["aluno"].queryset
    assert aluno in alunos
    assert outro_professor not in alunos


@pytest.mark.django_db
def test_alocar_pela_tela(client, curso, professor, aluno):
    client.force_login(professor)
    resposta = client.post(
        reverse("equipe", args=[curso.pk]),
        {"acao": "aluno_existente", "aluno": aluno.pk},
        follow=True,
    )
    assert resposta.status_code == 200
    assert curso.tem_membro(aluno)
    assert aluno.nome_completo in resposta.content.decode()


@pytest.mark.django_db
def test_acao_desconhecida_nao_cria_conta(client, curso, professor):
    """O desvio era `if professor: ... else: aluno`, um pega-tudo que criava conta
    e disparava e-mail para qualquer `acao` inesperada. Com tres formularios na
    tela, igualdade explicita nos tres ramos - o mesmo padrao que `pessoas` e
    `decidir_curso` ja seguem."""
    contas_antes = Usuario.objects.count()
    client.force_login(professor)
    resposta = client.post(
        reverse("equipe", args=[curso.pk]),
        {"acao": "qualquer-coisa", "nome": "Joana Silva", "email": "joana@acad.ufsm.br"},
        follow=True,
    )
    assert Usuario.objects.count() == contas_antes
    assert "não reconhecida" in resposta.content.decode().lower()


@pytest.mark.django_db
def test_cada_formulario_manda_a_propria_acao(
    client, curso, professor, outro_professor, aluno
):
    """Prende o par formulario/acao, e nao cada um de um lado.

    Os testes acima mandam `acao` a mao, entao trocar o campo escondido no
    template nao quebrava nenhum: escolher um estudante do select cairia no ramo
    do aluno NOVO e a tela responderia "Informe o nome", com a suite verde. Achado
    na campanha de deleção.

    `outro_professor` entra na lista de fixtures porque o select de professor so
    e desenhado quando ha alguem para escolher: sem ninguem disponivel,
    `_campo.html` mostra "Nenhum professor disponível." no lugar do campo, e o
    teste procuraria um `name="professor"` que a tela nao tem motivo para ter.
    """
    import re

    client.force_login(professor)
    html = client.get(reverse("equipe", args=[curso.pk])).content.decode()
    formularios = re.findall(r"<form method=\"post\">.*?</form>", html, re.S)
    acao_de_cada = {
        re.search(r'name="acao" value="([a-z_]+)"', f).group(1): f
        for f in formularios
        if re.search(r'name="acao"', f)
    }
    assert set(acao_de_cada) == {"aluno_existente", "aluno", "professor"}
    # O select de estudante mora no formulario de estudante ja cadastrado.
    assert 'name="aluno"' in acao_de_cada["aluno_existente"]
    # O de nome e e-mail, no do estudante novo.
    assert 'name="email"' in acao_de_cada["aluno"]
    # E o de professor, no seu.
    assert 'name="professor"' in acao_de_cada["professor"]
