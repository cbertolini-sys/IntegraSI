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
# insensível a acento — sem isso, uma escola digitando "seguranca" (como as
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
