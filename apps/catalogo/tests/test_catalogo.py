import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import Formato, StatusCurso, StatusEntregavel, TipoPublico
from apps.cursos.models import Tema


def publica(curso, membro_equipe, professor, coordenador):
    # adicionar_membro tira o curso de RASCUNHO para EM_PRODUCAO (services.py); sem
    # isso submeter_ao_coordenador recusa por status, nao pelos entregaveis. Usa um
    # aluno so da producao (nao a fixture 'aluno') para o teste de dado pessoal
    # poder adicionar 'aluno' por conta propria, sem colidir com a constraint de
    # membro unico por curso.
    services.adicionar_membro(curso, membro_equipe, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    return curso


def _leva_status(curso, status, membro_equipe, professor, coordenador):
    """Avanca o curso ate o status pedido, pelos mesmos services que a producao
    real usaria - nunca por .update() direto. Usado pela matriz de visibilidade
    (revisao do Task 5, Fix 2): cada status alcancavel precisa ser conferido nas
    duas portas (listagem e detalhe), nao so numa delas."""
    if status == StatusCurso.RASCUNHO:
        return curso
    services.adicionar_membro(curso, membro_equipe, por=professor)
    if status == StatusCurso.EM_PRODUCAO:
        return curso
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    if status == StatusCurso.AGUARDANDO_COORDENADOR:
        return curso
    if status == StatusCurso.DEVOLVIDO:
        services.devolver_curso(curso, por=coordenador, comentario="Corrija a ementa antes de reenviar.")
        return curso
    services.publicar_curso(curso, por=coordenador)
    if status == StatusCurso.DESPUBLICADO:
        services.despublicar_curso(curso, por=coordenador, motivo="Desatualizado.")
    if status == StatusCurso.SUBSTITUIDO:
        # O Plano 4 abriu o caminho real ate SUBSTITUIDO: publicar a versao
        # seguinte da linhagem. Titulo diferente de proposito - a v2 fica no
        # catalogo, e o teste confere que o titulo da v1 sumiu de la.
        nova = services.abrir_nova_versao(curso, por=coordenador, motivo="Refazer o caderno.")
        nova.titulo = "Segunda versao, outro titulo"
        nova.save()
        services.adicionar_membro(nova, membro_equipe, por=professor)
        nova.entregaveis.update(status=StatusEntregavel.APROVADO)
        nova.refresh_from_db()
        services.submeter_ao_coordenador(nova, por=professor)
        services.publicar_curso(nova, por=coordenador)
    return curso


@pytest.fixture
def curso_publicado(dados_curso, outro_aluno, professor, coordenador):
    curso = services.criar_curso(**dados_curso)
    return publica(curso, outro_aluno, professor, coordenador)


@pytest.mark.django_db
def test_catalogo_e_publico(client, curso_publicado):
    resposta = client.get(reverse("catalogo"))
    assert resposta.status_code == 200
    assert curso_publicado.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_curso_em_rascunho_nao_aparece(client, dados_curso):
    # Sem adicionar_membro o curso nunca sai de RASCUNHO (services.py); a matriz
    # de visibilidade abaixo cobre RASCUNHO nas duas portas - este teste fica
    # como o caso minimo e continua nomeado pelo que de fato exercita.
    curso = services.criar_curso(**dados_curso)
    resposta = client.get(reverse("catalogo"))
    assert curso.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_curso_despublicado_sai_do_catalogo(client, curso_publicado, coordenador):
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Desatualizado.")
    resposta = client.get(reverse("catalogo"))
    assert curso_publicado.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_pagina_publica_de_curso_nao_publicado_devolve_404(client, dados_curso):
    curso = services.criar_curso(**dados_curso)
    resposta = client.get(reverse("catalogo_curso", args=[curso.pk]))
    assert resposta.status_code == 404


@pytest.mark.django_db
def test_pagina_publica_mostra_dados_do_curso_e_nao_os_materiais(client, curso_publicado):
    resposta = client.get(reverse("catalogo_curso", args=[curso_publicado.pk]))
    conteudo = resposta.content.decode()
    assert curso_publicado.resumo in conteudo
    assert "Plano de Ensino" not in conteudo


@pytest.mark.django_db
def test_filtro_por_publico_alvo(client, curso_publicado, dados_curso, outro_aluno, professor, coordenador):
    dados_curso.update(
        titulo="Cidadania digital para adultos", tipo_publico=TipoPublico.COMUNITARIO,
        etapa_ano="", publico_descricao="Adultos em vulnerabilidade digital",
    )
    publica(services.criar_curso(**dados_curso), outro_aluno, professor, coordenador)

    # Sobre a grade, e nao sobre o HTML: o heroi ignora o filtro (test_vitrine.py).
    grade = client.get(reverse("catalogo"), {"etapa": "EF05"}).context["cursos"]
    assert curso_publicado in grade
    assert "Cidadania digital para adultos" not in [c.titulo for c in grade]


@pytest.mark.django_db
def test_filtro_comunitario(client, curso_publicado, dados_curso, outro_aluno, professor, coordenador):
    """Exclusao, nao so inclusao: curso_publicado e ESCOLAR (fixture dados_curso)
    e precisa sumir quando o filtro comunitario e aplicado."""
    dados_curso.update(
        titulo="Cidadania digital para adultos", tipo_publico=TipoPublico.COMUNITARIO,
        etapa_ano="", publico_descricao="Adultos em vulnerabilidade digital",
    )
    curso_comunitario = publica(services.criar_curso(**dados_curso), outro_aluno, professor, coordenador)

    # Sobre a grade, e nao sobre o HTML: o heroi ignora o filtro (test_vitrine.py).
    grade = client.get(reverse("catalogo"), {"comunitario": "1"}).context["cursos"]
    assert curso_comunitario in grade
    assert curso_publicado not in grade


@pytest.mark.django_db
def test_filtro_por_tema(client, dados_curso, outro_aluno, professor, coordenador):
    """O tema e marcado enquanto o curso esta em producao, e so depois ele publica.

    Era o contrario ate o Plano 6, quando definir_temas aceitava curso publicado.
    A autoridade dele passou a ser pode_editar_ficha, que congela a ficha fora da
    producao (spec 4.5: curso no catalogo muda por nova versao). A coordenacao
    segue podendo remarcar um curso publicado pelo Admin, cujo save_related
    reindexa por conta propria."""
    tema = Tema.objects.create(nome="Robotica Educacional")
    curso = services.criar_curso(**dados_curso)
    services.definir_temas(curso, [tema], por=professor)
    curso_publicado = publica(curso, outro_aluno, professor, coordenador)
    # Sobre a grade, e nao sobre o HTML: o heroi ignora o filtro (test_vitrine.py).
    assert curso_publicado in client.get(reverse("catalogo"), {"tema": tema.slug}).context["cursos"]
    assert curso_publicado not in client.get(reverse("catalogo"), {"tema": "outro"}).context["cursos"]


@pytest.mark.django_db
def test_filtro_por_formato(client, curso_publicado, dados_curso, outro_aluno, professor, coordenador):
    """Exclusao, nao so inclusao: curso_publicado e PRESENCIAL (fixture dados_curso)
    e precisa sumir quando o filtro pede ONLINE."""
    dados_curso.update(titulo="Robotica 100% online", formato=Formato.ONLINE)
    curso_online = publica(services.criar_curso(**dados_curso), outro_aluno, professor, coordenador)

    resposta = client.get(reverse("catalogo"), {"formato": Formato.ONLINE})
    # Sobre a grade, e nao sobre o HTML: o heroi ignora o filtro de proposito.
    assert curso_online in resposta.context["cursos"]
    assert curso_publicado not in resposta.context["cursos"]


@pytest.mark.django_db
def test_filtro_por_referencial(client, curso_publicado, dados_curso, outro_aluno, professor, coordenador):
    """Exclusao, nao so inclusao - e a regra que interage com o filtro de
    referencial: curso_publicado nao tem referencial nenhum (fixture dados_curso),
    entao precisa sumir quando o filtro pede um referencial especifico, mas
    continuar aparecendo sem filtro nenhum (nada pode pressupor a BNCC)."""
    from apps.referenciais.models import Categoria, Competencia, Referencial

    referencial = Referencial.objects.create(
        nome="BNCC da Computação", sigla="BNCC-COMP", min_competencias=1, max_competencias=5,
    )
    categoria = Categoria.objects.create(referencial=referencial, nome="Mundo Digital", ordem=1)
    competencia = Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="EF05CO01",
        descricao="Reconhecer padrões.", etapa="EF05", ordem=1,
    )
    dados_curso.update(titulo="Robotica com a BNCC")
    curso_bncc = services.criar_curso(**dados_curso)
    curso_bncc.referencial = referencial
    curso_bncc.save()
    curso_bncc.competencias.add(competencia)
    publica(curso_bncc, outro_aluno, professor, coordenador)

    # sem filtro, o curso sem referencial (curso_publicado) nao some do catalogo:
    # referencial e um filtro que so alguns cursos respondem, nunca um pressuposto.
    sem_filtro = client.get(reverse("catalogo")).context["cursos"]
    assert curso_publicado in sem_filtro
    assert curso_bncc in sem_filtro

    # Sobre a grade, e nao sobre o HTML: o heroi mostra os ultimos publicados
    # ignorando o filtro (ver test_vitrine.py), entao curso_publicado continua no
    # HTML mesmo filtrado por referencial.
    filtrado = client.get(reverse("catalogo"), {"referencial": "BNCC-COMP"}).context["cursos"]
    assert curso_bncc in filtrado
    assert curso_publicado not in filtrado


@pytest.mark.django_db
def test_busca_no_catalogo(client, curso_publicado):
    """Afirma sobre a GRADE (`context["cursos"]`), e nao sobre o HTML bruto.

    O heroi mostra os ultimos publicados ignorando o filtro (ver
    test_vitrine.py), entao o titulo continua no HTML mesmo quando a busca nao
    casa -- e o que o filtro governa e a grade. Mesma correcao que o Plano 4 fez
    em test_catalogo_mostra_a_linhagem_uma_vez_so, pelo mesmo motivo: assercao em
    HTML bruto quebra quando outra parte da pagina passa a citar o mesmo texto.
    """
    achou = client.get(reverse("catalogo"), {"q": "pensamento"})
    assert curso_publicado in achou.context["cursos"]
    nao_achou = client.get(reverse("catalogo"), {"q": "astronomia"})
    assert curso_publicado not in nao_achou.context["cursos"]


@pytest.mark.django_db
def test_catalogo_nao_expoe_dado_pessoal_da_equipe(client, curso_publicado, aluno, professor):
    services.adicionar_membro(curso_publicado, aluno, por=professor)
    resposta = client.get(reverse("catalogo_curso", args=[curso_publicado.pk]))
    conteudo = resposta.content.decode()
    assert aluno.cpf not in conteudo
    assert aluno.email not in conteudo


STATUS_NAO_PUBLICOS = [
    StatusCurso.RASCUNHO,
    StatusCurso.EM_PRODUCAO,
    StatusCurso.AGUARDANDO_COORDENADOR,
    StatusCurso.DEVOLVIDO,
    StatusCurso.DESPUBLICADO,
    StatusCurso.SUBSTITUIDO,
]


@pytest.mark.django_db
@pytest.mark.parametrize("status", STATUS_NAO_PUBLICOS, ids=[s.name for s in STATUS_NAO_PUBLICOS])
def test_curso_nao_publicado_fica_fora_das_duas_portas(client, dados_curso, aluno, professor, coordenador, status):
    """Matriz de visibilidade: todo status alcancavel que nao seja PUBLICADO
    precisa ficar de fora tanto da listagem quanto do detalhe - a guarda e a
    mesma (cursos_publicados()) para as duas portas, mas nada garante que uma
    tarefa futura (ex.: Plano 4 tratando SUBSTITUIDO como caso especial) nao
    abra uma delas sem passar pela outra. SUBSTITUIDO entrou na lista no Plano 4,
    Task 5, que abriu o caminho real ate ele - `_leva_status` chega la publicando
    a versao seguinte, nunca por .update()."""
    curso = services.criar_curso(**dados_curso)
    _leva_status(curso, status, aluno, professor, coordenador)
    curso.refresh_from_db()
    assert curso.status == status

    resposta_lista = client.get(reverse("catalogo"))
    assert curso.titulo not in resposta_lista.content.decode()

    resposta_detalhe = client.get(reverse("catalogo_curso", args=[curso.pk]))
    assert resposta_detalhe.status_code == 404



# --- Previa da pagina publica, para quem produz (a pedido) -------------------


@pytest.mark.django_db
def test_previa_mostra_curso_em_producao(client, dados_curso, professor):
    """A pagina publica so aceita PUBLICADO; a equipe precisa ver como o curso vai
    aparecer ANTES de publicar, que e quando ainda da para corrigir."""
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.get(reverse("previa_do_curso", args=[curso.pk]))
    assert resposta.status_code == 200
    assert curso.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_previa_se_anuncia_como_previa(client, dados_curso, professor):
    """Sem aviso, a equipe confunde a previa com a pagina no ar e acha que o curso
    ja esta publicado."""
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    html = client.get(reverse("previa_do_curso", args=[curso.pk])).content.decode()
    assert "Prévia" in html


@pytest.mark.django_db
def test_previa_nao_oferece_solicitacao(client, dados_curso, professor):
    """O botao de solicitar nao pode aparecer: o curso nao esta no catalogo, e uma
    solicitacao criada daqui apontaria para um curso que ninguem pode oferecer."""
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    html = client.get(reverse("previa_do_curso", args=[curso.pk])).content.decode()
    assert "Solicitar este curso" not in html


@pytest.mark.django_db
def test_previa_recusa_quem_nao_enxerga_o_curso(client, dados_curso, outro_aluno):
    """Material nao aprovado nao circula (spec 10). A previa e a pagina publica de
    um curso que ainda NAO e publico, entao vale a permissao do curso."""
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    client.force_login(outro_aluno)
    assert client.get(reverse("previa_do_curso", args=[curso.pk])).status_code == 403


@pytest.mark.django_db
def test_previa_recusa_visitante(client, dados_curso):
    """Sem sessao, nem 403: manda para o login. Curso em producao nao tem porta
    anonima nenhuma."""
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    resposta = client.get(reverse("previa_do_curso", args=[curso.pk]))
    assert resposta.status_code == 302
    assert "entrar" in resposta.url or "login" in resposta.url


@pytest.mark.django_db
def test_pagina_publica_continua_recusando_curso_em_producao(client, dados_curso, professor):
    """Prende o outro lado: a previa nao pode ter afrouxado a pagina publica, que
    e a porta anonima de verdade."""
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    assert client.get(reverse("catalogo_curso", args=[curso.pk])).status_code == 404


# --- A pagina publica mostra tudo o que a edicao oferece (a pedido) ----------


@pytest.fixture
def curso_cheio(dados_curso, professor):
    """Um curso com TODOS os campos da edicao preenchidos, inclusive os que
    convivem: etapa escolar e descricao do publico juntas, que passaram a ser
    complemento uma da outra."""
    from apps.cursos import services
    from apps.cursos.models import Tema
    from apps.referenciais.models import Categoria, Competencia, Referencial

    curso = services.criar_curso(**dados_curso)
    curso.publico_descricao = "Turmas da escola do campo"
    curso.pre_requisitos = "Saber ligar e desligar o computador."
    referencial = Referencial.objects.create(nome="Referencial de Teste", sigla="TESTE")
    categoria = Categoria.objects.create(referencial=referencial, nome="Eixo Um", ordem=1)
    competencia = Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="TS05CO01",
        descricao="Descricao da competencia de teste.", etapa="EF05", ordem=1,
    )
    curso.referencial = referencial
    curso.save()
    curso.competencias.add(competencia)
    services.definir_temas(curso, [Tema.objects.create(nome="Robótica Educacional")], por=professor)
    return curso


@pytest.mark.django_db
def test_a_pagina_publica_mostra_tudo_o_que_a_edicao_oferece(client, curso_cheio, professor):
    """A exigencia, por extenso: o que a equipe preenche na edicao do curso e o que
    o publico ve. Um campo que so existe no formulario e trabalho que ninguem le.

    A varredura percorre os campos do FORMULARIO, e nao uma lista escrita a mao:
    campo novo na edicao passa a ser cobrado aqui sozinho.
    """
    from apps.cursos.forms import FichaCursoForm

    client.force_login(professor)
    html = client.get(reverse("previa_do_curso", args=[curso_cheio.pk])).content.decode()

    esperado = {
        "titulo": curso_cheio.titulo,
        "resumo": curso_cheio.resumo,
        "carga_horaria": str(curso_cheio.carga_horaria),
        "formato": curso_cheio.get_formato_display(),
        "etapa_ano": curso_cheio.get_etapa_ano_display(),
        "publico_descricao": curso_cheio.publico_descricao,
        "pre_requisitos": curso_cheio.pre_requisitos,
        "temas": "Robótica Educacional",
        "referencial": curso_cheio.referencial.nome,
        "competencias": "TS05CO01",
        "palavras_chave": "pensamento computacional",
        "tipo_publico": curso_cheio.get_tipo_publico_display(),
    }
    # Se um campo entrar no formulario e ninguem decidir como ele aparece, o teste
    # acusa aqui, e nao meses depois numa tela incompleta.
    assert set(esperado) == set(FichaCursoForm().fields)

    faltando = [campo for campo, valor in esperado.items() if valor not in html]
    assert faltando == [], f"não aparecem na página pública: {faltando}"


@pytest.mark.django_db
def test_publico_alvo_junta_etapa_e_descricao(curso_cheio):
    """A descricao virou complemento da etapa, e escolher so uma escondia a outra:
    era o que fazia a previa parecer incompleta."""
    assert "5º ano do Ensino Fundamental" in curso_cheio.publico_alvo
    assert "Turmas da escola do campo" in curso_cheio.publico_alvo


@pytest.mark.django_db
def test_previa_de_curso_vazio_nao_imprime_none(client, dados_curso, professor):
    """A previa existe para curso incompleto, entao ela precisa aguentar campo
    vazio: "None horas" foi o mesmo defeito que a pagina do curso ja teve."""
    from apps.cursos import services

    dados_curso.update(carga_horaria=None, formato="", resumo="", palavras_chave="")
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    html = client.get(reverse("previa_do_curso", args=[curso.pk])).content.decode()
    assert "None" not in html
