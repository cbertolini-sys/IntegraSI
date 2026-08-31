"""A ficha do curso: o que a equipe preenche depois da proposta (Plano 6).

As regras que este arquivo prende:

 1. Membro da equipe edita a ficha.
 2. Quem nao e da equipe nao edita.
 3. Curso publicado nao tem ficha editavel (muda por nova versao, spec 4.5).
 4. Curso em producao tem.
 5. A guarda da VIEW responde sozinha por GET.
 6. Competencia de outro referencial e recusada.
 7. Tema definido PELA TELA reindexa e aparece na busca (fiacao, nao servico).
"""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.cursos import busca, permissions, services
from apps.cursos.choices import Formato, StatusCurso, TipoPublico
from apps.cursos.models import Curso, Tema


@pytest.fixture
def proposta(edicao, professor):
    return services.criar_curso(titulo="Robotica com sucata", professor_responsavel=professor)


@pytest.fixture
def referencial_alheio(db):
    """Um referencial que NAO e o do curso, com uma competencia dentro."""
    from apps.referenciais.models import Categoria, Competencia, Referencial

    referencial = Referencial.objects.create(
        nome="Referencial de Fora", sigla="FORA", min_competencias=1, max_competencias=5
    )
    categoria = Categoria.objects.create(referencial=referencial, nome="Categoria", ordem=1)
    Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="EF05XX01",
        descricao="Competencia de outro referencial", etapa="EF05", ordem=1,
    )
    return referencial


def ficha_valida(**extra):
    dados = {
        "titulo": "Robotica com sucata reciclada",
        "resumo": "Oficina de montagem com material reaproveitado.",
        "tipo_publico": TipoPublico.ESCOLAR,
        "etapa_ano": "EF05",
        "publico_descricao": "",
        "referencial": None,
        "competencias": [],
        "carga_horaria": 8,
        "formato": Formato.PRESENCIAL,
        "pre_requisitos": "",
        "temas": [],
        "palavras_chave": "",
    }
    dados.update(extra)
    return dados


# --- Regras 1 e 2: quem edita -------------------------------------------------


@pytest.mark.django_db
def test_membro_da_equipe_edita_a_ficha(proposta, professor, aluno):
    services.adicionar_membro(proposta, aluno, por=professor)
    services.atualizar_ficha(proposta, ficha_valida(), por=aluno)
    proposta.refresh_from_db()
    assert proposta.titulo == "Robotica com sucata reciclada"
    assert proposta.carga_horaria == 8


@pytest.mark.django_db
def test_quem_nao_e_da_equipe_nao_edita_a_ficha(proposta, outro_aluno):
    with pytest.raises(PermissionDenied):
        services.atualizar_ficha(proposta, ficha_valida(), por=outro_aluno)


# --- Regras 3 e 4: so enquanto o curso esta em producao ----------------------


@pytest.mark.django_db
def test_ficha_de_curso_publicado_nao_e_editavel(proposta, professor):
    """Curso publicado muda por nova versao (spec 4.5), nunca por edicao no lugar:
    editar direto trocaria embaixo do catalogo um curso que alguem ja solicitou."""
    proposta.status = StatusCurso.PUBLICADO
    proposta.save(update_fields=["status"])
    assert permissions.pode_editar_ficha(professor, proposta) is False


@pytest.mark.django_db
def test_ficha_em_producao_e_editavel(proposta, professor, aluno):
    """Prende o outro lado do teste acima: se STATUS_EDITAVEIS ficasse vazio, so
    aquele passaria."""
    services.adicionar_membro(proposta, aluno, por=professor)
    proposta.refresh_from_db()
    assert proposta.status == StatusCurso.EM_PRODUCAO
    assert permissions.pode_editar_ficha(aluno, proposta) is True


# --- Regra 5: a guarda da view, isolada por GET ------------------------------


@pytest.mark.django_db
def test_get_da_ficha_recusa_quem_nao_e_da_equipe(client, proposta, outro_aluno):
    """Por GET de proposito. A view chama atualizar_ficha, que confere permissao
    tambem; num POST, afrouxar a guarda da view nao quebraria nada, porque o
    servico recusaria igual e o teste veria o mesmo 403. So o GET isola a view."""
    client.force_login(outro_aluno)
    assert client.get(reverse("ficha", args=[proposta.pk])).status_code == 403


@pytest.mark.django_db
def test_get_da_ficha_abre_para_membro(client, proposta, professor):
    client.force_login(professor)
    assert client.get(reverse("ficha", args=[proposta.pk])).status_code == 200


# --- Regra 6: competencia precisa ser do referencial escolhido ---------------


@pytest.mark.django_db
def test_competencia_de_outro_referencial_e_recusada(proposta, referencial_alheio):
    """A ficha nao filtra o select por referencial: filtrar no cliente exigiria JS
    de dependencia entre campos. A regra fica na validacao, com mensagem."""
    from apps.cursos.forms import FichaCursoForm

    form = FichaCursoForm(
        ficha_valida(competencias=[referencial_alheio.competencias.first().pk]),
        instance=proposta,
    )
    assert form.is_valid() is False
    assert "competencias" in form.errors


@pytest.mark.django_db
def test_competencia_do_referencial_escolhido_e_aceita(proposta, referencial_alheio):
    """Prende o outro lado: com o referencial certo, a mesma competencia passa.
    Sem este par, um `raise` incondicional em clean() passaria no teste de cima."""
    from apps.cursos.forms import FichaCursoForm

    form = FichaCursoForm(
        ficha_valida(
            referencial=referencial_alheio.pk,
            competencias=[referencial_alheio.competencias.first().pk],
        ),
        instance=proposta,
    )
    assert form.is_valid() is True, form.errors


# --- Regra 7: a fiacao do tema, que veio de test_busca.py --------------------


@pytest.mark.django_db
def test_tema_definido_pela_tela_aparece_na_busca_por_tema(client, proposta, professor):
    """Herdeiro do teste que morava em test_busca.py, e pelo mesmo motivo.

    O defeito do Plano 2 foi uma tela escrevendo curso.temas.set() direto, sem
    passar por services.definir_temas, que e quem reindexa vetor_temas. Todo curso
    com tema associado por aquela tela ficava invisivel na busca por tema, e so
    "funcionava" se alguem depois renomeasse um Tema pelo Admin e o reindex de
    TemaAdmin.save_model disparasse por coincidencia.

    Este teste vai PELA VIEW de proposito: um teste que chamasse definir_temas
    direto teria passado o tempo todo, inclusive com o bug ao vivo. E a fiacao que
    ele guarda, nao o servico.
    """
    tema = Tema.objects.create(nome="Robótica Educacional")
    client.force_login(professor)
    dados = ficha_valida(temas=[tema.pk])
    dados["resumo"] = "Resumo sem a palavra do tema."
    dados = {k: ("" if v is None else v) for k, v in dados.items()}
    resposta = client.post(reverse("ficha", args=[proposta.pk]), dados, follow=True)
    assert resposta.status_code == 200
    proposta.refresh_from_db()
    assert proposta.temas.count() == 1
    assert busca.buscar(Curso.objects.filter(pk=proposta.pk), "robotica").count() == 1


@pytest.mark.django_db
def test_guarda_de_atualizar_ficha_responde_sozinha(proposta, outro_aluno):
    """Isola a guarda de atualizar_ficha da guarda de definir_temas.

    A ficha completa inclui `temas`, e definir_temas confere permissao tambem: um
    teste que passe a ficha inteira nao distingue qual das duas recusou, e apagar
    uma delas deixaria a outra levantando a mesma excecao. Sem `temas` no dicionario,
    definir_temas nem e chamado, e so a guarda de atualizar_ficha pode responder.
    """
    with pytest.raises(PermissionDenied):
        services.atualizar_ficha(proposta, {"titulo": "Invadido"}, por=outro_aluno)


@pytest.mark.django_db
def test_aluno_da_equipe_define_tema_pela_ficha(proposta, professor, aluno):
    """definir_temas exigia pode_gerir_equipe, que exclui aluno: a ficha inteira
    falhava para quem a tela ja tinha autorizado."""
    services.adicionar_membro(proposta, aluno, por=professor)
    tema = Tema.objects.create(nome="Pensamento Computacional")
    services.atualizar_ficha(proposta, ficha_valida(temas=[tema.pk]), por=aluno)
    assert proposta.temas.count() == 1
