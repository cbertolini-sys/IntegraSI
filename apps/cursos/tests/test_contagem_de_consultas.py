"""As telas de lista nao podem consultar o banco uma vez por linha.

Nao havia um unico teste de contagem de consultas no projeto. Os
`select_related` e `prefetch_related` das telas mais pesadas estao escritos com
cuidado, alguns com comentario dizendo qual N+1 evitam. Mas apagar qualquer um
deles deixa a suite inteira verde: a tela continua CORRETA, so fica lenta, e
ninguem percebe ate a base crescer.

**A afirmacao aqui nao e sobre um numero, e sim sobre a forma da curva.** Cada
teste mede a mesma tela com poucas linhas e com muitas, e exige que o numero de
consultas seja o MESMO. Essa e a invariante de verdade: consulta por linha e o
defeito, e o total absoluto e detalhe de implementacao.

Prender um numero exato tambem funcionaria, e seria pior. Ele quebra a cada
melhoria legitima, vira ruido, e um teste que reprova o certo e o primeiro a ser
desligado. Com a comparacao, uma otimizacao futura passa verde e um N+1 novo
reprova, que e exatamente o que se quer.

O aquecimento antes da primeira medicao nao e detalhe: a primeira requisicao de
uma sessao busca tipos de conteudo e a propria sessao, e sem ele as duas medidas
diferem por um motivo que nada tem a ver com N+1.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import Rotulo, StatusCurso, TipoMidia, TipoPratica
from apps.cursos.models import Anexo, Arquivo, Curso


def consultas(client, url):
    with CaptureQueriesContext(connection) as capturadas:
        resposta = client.get(url)
    assert resposta.status_code == 200, resposta.status_code
    return len(capturadas)


def cursos_na_situacao(dados_curso, professor, quantos, status, desde=0):
    """Cria cursos prontos, direto na situacao pedida.

    `update()` em vez de percorrer o ciclo pelos servicos: o assunto deste arquivo
    e a renderizacao da lista, e submeter seis entregaveis por curso, seis vezes,
    so tornaria o teste lento sem medir nada a mais.
    """
    for i in range(desde, desde + quantos):
        dados = dict(dados_curso, titulo=f"Curso de demonstração {i}")
        services.criar_curso(**dados)
    Curso.objects.filter(status=StatusCurso.RASCUNHO).update(status=status)


# --- as duas listas da coordenacao -------------------------------------------


@pytest.mark.django_db
def test_a_fila_da_coordenacao_nao_consulta_por_curso(
    client, coordenador, professor, dados_curso, django_assert_num_queries
):
    """O template lê `curso.professor_responsavel.nome_completo` em cada linha."""
    client.force_login(coordenador)
    url = reverse("fila_coordenacao")
    cursos_na_situacao(dados_curso, professor, 2, StatusCurso.AGUARDANDO_COORDENADOR)

    client.get(url)  # aquecimento
    com_dois = consultas(client, url)

    cursos_na_situacao(dados_curso, professor, 4, StatusCurso.AGUARDANDO_COORDENADOR, desde=2)
    com_seis = consultas(client, url)

    assert Curso.objects.count() == 6, "o cenário não cresceu, então nada foi medido"
    assert com_seis == com_dois, (
        f"{com_dois} consultas com 2 cursos e {com_seis} com 6: "
        "a tela está consultando o banco uma vez por linha"
    )


@pytest.mark.django_db
def test_a_lista_do_catalogo_nao_consulta_por_curso(
    client, coordenador, professor, dados_curso
):
    client.force_login(coordenador)
    url = reverse("cursos_no_catalogo")
    cursos_na_situacao(dados_curso, professor, 2, StatusCurso.PUBLICADO)

    client.get(url)
    com_dois = consultas(client, url)

    cursos_na_situacao(dados_curso, professor, 4, StatusCurso.PUBLICADO, desde=2)
    com_seis = consultas(client, url)

    assert com_seis == com_dois, (
        f"{com_dois} consultas com 2 cursos e {com_seis} com 6"
    )


# --- a tela do curso, que a equipe mais abre ---------------------------------


def anexo_em(entregavel, por, numero):
    conteudo = f"material {numero}".encode()
    arquivo = Arquivo.objects.create(
        nome_original=f"material-{numero}.txt",
        tamanho=len(conteudo),
        mime="text/plain",
        hash_conteudo=f"{numero:064d}",
        enviado_por=por,
    )
    Anexo.objects.create(
        entregavel=entregavel,
        arquivo=arquivo,
        enviado_por=por,
        tipo_midia=TipoMidia.ARQUIVO,
        titulo=f"Material {numero}",
        rotulo=Rotulo.NENHUM,
        tipo_pratica=TipoPratica.NENHUM,
    )


@pytest.mark.django_db
def test_a_tela_do_curso_nao_consulta_por_anexo(client, dados_curso, professor, aluno):
    """`prefetch_related("entregaveis__anexos")`: o cartão de progresso roda
    `validacoes.pendencias` nos seis entregáveis, e a regra de cada um lê os
    anexos."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    plano = curso.entregaveis.first()
    client.force_login(professor)
    url = reverse("curso", args=[curso.pk])

    anexo_em(plano, professor, 1)
    client.get(url)
    com_um = consultas(client, url)

    for numero in range(2, 8):
        anexo_em(plano, professor, numero)
    com_sete = consultas(client, url)

    assert com_sete == com_um, (
        f"{com_um} consultas com 1 anexo e {com_sete} com 7"
    )


@pytest.mark.django_db
def test_a_tela_do_curso_nao_consulta_por_membro(
    client, dados_curso, professor, aluno, outro_aluno, outro_professor
):
    """`membros.select_related("pessoa")`: o template lê `membro.pessoa` em cada
    linha da equipe."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    client.force_login(professor)
    url = reverse("curso", args=[curso.pk])

    client.get(url)
    com_dois = consultas(client, url)

    services.adicionar_membro(curso, outro_aluno, por=professor)
    services.adicionar_membro(curso, outro_professor, por=professor)
    com_quatro = consultas(client, url)

    assert com_quatro == com_dois, (
        f"{com_dois} consultas com 2 membros e {com_quatro} com 4"
    )
