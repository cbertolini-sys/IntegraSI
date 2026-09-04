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
def proposta(professor):
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
    import re

    client.force_login(professor)
    html = client.get(
        reverse("ficha_habilidades", args=[proposta.pk]),
        {"referencial": habilidades.pk, "etapa_ano": ""},
    ).content.decode()
    # Espaco normalizado: a frase e quebrada em varias linhas no template, e
    # conferir o literal fazia o teste depender de onde a linha termina.
    texto = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert "organiza o que oferece por etapa escolar" in texto
    # Precisa dizer ONDE: a pessoa escolheu o referencial e os campos de publico
    # ficam dois acima. Foi o relato de quem usou que trouxe esta frase.
    assert "nos campos acima" in texto


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


@pytest.mark.django_db
def test_bloco_fica_colado_ao_campo_de_referencial(client, proposta, professor, habilidades):
    """Quem escolhe o referencial precisa ver a lista ali mesmo.

    O bloco ficava no fim do formulario, depois de palavras-chave, e quem usou
    relatou que "nao aparece nada": a lista estava a meia tela de distancia do
    campo que a produz. A assercao e sobre a POSICAO no HTML, porque e disso que
    a queixa tratava, e nada mais no sistema garante ordem de template."""
    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    posicao_referencial = html.index('id="id_referencial"')
    posicao_bloco = html.index('id="habilidades"')
    # Pre-requisitos e o campo seguinte na ordem da tela; carga horaria passou a
    # vir antes do referencial, e prender o bloco a ela deixaria de dizer
    # "colado ao referencial" e passaria a dizer "em algum lugar depois".
    posicao_seguinte = html.index('id="id_pre_requisitos"')
    assert posicao_referencial < posicao_bloco < posicao_seguinte


@pytest.mark.django_db
def test_referencial_oferece_nenhum_por_extenso(client, proposta, professor, bncc):
    """O vazio que o Django gera e "---------", que nao diz nada.

    Curso sem referencial e de primeira classe (spec 4.2): a opcao precisa se
    chamar pelo nome, senao parece campo que a pessoa esqueceu de preencher."""
    import re

    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    select = re.search(r'<select name="referencial".*?</select>', html, re.S).group(0)
    opcoes = re.findall(r"<option[^>]*>([^<]*)</option>", select)
    assert opcoes[0] == "Nenhum"
    assert "---------" not in select


@pytest.mark.django_db
def test_escolher_nenhum_esvazia_o_bloco(client, proposta, professor, habilidades):
    """A segunda metade: escolher Nenhum tem de apagar a lista.

    O curso ja tem referencial gravado, e a view precisa distinguir "o campo veio
    vazio" de "o campo nao veio". Com `GET.get(...) or curso.referencial_id`, o
    vazio caia de volta no gravado e as habilidades continuavam na tela depois de
    a pessoa escolher Nenhum."""
    proposta.referencial = habilidades
    proposta.etapa_ano = "EF05"
    proposta.save()

    client.force_login(professor)
    html = client.get(
        reverse("ficha_habilidades", args=[proposta.pk]),
        {"referencial": "", "etapa_ano": "EF05"},
    ).content.decode()
    assert "Nenhum referencial escolhido" in html
    assert "EF05CO01" not in html


@pytest.mark.django_db
def test_ficha_oferece_cinco_caixas_de_palavra_chave(client, proposta, professor):
    """Cinco caixas, e nao uma linha com virgulas: deixa obvio quantas se espera e
    evita que alguem escreva uma frase inteira num campo so."""
    import re

    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    caixas = re.findall(r'name="palavras_chave_\d"', html)
    assert len(caixas) == 5


@pytest.mark.django_db
def test_as_cinco_caixas_viram_um_texto_so(proposta, professor):
    """O campo do banco continua sendo um texto, porque e ele que alimenta a busca."""
    from apps.cursos import services
    from apps.cursos.forms import FichaCursoForm

    dados = ficha_valida()
    dados.pop("palavras_chave", None)
    for i, palavra in enumerate(["robotica", "sucata", "reciclagem", "motor", "oficina"]):
        dados[f"palavras_chave_{i}"] = palavra
    form = FichaCursoForm(dados, instance=proposta)
    assert form.is_valid() is True, form.errors
    services.atualizar_ficha(proposta, form.cleaned_data, por=professor)
    proposta.refresh_from_db()
    assert proposta.palavras_chave == "robotica, sucata, reciclagem, motor, oficina"


@pytest.mark.django_db
def test_caixas_voltam_preenchidas_ao_reabrir(proposta, professor):
    """Ida e volta: o texto gravado precisa se repartir de volta nas cinco caixas,
    senao a equipe reescreve tudo a cada edicao."""
    from apps.cursos.forms import FichaCursoForm

    import re

    proposta.palavras_chave = "robotica, sucata, reciclagem, motor, oficina"
    proposta.save()
    form = FichaCursoForm(instance=proposta)
    # O HTML renderizado, e nao BoundField.value(): este devolve o texto gravado
    # cru, porque quem reparte e o widget, na hora de desenhar. O que interessa e
    # o que a pessoa ve nas caixas.
    caixas = re.findall(r'name="palavras_chave_\d"[^>]*value="([^"]*)"', str(form["palavras_chave"]))
    assert caixas == ["robotica", "sucata", "reciclagem", "motor", "oficina"]


@pytest.mark.django_db
def test_caixas_vazias_nao_inventam_virgulas(proposta, professor):
    """Prende o outro lado do reparte: ficha sem palavra nenhuma nao pode gravar
    uma sequencia de virgulas, que a busca indexaria como lixo."""
    from apps.cursos import services
    from apps.cursos.forms import FichaCursoForm

    dados = ficha_valida()
    dados.pop("palavras_chave", None)
    form = FichaCursoForm(dados, instance=proposta)
    assert form.is_valid() is True, form.errors
    services.atualizar_ficha(proposta, form.cleaned_data, por=professor)
    proposta.refresh_from_db()
    assert proposta.palavras_chave == ""


@pytest.mark.django_db
def test_a_ficha_desenha_todos_os_campos_do_formulario(client, proposta, professor):
    """A ficha renderiza campo a campo, agrupado em secoes, e nao por form.as_p.

    O preco disso e que acrescentar um campo ao formulario e esquecer o template
    nao quebraria nada: o campo simplesmente nunca apareceria, e a pessoa nao
    teria como preencher o que o portao vai cobrar. Este teste e o que cobra.

    `competencias` fica de fora de proposito: ele vira o bloco de habilidades, com
    caixas de nome `competencias` sem `id_competencias`, e tem teste proprio.
    """
    from apps.cursos.forms import FichaCursoForm
    from apps.cursos.models import Tema

    # Campo de escolha sem opcao nenhuma nao desenha `name=`, e mostra um aviso no
    # lugar. Um tema cadastrado deixa o campo aparecer de verdade, que e o que este
    # teste mede; sem ele, a ausencia legitima do campo vazio se confundiria com a
    # ausencia por esquecimento no template, e a regra deixaria de prender.
    Tema.objects.create(nome="Robótica Educacional")

    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    ausentes = [
        nome
        for nome in FichaCursoForm().fields
        if nome != "competencias" and f'name="{nome}"' not in html
        and f'name="{nome}_0"' not in html
    ]
    assert ausentes == []


# --- O referencial reage ao tipo de publico (a pedido) -----------------------


def opcoes_de_referencial(html):
    import re

    select = re.search(r'<select name="referencial".*?</select>', html, re.S)
    return re.findall(r"<option[^>]*>([^<]*)</option>", select.group(0)) if select else []


@pytest.mark.django_db
def test_bncc_nao_aparece_sem_publico_escolar(client, proposta, professor, habilidades):
    """A BNCC organiza por etapa escolar: oferece-la a um curso comunitario e
    oferecer o que nao serve. A regra vem do DADO (o referencial TEM competencias
    por etapa), nunca da sigla: nenhuma tela pode pressupor BNCC (spec 4.2).

    Usa `habilidades`, e nao `bncc`: sem o CSV importado o referencial nao tem
    competencia nenhuma e por isso nao organiza por etapa, entao continuaria na
    lista. E o mesmo criterio que impede um referencial recem-criado de travar
    curso nenhum."""
    from apps.cursos.choices import TipoPublico

    client.force_login(professor)
    for tipo in ("", TipoPublico.COMUNITARIO):
        html = client.get(
            reverse("ficha_referencial", args=[proposta.pk]), {"tipo_publico": tipo}
        ).content.decode()
        assert opcoes_de_referencial(html) == ["Nenhum"], tipo


@pytest.mark.django_db
def test_bncc_aparece_com_publico_escolar(client, proposta, professor, habilidades):
    """Prende o outro lado: sem este par, esconder a BNCC sempre passaria."""
    from apps.cursos.choices import TipoPublico

    client.force_login(professor)
    html = client.get(
        reverse("ficha_referencial", args=[proposta.pk]),
        {"tipo_publico": TipoPublico.ESCOLAR},
    ).content.decode()
    assert opcoes_de_referencial(html) == ["Nenhum", "BNCC da Computação"]


@pytest.mark.django_db
def test_referencial_sem_etapa_aparece_em_qualquer_publico(client, proposta, professor):
    """A regra e sobre organizar por etapa, e nao sobre ser a BNCC: um referencial
    sem competencias por etapa serve a curso comunitario e continua na lista."""
    from apps.referenciais.models import Referencial

    Referencial.objects.create(nome="Referencial Livre", sigla="LIVRE")
    client.force_login(professor)
    html = client.get(
        reverse("ficha_referencial", args=[proposta.pk]), {"tipo_publico": ""}
    ).content.decode()
    assert opcoes_de_referencial(html) == ["Nenhum", "Referencial Livre"]


@pytest.mark.django_db
def test_trocar_para_comunitario_esvazia_as_habilidades(client, proposta, professor, habilidades):
    """A troca precisa levar as habilidades junto: deixar a lista da BNCC na tela
    de um curso que nao pode mais adota-la seria pior que nao mostrar nada."""
    from apps.cursos.choices import TipoPublico

    proposta.referencial = habilidades
    proposta.tipo_publico = TipoPublico.ESCOLAR
    proposta.etapa_ano = "EF05"
    proposta.save()

    client.force_login(professor)
    html = client.get(
        reverse("ficha_referencial", args=[proposta.pk]),
        {"tipo_publico": TipoPublico.COMUNITARIO, "etapa_ano": ""},
    ).content.decode()
    assert opcoes_de_referencial(html) == ["Nenhum"]
    assert "EF05CO01" not in html


@pytest.mark.django_db
def test_a_tela_explica_por_que_a_lista_esta_curta(client, proposta, professor, habilidades):
    """Sumir sem explicacao vira defeito aos olhos de quem usa: foi assim que o
    bloco de habilidades vazio virou "nao aparece nada"."""
    import re

    client.force_login(professor)
    html = client.get(
        reverse("ficha_referencial", args=[proposta.pk]), {"tipo_publico": ""}
    ).content.decode()
    texto = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert "aparecem aqui quando o tipo de público é escolar" in texto


@pytest.mark.django_db
def test_escolha_que_saiu_da_lista_nao_fica_marcada(client, proposta, professor, habilidades):
    """O caso real da troca, que o teste anterior nao alcancava.

    O HTMX manda o valor ATUAL do select junto com o novo tipo de publico, entao a
    requisicao chega com tipo_publico=COMUNITARIO e referencial=BNCC ao mesmo
    tempo. Sem limpar, o select voltaria com a BNCC marcada numa lista que nao a
    contem mais, e as habilidades dela seguiriam na tela.
    """
    import re

    client.force_login(professor)
    html = client.get(
        reverse("ficha_referencial", args=[proposta.pk]),
        {
            "tipo_publico": "COMUNITARIO",
            "etapa_ano": "EF05",
            "referencial": str(habilidades.pk),
        },
    ).content.decode()

    assert opcoes_de_referencial(html) == ["Nenhum"]
    # A opcao marcada precisa ser "Nenhum", e nao "nenhuma marcada": select sem
    # marcacao alguma cairia no primeiro item de qualquer jeito, e o teste passaria
    # sem provar que a escolha antiga foi desfeita.
    select = re.search(r'<select name="referencial".*?</select>', html, re.S).group(0)
    marcada = re.search(r"<option[^>]*selected[^>]*>([^<]*)</option>", select)
    assert marcada is not None and marcada.group(1) == "Nenhum"
    assert "EF05CO01" not in html


# --- A etapa reage ao tipo de publico (a pedido) -----------------------------


def opcoes_de_etapa(html):
    import re

    select = re.search(r'<select name="etapa_ano".*?</select>', html, re.S)
    return re.findall(r"<option[^>]*>([^<]*)</option>", select.group(0)) if select else []


@pytest.mark.django_db
def test_publico_comunitario_deixa_so_nenhum_na_etapa(client, proposta, professor):
    """Curso.clean() ja recusa etapa em curso comunitario. O select oferecia as
    treze mesmo assim, e a pessoa so descobria ao salvar."""
    client.force_login(professor)
    html = client.get(
        reverse("ficha_etapa", args=[proposta.pk]), {"tipo_publico": "COMUNITARIO"}
    ).content.decode()
    assert opcoes_de_etapa(html) == ["Nenhum"]


@pytest.mark.django_db
def test_publico_escolar_oferece_as_etapas(client, proposta, professor):
    """Prende o outro lado: sem este par, esvaziar sempre passaria."""
    client.force_login(professor)
    html = client.get(
        reverse("ficha_etapa", args=[proposta.pk]), {"tipo_publico": "ESCOLAR"}
    ).content.decode()
    opcoes = opcoes_de_etapa(html)
    assert opcoes[0] == "Nenhum"
    assert "5º ano do Ensino Fundamental" in opcoes
    assert len(opcoes) == 14


@pytest.mark.django_db
def test_o_vazio_da_etapa_se_chama_nenhum(client, proposta, professor):
    """O "---------" do Django nao diz nada. Curso sem etapa e legitimo (publico
    comunitario), entao a opcao precisa se chamar pelo nome."""
    import re

    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    assert opcoes_de_etapa(html)[0] == "Nenhum"
    # Nenhum select da ficha mostra o "---------" do Django.
    assert "---------" not in html
    # E os rotulos sao diferentes de proposito: "Nenhum" e estado legitimo da
    # etapa; tipo de publico e formato vazios sao pendencia que o portao cobra, e
    # chama-los de "Nenhum" diria que estao resolvidos.
    for campo in ("tipo_publico", "formato"):
        select = re.search(rf'<select name="{campo}".*?</select>', html, re.S).group(0)
        assert re.findall(r"<option[^>]*>([^<]*)</option>", select)[0] == "A definir"


@pytest.mark.django_db
def test_trocar_para_comunitario_desmarca_a_etapa(client, proposta, professor):
    """Mesmo caso do referencial: o HTMX manda o valor atual do select junto com o
    novo tipo de publico, entao a etapa antiga chega na mesma requisicao."""
    import re

    proposta.etapa_ano = "EF05"
    proposta.save()
    client.force_login(professor)
    html = client.get(
        reverse("ficha_etapa", args=[proposta.pk]),
        {"tipo_publico": "COMUNITARIO", "etapa_ano": "EF05"},
    ).content.decode()
    select = re.search(r'<select name="etapa_ano".*?</select>', html, re.S).group(0)
    marcada = re.search(r"<option[^>]*selected[^>]*>([^<]*)</option>", select)
    assert marcada is not None and marcada.group(1) == "Nenhum"


@pytest.mark.django_db
def test_a_tela_desenha_o_gatilho_de_ajuda_de_cada_campo(client, proposta, professor):
    """Ponta a ponta: a ajuda escrita em Python chega ao HTML como `data-ajuda`,
    que e onde o Tippy a encontra.

    Sem este teste, o `help_text` poderia estar certo em todos os formularios e a
    tela continuar muda: sao duas pontas de uma fiacao, e o teste do help_text
    prova so uma delas."""
    import re

    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    gatilhos = re.findall(r'class="ajuda-campo"\s+data-ajuda="([^"]+)"', html)
    assert len(gatilhos) >= 9, f"só {len(gatilhos)} gatilhos"
    assert any("catálogo" in g for g in gatilhos)


@pytest.mark.django_db
def test_o_gatilho_nao_e_um_botao_de_acao(client, proposta, professor):
    """O gatilho e um <button> por ser interativo, e nao por ser botao de acao:
    nao pode trazer a classe `botao`, que o pintaria de azul com 2,75rem de altura
    ao lado de cada rotulo. Foi o primeiro efeito colateral que apareceu."""
    import re

    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    for classes in re.findall(r'<button[^>]*class="([^"]*ajuda-campo[^"]*)"', html):
        assert "botao" not in classes.split(), classes


@pytest.mark.django_db
def test_nenhuma_referencia_de_acessibilidade_fica_pendurada(client, proposta, professor):
    """`aria-describedby` precisa apontar para um elemento que existe.

    O Django escreve esse atributo em todo campo com help_text. Ao trocar a ajuda
    visivel por um balao, e facil apagar o alvo e deixar a referencia no vazio:
    quem usa leitor de tela perderia a explicacao justamente por causa da melhoria
    visual. Este teste cobre as duas pontas, o campo e o alvo.
    """
    import re

    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    apontados = set(re.findall(r'aria-describedby="([^"]+)"', html))
    existentes = set(re.findall(r'id="([^"]+)"', html))
    assert apontados, "nenhum aria-describedby na tela"
    penduradas = sorted(a for a in apontados if a not in existentes)
    assert penduradas == [], f"aria-describedby sem alvo: {penduradas}"


@pytest.mark.django_db
def test_gatilho_de_ajuda_fica_na_linha_do_rotulo(client, proposta, professor):
    """`.campo label` e `display: block`, entao o gatilho solto caia na linha de
    baixo, sob o texto. Fica dentro do invólucro que os poe lado a lado.

    A assercao e sobre a estrutura, e nao sobre pixels: CSS nao da para testar
    aqui, mas o invólucro e a condicao para o layout funcionar, e apaga-lo devolve
    o defeito."""
    import re

    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    invólucros = re.findall(r'<span class="rotulo-campo">(.*?)</span>', html, re.S)
    assert invólucros, "nenhum invólucro de rótulo"
    com_gatilho = [i for i in invólucros if "ajuda-campo" in i]
    assert len(com_gatilho) >= 9
    for trecho in com_gatilho:
        assert "<label" in trecho, "gatilho fora do invólucro do rótulo"


@pytest.mark.django_db
def test_a_grade_das_palavras_chave_so_tem_as_cinco_caixas(client, proposta, professor):
    """As cinco caixas sao uma grade de cinco colunas, e todo filho direto vira
    item dela.

    Foi assim que o gatilho de ajuda as desalinhou: o invólucro do rotulo virou
    filho direto, ocupou UMA coluna e empurrou as caixas. O teste nao mede pixels;
    ele lista quem esta na grade, que e a condicao para o alinhamento existir.

    O `helptext` escondido entra na lista porque esta no HTML, mas e
    `position: absolute` e por isso nao ocupa celula.
    """
    import re

    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    i = html.index("caixas-palavras")
    bloco = html[i:html.index("</div>", i)]

    caixas = re.findall(r'name="palavras_chave_\d"', bloco)
    assert len(caixas) == 5

    # Filhos diretos, na ordem: o invólucro do rótulo, as cinco caixas e a ajuda
    # escondida. Qualquer elemento visível a mais quebra o alinhamento.
    assert bloco.count('class="rotulo-campo"') == 1
    assert 'class="ajuda"' not in bloco, "texto de ajuda visível voltou para a grade"


@pytest.mark.django_db
def test_temas_sao_caixas_de_marcar(client, proposta, professor):
    """O `<select multiple>` do Django pede Ctrl para escolher mais de um, que e
    conhecimento que ninguem tem por obrigacao.

    Continua sendo multipla escolha: um dos cursos do sistema ja tem dois temas, e
    trocar por escolha unica faria ele perder um."""
    import re

    from apps.cursos.models import Tema

    Tema.objects.create(nome="Robótica Educacional")
    Tema.objects.create(nome="Segurança Digital")
    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()

    assert '<select name="temas"' not in html
    caixas = re.findall(r'<input type="checkbox" name="temas"', html)
    assert len(caixas) == 2


@pytest.mark.django_db
def test_temas_continuam_aceitando_mais_de_um(proposta, professor):
    """Prende o que a troca de widget nao podia quebrar."""
    from apps.cursos import services
    from apps.cursos.models import Tema

    a = Tema.objects.create(nome="Robótica Educacional")
    b = Tema.objects.create(nome="Segurança Digital")
    services.atualizar_ficha(proposta, ficha_valida(temas=[a.pk, b.pk]), por=professor)
    assert proposta.temas.count() == 2


@pytest.mark.django_db
def test_campo_sem_opcao_cadastrada_diz_que_esta_vazio(client, proposta, professor):
    """As caixas de marcar somem por inteiro num sistema sem tema cadastrado, e a
    pessoa via o rotulo "Temas" com o vazio embaixo, sem saber se era erro.

    Foi o teste de completude do formulario que apanhou isso: ele exigia o campo
    no HTML e o campo nao estava la. O <select multiple> anterior ao menos
    aparecia vazio; dizer o que houve e mais honesto que os dois.
    """
    from apps.cursos.models import Tema

    assert Tema.objects.count() == 0
    client.force_login(professor)
    html = client.get(reverse("ficha", args=[proposta.pk])).content.decode()
    assert "Nada cadastrado ainda" in html
    assert 'name="temas"' not in html
