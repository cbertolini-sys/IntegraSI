"""O comando que semeia o ambiente de teste com pessoas e cursos publicados.

Existe porque o servidor de producao vai ser usado para testar com gente, e
montar isso a mao significaria digitar Python solto em producao - exatamente o
que a regra de deploy do CLAUDE.md manda evitar. Aqui a semeadura e revisavel,
testada e repetivel.

O que ele NAO faz, de proposito: convite por e-mail. As contas nascem com perfil
completo e senha conhecida, porque os enderecos da lista sao de um dominio que
nao existe. Mandar convite para la geraria devolucao e sujaria a reputacao do
remetente. O fluxo de convite se testa a parte, com um endereco real.
"""

import io

import pytest
from django.contrib.auth import authenticate
from django.core.management import call_command

from apps.contas.models import Usuario
from apps.contas.validators import valida_cpf
from apps.cursos.choices import StatusCurso, StatusEntregavel
from apps.cursos.models import Curso, MembroEquipe
from apps.notificacoes.models import Notificacao

LISTA = """﻿
1. ESTRUTURA DOS USUÁRIOS de TESTE A SEREM CRIADOS:

- 1 Coordenador:
  * Nome: Nick Fury | Email: nick@escola.com

- 2 Professores:
  * Nome: Charles Xavier | Email: charles@escola.com
  * Nome: Bruce Banner | Email: bruce@escola.com

- 5 Alunos:
  * Nome: Peter Parker | Email: peter@escola.com
  * Nome: Gwen Stacy | Email: gwen@escola.com
  * Nome: Miles Morales | Email: miles@escola.com
  * Nome: Kamala Khan | Email: kamala@escola.com
  * Nome: Riri Williams | Email: riri@escola.com
"""


@pytest.fixture
def lista(tmp_path):
    caminho = tmp_path / "usersTemp.txt"
    caminho.write_text(LISTA, encoding="utf-8")
    return str(caminho)


@pytest.fixture
def semeado(lista, db):
    call_command("semear_demonstracao", arquivo=lista, senha="si123456")


def semear(lista, **extra):
    """Roda o comando capturando a saida, para os testes que afirmam sobre o aviso."""
    saida = io.StringIO()
    call_command("semear_demonstracao", arquivo=lista, senha="si123456", stdout=saida, **extra)
    return saida.getvalue()


# --- as pessoas ---------------------------------------------------------------


@pytest.mark.django_db
def test_cria_as_oito_pessoas_com_os_papeis_do_arquivo(semeado):
    assert Usuario.objects.count() == 8
    assert Usuario.objects.get(email="nick@escola.com").papel == Usuario.COORDENADOR
    assert Usuario.objects.get(email="charles@escola.com").papel == Usuario.PROFESSOR
    assert Usuario.objects.get(email="bruce@escola.com").papel == Usuario.PROFESSOR
    assert Usuario.objects.filter(papel=Usuario.ALUNO).count() == 5


@pytest.mark.django_db
def test_todo_mundo_nasce_com_o_perfil_completo(semeado):
    """Sem isto o `PerfilCompletoMiddleware` prende a pessoa na tela de cadastro
    e ela nao navega. Como nao ha convite (o dominio nao existe), ela ficaria
    presa sem ter como se soltar."""
    for pessoa in Usuario.objects.all():
        assert pessoa.perfil_completo, f"{pessoa.email} entrou com perfil incompleto"


@pytest.mark.django_db
def test_os_cpfs_gerados_sao_validos(semeado):
    """CPF de mentira ainda precisa passar pelos digitos verificadores: o modelo
    valida em `full_clean()`, e um CPF invalido faria a conta nem gravar."""
    for pessoa in Usuario.objects.all():
        valida_cpf(pessoa.cpf)


@pytest.mark.django_db
def test_a_senha_informada_abre_a_conta(semeado):
    """A prova e o `authenticate`, e nao `check_password` no objeto: e o caminho
    que a tela de login usa, e ele passa pelo backend e pelo `is_active`."""
    for email in ["nick@escola.com", "charles@escola.com", "peter@escola.com"]:
        assert authenticate(username=email, password="si123456") is not None, email


# --- os cursos ----------------------------------------------------------------


@pytest.mark.django_db
def test_publica_dois_cursos(semeado):
    publicados = Curso.objects.filter(status=StatusCurso.PUBLICADO)
    assert publicados.count() == 2


@pytest.mark.django_db
def test_cada_curso_tem_um_professor_diferente_e_alunos_na_equipe(semeado):
    cursos = list(Curso.objects.filter(status=StatusCurso.PUBLICADO).order_by("pk"))
    responsaveis = {c.professor_responsavel.email for c in cursos}
    assert responsaveis == {"charles@escola.com", "bruce@escola.com"}
    for curso in cursos:
        alunos = MembroEquipe.objects.filter(curso=curso, pessoa__papel=Usuario.ALUNO)
        assert alunos.count() >= 2, f"{curso.titulo} ficou sem equipe"


@pytest.mark.django_db
def test_os_seis_entregaveis_de_cada_curso_ficam_aprovados(semeado):
    """Publicar exige os seis aprovados. Se algum ficasse para tras o curso nem
    chegaria a PUBLICADO, mas a afirmacao aqui e sobre o caminho, e nao sobre o
    efeito: um curso publicado com entregavel pendente seria estado impossivel."""
    for curso in Curso.objects.filter(status=StatusCurso.PUBLICADO):
        pendentes = curso.entregaveis.exclude(status=StatusEntregavel.APROVADO)
        assert not pendentes.exists(), f"{curso.titulo}: {list(pendentes)}"


@pytest.mark.django_db
def test_o_plano_de_ensino_sai_escrito(semeado):
    """Curso publicado com Plano de Ensino em branco nao serve de demonstracao:
    a pagina publica abriria vazia."""
    from apps.cursos.choices import TipoEntregavel

    for curso in Curso.objects.filter(status=StatusCurso.PUBLICADO):
        plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
        vazias = [s.titulo for s in plano.secoes.all() if not s.conteudo.strip()]
        assert not vazias, f"{curso.titulo}: secoes em branco {vazias}"


# --- higiene ------------------------------------------------------------------


@pytest.mark.django_db
def test_nao_deixa_email_na_fila_para_o_dominio_que_nao_existe(semeado):
    """`adicionar_membro` e `submeter_ao_coordenador` enfileiram aviso. Para
    `@escola.com` isso viraria devolucao a cada 5 minutos, contra o Gmail que
    assina o envio. O comando limpa o que ele mesmo gerou."""
    pendentes = Notificacao.objects.filter(
        enviado_em__isnull=True, destinatario__endswith="@escola.com"
    )
    assert not pendentes.exists(), list(pendentes.values_list("destinatario", flat=True))


@pytest.mark.django_db
def test_rodar_duas_vezes_nao_duplica_nada(lista, db):
    """Semeadura tem que ser repetivel: quem rodar de novo por engano, ou para
    completar uma execucao interrompida, nao pode acabar com contas em dobro."""
    call_command("semear_demonstracao", arquivo=lista, senha="si123456")
    call_command("semear_demonstracao", arquivo=lista, senha="si123456")

    assert Usuario.objects.count() == 8
    assert Curso.objects.count() == 2


# --- o coordenador semeado ----------------------------------------------------
# Achados rodando o rebaixamento em producao, depois da auditoria de 04/09.


@pytest.mark.django_db
def test_o_coordenador_semeado_entra_com_acesso_ao_admin(semeado):
    """`promover_a_coordenador` liga `is_staff` junto com o papel, e por bom
    motivo: o Admin e a porta pela qual a coordenacao destrava conta presa, e e a
    unica rota que o `PerfilCompletoMiddleware` deixa passar de proposito.

    O comando gravava so o papel. O coordenador semeado tinha poder de coordenacao
    dentro do sistema e nenhum acesso ao Admin: dois estados que deveriam andar
    juntos, discordando em silencio. Foi visto no servidor, nao aqui.
    """
    coordenador = Usuario.objects.get(email="nick@escola.com")

    assert coordenador.papel == Usuario.COORDENADOR
    assert coordenador.is_staff, "papel de coordenador sem acesso ao Admin"


@pytest.mark.django_db
def test_o_comando_avisa_o_preco_de_criar_coordenador(lista, db):
    """Coordenador ficticio nao afeta so quem testa: TODO coordenador ativo recebe
    aviso de solicitacao da comunidade e de curso submetido. Com endereco que nao
    existe, cada uma dessas acoes vira devolucao contra a conta que assina os
    envios. Aconteceu, e custou um rebaixamento a mao em producao.

    O comando nao pode recusar (a lista e que manda, e ele nao sabe quais
    enderecos existem), mas pode dizer o preco a quem roda.
    """
    saida = semear(lista)

    assert "coordenador" in saida.lower()
    assert "devolu" in saida.lower(), saida
