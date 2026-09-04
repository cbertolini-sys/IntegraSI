import pytest
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.cursos import busca, services
from apps.cursos.models import Curso, Tema


@pytest.fixture
def curso_robotica(dados_curso, professor):
    dados_curso.update(
        titulo="Robotica com sucata",
        resumo="Oficina de robotica de baixo custo para o 9o ano.",
        palavras_chave="arduino, motores, reciclagem",
        etapa_ano="EF09",
    )
    return services.criar_curso(**dados_curso)


@pytest.mark.django_db
def test_busca_encontra_pelo_titulo(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "robotica").count() == 1


@pytest.mark.django_db
def test_busca_ignora_acento_e_flexao(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "robótica").count() == 1
    assert busca.buscar(Curso.objects.all(), "oficinas").count() == 1


@pytest.mark.django_db
def test_busca_encontra_pela_palavra_chave(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "arduino").count() == 1


@pytest.mark.django_db
def test_busca_nao_encontra_o_que_nao_existe(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "astronomia").count() == 0


@pytest.mark.django_db
def test_busca_encontra_pelo_nome_do_tema(curso_robotica, professor):
    tema = Tema.objects.create(nome="Robotica Educacional")
    outro = Tema.objects.create(nome="Seguranca Digital")
    services.definir_temas(curso_robotica, [outro], por=professor)
    assert busca.buscar(Curso.objects.all(), "seguranca").count() == 1
    services.definir_temas(curso_robotica, [tema], por=professor)
    assert busca.buscar(Curso.objects.all(), "seguranca").count() == 0


@pytest.mark.django_db
def test_termo_vazio_devolve_tudo(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "").count() == 1


# R62: os temas que o sistema realmente distribui vêm acentuados ("Segurança
# Digital", spec do Plano 1) e é justamente por isso que a busca precisa ser
# insensível a acento - sem isso, uma escola digitando "seguranca" (como as
# pessoas de fato digitam) não encontraria nada indexado por um tema acentuado.
# Os testes do brief acima usam nomes de tema sem acento, o que não exercitaria
# essa lacuna; este teste cobre o caso real, isolando o termo para que só o
# vetor_temas (e não o título/resumo do curso) possa responder pela busca.
@pytest.mark.django_db
def test_busca_ignora_acento_no_nome_do_tema(curso_robotica, professor):
    tema_acentuado = Tema.objects.create(nome="Segurança Digital")
    services.definir_temas(curso_robotica, [tema_acentuado], por=professor)
    assert busca.buscar(Curso.objects.all(), "seguranca").count() == 1


# Global constraint do brief: "definir_temas goes through services.py and checks
# permission like every other service." Sem este teste, remover a chamada a
# permissions.garante() de definir_temas não quebraria nenhum teste do brief - os
# testes acima sempre chamam com o professor responsável.
@pytest.mark.django_db
def test_definir_temas_recusa_professor_de_outro_curso(curso_robotica, outro_professor):
    tema = Tema.objects.create(nome="Robotica Educacional")
    with pytest.raises(PermissionDenied):
        services.definir_temas(curso_robotica, [tema], por=outro_professor)


# Global constraint do brief: "Renaming a Tema must reindex the courses linked to
# it." Exercitado pelo caminho real (o Admin, unico lugar hoje que renomeia um
# Tema), nao chamando atualizar_vetor_temas diretamente - senao o teste passaria
# mesmo se o save_model do TemaAdmin nunca chamasse a reindexacao.
@pytest.mark.django_db
def test_renomear_tema_pelo_admin_reindexa_cursos_vinculados(client, curso_robotica, professor, coordenador):
    tema = Tema.objects.create(nome="Robotica Educacional")
    services.definir_temas(curso_robotica, [tema], por=professor)
    assert busca.buscar(Curso.objects.all(), "robotica").count() == 1

    coordenador.is_staff = True
    coordenador.is_superuser = True
    coordenador.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(coordenador)

    resposta = client.post(
        reverse("admin:cursos_tema_change", args=[tema.pk]),
        {"nome": "Astronomia Amadora", "slug": "", "ativo": "on"},
    )
    assert resposta.status_code == 302

    assert busca.buscar(Curso.objects.all(), "astronomia").count() == 1


# Achado da revisao do Task 4: nova_proposta (apps/cursos/views/professor.py) e o
# caminho real por onde todo curso com tema nasce, e ate agora chamava
# O teste de fiacao que vivia aqui (proposta criada PELA TELA com tema aparece na
# busca por tema) mudou de endereco no Plano 6: a tela de criacao passou a pedir so
# o titulo, e quem associa tema agora e a ficha do curso. Ele foi reescrito contra a
# tela da ficha, em apps/cursos/tests/test_ficha.py, e continua indo pela view de
# proposito: um teste que chamasse services.definir_temas direto teria passado o
# tempo todo, inclusive com o bug do Plano 2 ao vivo.

# Achado da revisao ao fix acima: CursoAdmin declara
# filter_horizontal = ["competencias", "temas"] e nao sobrescrevia save_related,
# entao associar temas a um curso pelo Admin passava pelo form.save_m2m() padrao
# do ModelAdmin - a mesma escrita direta em Curso.temas que nova_proposta fazia,
# so que por uma porta diferente (o coordenador, nao o professor). Mesmo defeito,
# caminho separado; corrigido com um save_related em CursoAdmin. Teste vai pelo
# Admin de verdade, nao chamando atualizar_vetor_temas na mao, pelo mesmo motivo
# do teste de nova_proposta acima.
@pytest.mark.django_db
def test_curso_admin_associa_tema_reindexa_para_busca(client, dados_curso, coordenador):
    tema = Tema.objects.create(nome="Robótica Educacional")
    curso = services.criar_curso(**dados_curso)

    coordenador.is_staff = True
    coordenador.is_superuser = True
    coordenador.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(coordenador)

    resposta = client.post(
        reverse("admin:cursos_curso_change", args=[curso.pk]),
        {
            "titulo": curso.titulo,
            "resumo": curso.resumo,
            "professor_responsavel": curso.professor_responsavel_id,
            "tipo_publico": curso.tipo_publico,
            "etapa_ano": curso.etapa_ano,
            "publico_descricao": curso.publico_descricao,
            "competencias": [],
            "carga_horaria": curso.carga_horaria,
            "formato": curso.formato,
            "pre_requisitos": curso.pre_requisitos,
            "temas": [tema.pk],
            "palavras_chave": curso.palavras_chave,
            "status": curso.status,
        },
    )
    assert resposta.status_code == 302

    assert busca.buscar(Curso.objects.filter(pk=curso.pk), "robotica").count() == 1


# Pergunta da revisao: TemaAdmin.save_model (reindexa por rename) e
# CursoAdmin.save_related (reindexa por reassociacao) escrevem a mesma coluna
# (vetor_temas) por gatilhos diferentes - conflitam se as duas acoes acontecerem
# na mesma sessao? Nao: cada submissao do Admin roda na sua propria
# transaction.atomic() (ModelAdmin.changeform_view), entao as duas nunca dividem
# transacao; e as duas chamam a mesma atualizar_vetor_temas, que sempre recalcula
# do zero a partir do estado atual do M2M - nao ha estado parcial ou incremento
# para as duas hooks discordarem. Este teste prova a sequencia real: renomear um
# tema (dispara o hook do TemaAdmin) e depois trocar os temas do curso pelo
# CursoAdmin (dispara o outro hook) tem que convergir para o estado final
# correto, sem sobra do nome antigo nem do tema antigo.
@pytest.mark.django_db
def test_renomear_tema_e_depois_reassociar_curso_pelo_admin_convergem(
    client, curso_robotica, professor, coordenador
):
    tema_original = Tema.objects.create(nome="Robotica Educacional")
    services.definir_temas(curso_robotica, [tema_original], por=professor)
    assert busca.buscar(Curso.objects.filter(pk=curso_robotica.pk), "educacional").count() == 1

    coordenador.is_staff = True
    coordenador.is_superuser = True
    coordenador.save(update_fields=["is_staff", "is_superuser"])
    client.force_login(coordenador)

    # 1) Renomear o tema pelo Admin: dispara TemaAdmin.save_model.
    resposta = client.post(
        reverse("admin:cursos_tema_change", args=[tema_original.pk]),
        {"nome": "Tema Renomeado", "slug": "", "ativo": "on"},
    )
    assert resposta.status_code == 302
    assert busca.buscar(Curso.objects.filter(pk=curso_robotica.pk), "renomeado").count() == 1

    # 2) Trocar os temas do curso para um tema totalmente novo pelo Admin: dispara
    # CursoAdmin.save_related. O nome antigo (renomeado) nao pode sobrar.
    tema_novo = Tema.objects.create(nome="Tema Novo")
    resposta = client.post(
        reverse("admin:cursos_curso_change", args=[curso_robotica.pk]),
        {
            "titulo": curso_robotica.titulo,
            "resumo": curso_robotica.resumo,
            "professor_responsavel": curso_robotica.professor_responsavel_id,
            "tipo_publico": curso_robotica.tipo_publico,
            "etapa_ano": curso_robotica.etapa_ano,
            "publico_descricao": curso_robotica.publico_descricao,
            "competencias": [],
            "carga_horaria": curso_robotica.carga_horaria,
            "formato": curso_robotica.formato,
            "pre_requisitos": curso_robotica.pre_requisitos,
            "temas": [tema_novo.pk],
            "palavras_chave": curso_robotica.palavras_chave,
            "status": curso_robotica.status,
        },
    )
    assert resposta.status_code == 302

    curso_robotica.refresh_from_db()
    assert busca.buscar(Curso.objects.filter(pk=curso_robotica.pk), "novo").count() == 1
    assert busca.buscar(Curso.objects.filter(pk=curso_robotica.pk), "renomeado").count() == 0
