"""Nova versao pela tela, e o que cada pessoa enxerga dela (Plano 4, Task 6).

As regras que este arquivo prende, na ordem em que aparecem:

 1. Existe a rota `nova_versao` em `cursos/<pk>/nova-versao/`, e ela exige login:
    visitante anonimo vai para o formulario de login, nao para um 500 nem para um
    405.
 2. A guarda de quem pode abrir versao vale no GET, e nao so no POST. O GET nao
    chama servico nenhum - sem guarda na view, qualquer pessoa logada abria a
    pagina e lia o titulo de um curso de outra equipe.
 3. O POST do coordenador abre a v2 e leva a tela de equipe DA NOVA VERSAO
    (spec 4.5, passo 3: a equipe e montada do zero).
 4. A recusa do servico (ValidationError) vira mensagem na tela e devolve ao
    curso, sem criar versao - e mostra TODAS as mensagens, nao so a primeira.
 5. Metodo fora de GET/POST responde 405 (convencao do Plano 3).
 6. `cursos/curso.html` oferece o link "Abrir nova versao" so a quem pode abrir:
    o curso precisa estar PUBLICADO e a pessoa precisa ser coordenador ou o
    professor responsavel. Aluno da equipe nao ve; ninguem ve antes de publicar.
 7. A partir da v2, a tela de producao diz qual versao e por que ela foi aberta.

Texto de tela em portugues acentuado (CLAUDE.md). O plano trazia o template e os
testes sem acento, o que obrigaria a escrever "Versao" no HTML: o teste e que
mudou, nao o template.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel
from apps.cursos.models import Curso


@pytest.fixture
def curso_publicado(dados_curso, aluno, professor, coordenador):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    curso.refresh_from_db()
    return curso


# --- Regra 1: rota e login ------------------------------------------------


@pytest.mark.django_db
def test_visitante_anonimo_vai_para_o_login(client, curso_publicado):
    resposta = client.get(reverse("nova_versao", args=[curso_publicado.pk]))

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))


# --- Regra 2: a guarda vale no GET ----------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("intruso", ["aluno", "outro_professor"])
def test_quem_nao_abre_versao_nem_ve_a_pagina(client, curso_publicado, request, intruso):
    """O GET nao chama servico: aqui a guarda da view esta sozinha.

    Sem ela a pagina renderizava 200 com o titulo do curso para qualquer pessoa
    logada - um aluno de outra equipe, um professor de outro curso - e so o POST
    seria recusado, la no fundo do servico.
    """
    client.force_login(request.getfixturevalue(intruso))

    resposta = client.get(reverse("nova_versao", args=[curso_publicado.pk]))

    assert resposta.status_code == 403
    assert curso_publicado.titulo not in resposta.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("quem", ["coordenador", "professor"])
def test_quem_abre_versao_ve_o_formulario(client, curso_publicado, request, quem):
    client.force_login(request.getfixturevalue(quem))

    conteudo = client.get(reverse("nova_versao", args=[curso_publicado.pk])).content.decode()

    assert curso_publicado.titulo in conteudo
    assert 'name="motivo"' in conteudo


@pytest.mark.django_db
def test_aluno_nao_abre_nova_versao_pela_tela(client, curso_publicado, aluno):
    """A recusa do POST e da view, nao do servico - mas as duas guardas dizem nao
    aqui, entao quem prende a do servico continua sendo test_versoes.py, que o
    chama direto e confere a mensagem."""
    client.force_login(aluno)

    resposta = client.post(reverse("nova_versao", args=[curso_publicado.pk]), {"motivo": "Quero mexer."})

    assert resposta.status_code == 403
    assert not Curso.objects.filter(raiz=curso_publicado).exists()


# --- Regra 3: o POST abre a versao e leva a equipe da nova -----------------


@pytest.mark.django_db
def test_coordenador_abre_nova_versao_pela_tela(client, curso_publicado, coordenador):
    client.force_login(coordenador)

    resposta = client.post(
        reverse("nova_versao", args=[curso_publicado.pk]),
        {"motivo": "Curso incompleto: faltam atividades desplugadas."},
        follow=True,
    )

    nova = Curso.objects.get(raiz=curso_publicado, versao=2)
    assert resposta.redirect_chain[-1][0] == reverse("equipe", args=[nova.pk])
    assert "Versão 2 aberta" in resposta.content.decode()


@pytest.mark.django_db
def test_professor_responsavel_tambem_abre(client, curso_publicado, professor):
    client.force_login(professor)

    client.post(reverse("nova_versao", args=[curso_publicado.pk]), {"motivo": "Atualizar exemplos."})

    assert Curso.objects.filter(raiz=curso_publicado, versao=2).exists()


# --- Regra 4: recusa do servico volta para o curso ------------------------


@pytest.mark.django_db
def test_motivo_em_branco_volta_para_o_curso_com_o_erro(client, curso_publicado, coordenador):
    client.force_login(coordenador)

    resposta = client.post(
        reverse("nova_versao", args=[curso_publicado.pk]), {"motivo": "   "}, follow=True
    )

    assert resposta.redirect_chain[-1][0] == reverse("curso", args=[curso_publicado.pk])
    assert "Informe o motivo da nova versão." in resposta.content.decode()
    assert not Curso.objects.filter(raiz=curso_publicado).exists()


@pytest.mark.django_db
def test_mostra_todas_as_mensagens_de_erro_do_servico(client, curso_publicado, coordenador, monkeypatch):
    """Como em decidir_curso: `erro.messages[0]` engoliria a segunda razao da
    recusa, e a pessoa corrigiria uma coisa para esbarrar na outra."""

    def sempre_recusa(*args, **kwargs):
        raise ValidationError(["Primeira razão da recusa.", "Segunda razão da recusa."])

    monkeypatch.setattr(services, "abrir_nova_versao", sempre_recusa)
    client.force_login(coordenador)

    conteudo = client.post(
        reverse("nova_versao", args=[curso_publicado.pk]), {"motivo": "Qualquer."}, follow=True
    ).content.decode()

    assert "Primeira razão da recusa." in conteudo
    assert "Segunda razão da recusa." in conteudo


# --- Regra 5: metodo errado ------------------------------------------------


@pytest.mark.django_db
def test_metodo_nao_suportado_e_rejeitado(client, curso_publicado, coordenador):
    """nova_versao atende GET (formulario) e POST (abertura), entao nao pode levar
    @require_POST; ainda assim DELETE nao pode cair no ramo de leitura por acaso."""
    client.force_login(coordenador)

    resposta = client.delete(reverse("nova_versao", args=[curso_publicado.pk]))

    assert resposta.status_code == 405
    assert not Curso.objects.filter(raiz=curso_publicado).exists()


# --- Regra 6: o link na tela de producao ----------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("quem", ["coordenador", "professor"])
def test_link_de_nova_versao_aparece_para_quem_pode_abrir(client, curso_publicado, request, quem):
    client.force_login(request.getfixturevalue(quem))

    conteudo = client.get(reverse("curso", args=[curso_publicado.pk])).content.decode()

    assert reverse("nova_versao", args=[curso_publicado.pk]) in conteudo


@pytest.mark.django_db
def test_aluno_da_equipe_nao_ve_o_link_de_nova_versao(client, curso_publicado, aluno):
    client.force_login(aluno)

    conteudo = client.get(reverse("curso", args=[curso_publicado.pk])).content.decode()

    assert curso_publicado.titulo in conteudo
    assert reverse("nova_versao", args=[curso_publicado.pk]) not in conteudo


@pytest.mark.django_db
def test_link_de_nova_versao_nao_aparece_antes_de_publicar(client, dados_curso, professor):
    """So se abre versao de curso PUBLICADO: oferecer o link num rascunho e
    prometer uma porta que o servico fecha na cara."""
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)

    conteudo = client.get(reverse("curso", args=[curso.pk])).content.decode()

    assert curso.titulo in conteudo
    assert reverse("nova_versao", args=[curso.pk]) not in conteudo


# --- Regra 7: a producao diz em que versao esta ---------------------------


@pytest.mark.django_db
def test_tela_de_producao_da_v2_mostra_versao_e_motivo(client, curso_publicado, coordenador):
    nova = services.abrir_nova_versao(
        curso_publicado, por=coordenador, motivo="Faltam atividades desplugadas."
    )
    client.force_login(coordenador)

    conteudo = client.get(reverse("curso", args=[nova.pk])).content.decode()

    assert "Versão 2" in conteudo
    assert "Faltam atividades desplugadas." in conteudo


@pytest.mark.django_db
def test_tela_de_producao_da_v1_nao_fala_de_versao(client, dados_curso, professor):
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)

    conteudo = client.get(reverse("curso", args=[curso.pk])).content.decode()

    assert "Versão 1" not in conteudo
