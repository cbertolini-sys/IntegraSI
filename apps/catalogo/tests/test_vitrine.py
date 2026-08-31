"""O painel de "últimos cursos" no herói da página inicial.

É uma porta pública nova, e a regra mais dura do sistema se aplica a ela: nunca
mostrar curso que não esteja PUBLICADO (spec §10). Por isso ele passa pelo mesmo
`cursos_publicados()` que as outras três portas -- e não por uma consulta própria
que pudesse divergir.
"""

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel
from apps.cursos.models import Curso


@pytest.fixture
def curso_publicado(dados_curso, outro_aluno, professor, coordenador):
    """Definida aqui, e nao importada de test_catalogo.py: importar entre modulos
    de teste faz o segundo depender da ordem de coleta do primeiro."""
    return publica(services.criar_curso(**dados_curso), outro_aluno, professor, coordenador)


def publica(curso, aluno, professor, coordenador):
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    return curso


@pytest.mark.django_db
def test_a_vitrine_mostra_o_curso_publicado(client, curso_publicado):
    resposta = client.get(reverse("catalogo"))
    assert curso_publicado in resposta.context["vitrine"]


@pytest.mark.django_db
def test_a_vitrine_nunca_mostra_curso_nao_publicado(client, dados_curso):
    """A regra que importa. Um curso em produção não pode aparecer na primeira
    dobra da página pública."""
    rascunho = services.criar_curso(**dados_curso)
    resposta = client.get(reverse("catalogo"))
    assert rascunho not in resposta.context["vitrine"]
    assert rascunho.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_a_vitrine_para_em_dez(client, dados_curso, aluno, professor, coordenador):
    """Onze publicados, dez na vitrine: o corte é do servidor, não do CSS.
    Esconder o excedente com `overflow` mandaria os onze pelo fio."""
    for i in range(11):
        dados = dict(dados_curso, titulo=f"Curso {i:02d}")
        publica(services.criar_curso(**dados), aluno, professor, coordenador)
    vitrine = client.get(reverse("catalogo")).context["vitrine"]
    assert len(vitrine) == 10


@pytest.mark.django_db
def test_a_vitrine_traz_os_mais_recentes_primeiro(
    client, dados_curso, aluno, professor, coordenador
):
    """"Últimos inseridos": o mais novo abre o carrossel."""
    for i in range(3):
        dados = dict(dados_curso, titulo=f"Curso {i:02d}")
        publica(services.criar_curso(**dados), aluno, professor, coordenador)
    vitrine = list(client.get(reverse("catalogo")).context["vitrine"])
    assert [c.titulo for c in vitrine] == ["Curso 02", "Curso 01", "Curso 00"]


@pytest.mark.django_db
def test_a_vitrine_ignora_os_filtros_da_busca(client, curso_publicado):
    """O herói mostra a novidade do catálogo; a grade abaixo é que responde ao
    filtro. Sem isto, buscar "arduino" esvaziaria a primeira dobra da página."""
    resposta = client.get(reverse("catalogo"), {"q": "termo-que-nao-casa-com-nada"})
    assert list(resposta.context["cursos"]) == []
    assert curso_publicado in resposta.context["vitrine"]


@pytest.mark.django_db
def test_catalogo_vazio_nao_quebra(client, db):
    """Sem curso nenhum publicado, a página abre igual -- o carrossel some, o
    resto fica."""
    assert Curso.objects.filter(status=StatusCurso.PUBLICADO).count() == 0
    resposta = client.get(reverse("catalogo"))
    assert resposta.status_code == 200
    assert list(resposta.context["vitrine"]) == []


@pytest.mark.django_db
def test_o_curso_despublicado_sai_da_vitrine(client, curso_publicado, coordenador):
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Desatualizado.")
    resposta = client.get(reverse("catalogo"))
    assert curso_publicado not in resposta.context["vitrine"]


@pytest.mark.django_db
def test_a_pagina_carrega_o_script_do_carrossel(client, curso_publicado):
    """O carrossel e progressivo -- sem JS o primeiro cartao aparece igual --, mas
    o script precisa estar referenciado para o autoplay existir."""
    conteudo = client.get(reverse("catalogo")).content.decode()
    assert "js/vitrine.js" in conteudo
    assert "data-carrossel" in conteudo


@pytest.mark.django_db
def test_sem_javascript_o_primeiro_cartao_ja_aparece(client, curso_publicado):
    """A classe `ativo` sai do servidor no primeiro slide: quem tem JS bloqueado
    ainda ve um curso, e nao um bloco vazio."""
    conteudo = client.get(reverse("catalogo")).content.decode()
    assert 'class="vitrine-slide ativo"' in conteudo


@pytest.mark.django_db
def test_os_estaticos_saem_versionados(client, curso_publicado):
    """A folha de estilo e o script levam a versao na URL.

    Sem isto o navegador serve a folha antiga depois de uma alteracao -- o
    servidor de desenvolvimento manda Last-Modified sem Cache-Control, e o
    navegador cacheia por heuristica. Ja fez o carrossel aparecer sem estilo
    nenhum, com o CSS correto no servidor.
    """
    conteudo = client.get(reverse("catalogo")).content.decode()
    assert "css/integrasi.css?v=" in conteudo
    assert "js/vitrine.js?v=" in conteudo


@pytest.mark.django_db
def test_a_tag_de_formato_carrega_a_cor_do_valor(client, curso_publicado):
    """A cor da tag codifica informacao: PRESENCIAL, HIBRIDO e ONLINE se
    distinguem antes de serem lidos. A classe sai do proprio campo, entao um
    formato novo nao fica sem cor por esquecimento -- fica com a cor neutra."""
    conteudo = client.get(reverse("catalogo")).content.decode()
    assert 'class="marca-formato presencial"' in conteudo


@pytest.mark.django_db
def test_a_barra_nao_tem_mais_o_link_de_cursos(client):
    """Removido a pedido: o logo ja leva ao catalogo, e o botao Entrar fica
    sozinho no canto."""
    conteudo = client.get(reverse("catalogo")).content.decode()
    assert ">Cursos</a>" not in conteudo


@pytest.mark.django_db
def test_o_rodape_traz_as_duas_marcas(client):
    """IntegraSI e o brasao da UFSM, lado a lado, com o brasao apontando para a
    pagina da unidade universitaria de Frederico Westphalen."""
    conteudo = client.get(reverse("catalogo")).content.decode()
    assert "img/integrasi-completo.png" in conteudo
    assert "img/ufsm-brasao.svg" in conteudo
    assert "https://www.ufsm.br/unidades-universitarias/frederico-westphalen" in conteudo


@pytest.mark.django_db
def test_o_link_externo_do_rodape_nao_entrega_a_aba(client):
    """`target="_blank"` sem `rel="noopener"` da a pagina de destino acesso ao
    `window.opener`. Sao dois links externos no rodape e os dois precisam disso."""
    conteudo = client.get(reverse("catalogo")).content.decode()
    for trecho in conteudo.split("<a ")[1:]:
        cabeca = trecho.split(">")[0]
        if 'target="_blank"' in cabeca:
            assert "noopener" in cabeca, f"link externo sem noopener: {cabeca[:90]}"
