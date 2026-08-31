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


# --- O bloco de habilidades do referencial (Plano 7) -------------------------


@pytest.fixture
def bncc(db):
    from django.core.management import call_command
    from apps.referenciais.models import Referencial

    call_command("loaddata", "bncc_computacao", verbosity=0)
    return Referencial.objects.get(sigla="BNCC-COMP")


@pytest.fixture
def habilidades(bncc):
    from pathlib import Path

    from django.conf import settings
    from django.core.management import call_command

    call_command(
        "importar_competencias", referencial="BNCC-COMP",
        csv=str(Path(settings.BASE_DIR) / "docs" / "dados" / "bncc_computacao_habilidades.csv"),
        verbosity=0,
    )
    return bncc


@pytest.mark.django_db
def test_bloco_de_habilidades_nao_existe_sem_referencial(client, proposta, professor):
    """Spec 4.2: campo vazio de um referencial que nao foi adotado e ruido."""
    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    assert 'id="habilidades"' in html
    assert "Nenhum referencial escolhido" in html


@pytest.mark.django_db
def test_bloco_lista_so_as_habilidades_da_etapa(client, proposta, professor, habilidades):
    client.force_login(professor)
    html = client.get(
        reverse("ficha_habilidades", args=[proposta.pk]),
        {"referencial": habilidades.pk, "etapa_ano": "EF05"},
    ).content.decode()
    assert "EF05CO01" in html
    assert "EF01CO01" not in html


@pytest.mark.django_db
def test_bloco_do_ensino_medio_aceita_qualquer_um_dos_tres_anos(
    client, proposta, professor, habilidades
):
    """As habilidades do Medio valem para os tres anos de uma vez (spec 4.2)."""
    client.force_login(professor)
    for ano in ("EM01", "EM02", "EM03"):
        html = client.get(
            reverse("ficha_habilidades", args=[proposta.pk]),
            {"referencial": habilidades.pk, "etapa_ano": ano},
        ).content.decode()
        assert "EM13CO01" in html, ano


@pytest.mark.django_db
def test_educacao_infantil_usa_o_termo_do_documento(
    client, proposta, professor, habilidades
):
    """O documento diz "objetivo de aprendizagem" na Infantil e "habilidade" do
    1o ano em diante; a tela usa o termo da etapa (spec 4.2)."""
    import re

    client.force_login(professor)

    def frase(etapa):
        """So o texto que a pessoa le. A palavra "habilidades" tambem aparece no
        id do bloco e na url do HTMX, que sao estrutura: procurar no HTML inteiro
        confundiria as duas coisas e o teste falharia por motivo errado."""
        html = client.get(
            reverse("ficha_habilidades", args=[proposta.pk]),
            {"referencial": habilidades.pk, "etapa_ano": etapa},
        ).content.decode()
        return re.search(r'<p class="apoio">(.*?)</p>', html, re.S).group(1)

    infantil = frase("EI")
    assert "objetivos de aprendizagem" in infantil
    assert "habilidades" not in infantil

    quinto = frase("EF05")
    assert "habilidades" in quinto
    assert "objetivos de aprendizagem" not in quinto


@pytest.mark.django_db
def test_bloco_pede_a_etapa_quando_falta(client, proposta, professor, habilidades):
    """Referencial escolhido e curso sem etapa: a tela explica em vez de listar
    nada e deixar a pessoa achando que a BNCC nao tem conteudo."""
    client.force_login(professor)
    html = client.get(
        reverse("ficha_habilidades", args=[proposta.pk]),
        {"referencial": habilidades.pk, "etapa_ano": ""},
    ).content.decode()
    assert "por etapa escolar" in html


@pytest.mark.django_db
def test_get_do_bloco_recusa_quem_nao_e_da_equipe(client, proposta, outro_aluno, habilidades):
    """A guarda da view do bloco, isolada: e um GET e ela responde sozinha.
    Sem ela, qualquer pessoa logada leria a ficha de qualquer curso por esta url."""
    client.force_login(outro_aluno)
    resposta = client.get(
        reverse("ficha_habilidades", args=[proposta.pk]),
        {"referencial": habilidades.pk, "etapa_ano": "EF05"},
    )
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_habilidade_de_outra_etapa_e_recusada(proposta, habilidades):
    """A tela filtra, mas um POST forjado nao passa pela tela. A regra fica no
    formulario, onde tem mensagem e teste."""
    from apps.cursos.forms import FichaCursoForm

    de_outra_etapa = habilidades.competencias.filter(etapa="EI").first()
    form = FichaCursoForm(
        ficha_valida(
            etapa_ano="EF05", referencial=habilidades.pk,
            competencias=[de_outra_etapa.pk],
        ),
        instance=proposta,
    )
    assert form.is_valid() is False
    assert "competencias" in form.errors


@pytest.mark.django_db
def test_habilidade_da_etapa_certa_e_aceita(proposta, habilidades):
    """Prende o outro lado: sem este par, um `raise` incondicional passaria."""
    from apps.cursos.forms import FichaCursoForm

    da_etapa = list(habilidades.competencias.filter(etapa="EF05")[:2])
    form = FichaCursoForm(
        ficha_valida(
            etapa_ano="EF05", referencial=habilidades.pk,
            competencias=[c.pk for c in da_etapa],
        ),
        instance=proposta,
    )
    assert form.is_valid() is True, form.errors
