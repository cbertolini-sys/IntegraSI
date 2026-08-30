"""Versoes de um curso (Plano 4, Task 5).

As regras que este arquivo prende, na ordem em que aparecem:

 1. A v1 e a raiz da linhagem: `versao == 1`, `raiz is None`, `linhagem_id == pk`.
 2. `abrir_nova_versao` clona dados do curso, os cinco entregaveis, as secoes e o
    conteudo delas.
 3. A nova versao nasce RASCUNHO, e todos os entregaveis clonados voltam a
    RASCUNHO (spec 4.5).
 4. A nova versao aponta para a raiz da linhagem e recebe `versao` = ultima + 1.
 5. O motivo informado fica gravado em `motivo_versao` da nova versao.
 6. Motivo em branco e recusado (spec 4.5: obrigatorio a partir da v2).
 7. So se abre nova versao de curso PUBLICADO - e isso inclui recusar
    DESPUBLICADO e SUBSTITUIDO, que escapam da trava da regra 9 (a "versao em
    producao") e so sao barrados por esta.
 8. So o coordenador ou o professor responsavel abre versao, e a recusa vem
    DESTA guarda: `definir_temas`, la dentro da clonagem, tambem levanta
    PermissionDenied para os mesmos usuarios, entao os testes conferem a
    mensagem - sem isso a guarda de entrada podia ser apagada inteira sem
    quebrar nada.
 9. Uma versao em producao por linhagem: duas equipes nao reescrevem o mesmo
    curso em paralelo (spec 4.5).
10. Os anexos clonados apontam para o MESMO `Arquivo`: clonar curso nao clona
    bytes (spec 4.6).
11. Anexo preso a uma secao fica preso a secao CLONADA, nunca a da versao velha.
12. O historico de `Revisao` nao e copiado: pertence a versao que o produziu.
13. A equipe NAO e clonada: a nova versao e produzida por outra equipe, que o
    professor monta (spec 4.5, passo 3).
14. A nova versao nasce na edicao corrente; sem edicao corrente, herda a do
    curso de origem.
15. Temas e competencias vao junto, e o vetor de temas e reindexado - senao a
    nova versao fica invisivel para a busca (spec 4.4).
16. A versao anterior continua PUBLICADO durante todo o trabalho (spec 4.5).
17. Publicar a nova move a anterior para SUBSTITUIDO, com log da transicao.
18. Publicar a nova substitui tambem uma versao anterior DESPUBLICADA: ser
    superada e fato da linhagem, nao do estado do catalogo naquele instante.
19. Por causa de 18, uma versao velha nao volta ao ar depois que a nova
    publicou - SUBSTITUIDO e terminal (spec 5).
20. Republicar um curso despublicado nao atropela uma versao da mesma linhagem
    que esteja em producao - nem marca o proprio curso republicado como
    SUBSTITUIDO no caminho.
21. A abertura da versao fica no LogTransicaoCurso.
22. O banco recusa duas versoes PUBLICADO na mesma linhagem (defesa em
    profundidade da invariante que faz o catalogo dispensar DISTINCT ON), e nao
    atrapalha duas linhagens diferentes publicadas ao mesmo tempo - nem a
    substituicao, que so alcanca a propria linhagem.
24. A raiz de uma linhagem nao pode ser apagada enquanto houver versao
    apontando para ela (`raiz` e PROTECT): apagar a v1 em cascata levaria a
    historia inteira do curso junto, em silencio.
23. Depois que a substituicao acontece, o material da v1 continua acessivel a
    quem a produziu e a coordenacao; a equipe NOVA chega ao mesmo arquivo pela
    propria versao, e nao pela versao substituida; quem nao tem vinculo com
    nenhuma das duas continua de fora.

A regra "SUBSTITUIDO fica fora das duas portas do catalogo" mora em
`apps/catalogo/tests/test_catalogo.py` (matriz de visibilidade), e "SUBSTITUIDO
nao e republicavel" em `test_publicacao.py`, junto das outras guardas de
publicacao.
"""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.urls import reverse

from apps.cursos import services
from apps.cursos.busca import buscar
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo, Arquivo, Curso, LogTransicaoCurso, Tema


def _publica(curso, membro, professor, coordenador):
    """Leva um curso de RASCUNHO ate PUBLICADO pelos services de verdade."""
    services.adicionar_membro(curso, membro, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    curso.refresh_from_db()
    return curso


@pytest.fixture
def curso_publicado(dados_curso, aluno, professor, coordenador, arquivo_qualquer):
    curso = services.criar_curso(**dados_curso)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa da primeira versao</p>"
    secao.save()
    return _publica(curso, aluno, professor, coordenador)


# --- Regras 1 a 5: a linhagem e o que a clonagem copia ---------------------


@pytest.mark.django_db
def test_primeira_versao_e_a_raiz(curso_publicado):
    assert curso_publicado.versao == 1
    assert curso_publicado.raiz is None
    assert curso_publicado.linhagem_id == curso_publicado.pk


@pytest.mark.django_db
def test_nova_versao_clona_conteudo_e_zera_os_estados(curso_publicado, coordenador):
    nova = services.abrir_nova_versao(
        curso_publicado, por=coordenador, motivo="Faltam atividades praticas."
    )
    assert nova.pk != curso_publicado.pk
    assert nova.titulo == curso_publicado.titulo
    assert nova.versao == 2
    assert nova.raiz_id == curso_publicado.pk
    assert nova.linhagem_id == curso_publicado.pk
    assert nova.status == StatusCurso.RASCUNHO
    assert nova.entregaveis.count() == 5
    assert set(nova.entregaveis.values_list("status", flat=True)) == {StatusEntregavel.RASCUNHO}
    plano = nova.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    assert plano.secoes.count() == 7
    assert "primeira versao" in plano.secoes.first().conteudo


@pytest.mark.django_db
def test_motivo_fica_gravado_na_nova_versao(curso_publicado, coordenador):
    """Sem isto, `motivo_versao` seria um campo que so serve para ser exigido e
    jogado fora: quem le a linhagem depois precisa saber por que a versao nasceu
    (spec 4.5)."""
    nova = services.abrir_nova_versao(
        curso_publicado, por=coordenador, motivo="Faltam atividades praticas."
    )
    nova.refresh_from_db()
    assert nova.motivo_versao == "Faltam atividades praticas."


@pytest.mark.django_db
def test_terceira_versao_continua_na_mesma_linhagem(
    curso_publicado, coordenador, professor, outro_aluno
):
    segunda = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Segunda.")
    _publica(segunda, outro_aluno, professor, coordenador)
    terceira = services.abrir_nova_versao(segunda, por=coordenador, motivo="Terceira.")
    assert terceira.versao == 3
    assert terceira.raiz_id == curso_publicado.pk
    assert terceira.linhagem_id == curso_publicado.pk


# --- Regras 10 e 11: arquivos compartilhados e anexos nas secoes -----------


@pytest.mark.django_db
def test_nova_versao_compartilha_o_arquivo_em_disco(curso_publicado, coordenador):
    antes = Arquivo.objects.count()
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Melhorar os slides.")
    assert Arquivo.objects.count() == antes
    original = curso_publicado.entregaveis.get(tipo=TipoEntregavel.SLIDES).anexos.first()
    copia = nova.entregaveis.get(tipo=TipoEntregavel.SLIDES).anexos.first()
    assert copia.pk != original.pk
    assert copia.arquivo_id == original.arquivo_id
    assert copia.titulo == original.titulo


@pytest.mark.django_db
def test_anexo_de_secao_aponta_para_a_secao_clonada(curso_publicado, coordenador, aluno, arquivo_qualquer):
    """Um anexo preso a uma secao nao pode continuar preso a secao da versao
    velha: editar a v2 mexeria no material da v1, e apagar a v2 arrastaria o
    anexo por CASCADE. Copiar sem mapear a secao (deixando None) tambem perde a
    ligacao que a spec 4.5 manda clonar."""
    plano = curso_publicado.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    Anexo.objects.create(
        entregavel=plano, secao=secao, tipo_midia=TipoMidia.ARQUIVO, titulo="Plano em PDF",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )

    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")

    copia = nova.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO).anexos.get()
    assert copia.secao_id is not None
    assert copia.secao_id != secao.pk
    assert copia.secao.entregavel.curso_id == nova.pk
    assert copia.secao.titulo == secao.titulo


# --- Regras 12 e 13: o que NAO e copiado ----------------------------------


@pytest.mark.django_db
def test_historico_de_revisao_nao_e_copiado(curso_publicado, coordenador, professor):
    from apps.cursos.models import Revisao

    slides = curso_publicado.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Revisao.objects.create(entregavel=slides, revisor=professor, decisao=Revisao.APROVADO)

    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")

    assert Revisao.objects.filter(entregavel__curso=nova).count() == 0
    assert Revisao.objects.filter(entregavel__curso=curso_publicado).count() == 1


@pytest.mark.django_db
def test_equipe_nao_e_clonada(curso_publicado, coordenador, aluno):
    """Spec 4.5, passo 3: "O professor monta a nova equipe. Pode ser outra turma
    inteira." Clonar os membros pareceria gentileza e daria a alunos de outro
    semestre acesso de edicao a um curso que eles nao vao produzir - e faria a
    nova versao nascer sem que ninguem precisasse assumi-la."""
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Outra equipe.")

    assert curso_publicado.membros.count() == 1
    assert nova.membros.count() == 0
    assert nova.tem_membro(aluno) is False


# --- Regra 14: a edicao da nova versao ------------------------------------


@pytest.mark.django_db
def test_nova_versao_nasce_na_edicao_corrente(curso_publicado, coordenador, edicao):
    """Outro semestre, outra equipe (spec 4.5): a versao nova pertence a edicao
    em andamento, nao a edicao em que a versao velha foi produzida."""
    import datetime

    from apps.edicoes.models import Edicao

    edicao.ativa = False
    edicao.save()
    corrente = Edicao.objects.create(
        codigo="2027/1", descricao="Nova edicao", data_inicio=datetime.date(2027, 3, 1),
        data_fim=datetime.date(2027, 7, 20), ativa=True,
    )

    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")

    assert nova.edicao_id == corrente.pk
    assert curso_publicado.edicao_id == edicao.pk


@pytest.mark.django_db
def test_sem_edicao_corrente_a_nova_versao_herda_a_do_curso(curso_publicado, coordenador, edicao):
    """`edicao` e obrigatorio no Curso: se o coordenador ainda nao abriu a
    proxima edicao, abrir versao nao pode estourar com IntegrityError."""
    edicao.ativa = False
    edicao.save()

    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")

    assert nova.edicao_id == edicao.pk


# --- Regra 15: temas, competencias e reindexacao --------------------------


@pytest.mark.django_db
def test_temas_e_competencias_vao_para_a_nova_versao(dados_curso, aluno, professor, coordenador):
    from apps.referenciais.models import Categoria, Competencia, Referencial

    referencial = Referencial.objects.create(
        nome="BNCC da Computacao", sigla="BNCC-COMP", min_competencias=1, max_competencias=5
    )
    categoria = Categoria.objects.create(referencial=referencial, nome="Mundo Digital", ordem=1)
    competencia = Competencia.objects.create(
        referencial=referencial, categoria=categoria, codigo="EF05CO01",
        descricao="Descricao", etapa="EF05", ordem=1,
    )
    tema = Tema.objects.create(nome="Robótica Educacional", slug="robotica-educacional")
    curso = services.criar_curso(**{**dados_curso, "referencial": referencial})
    curso.competencias.add(competencia)
    services.definir_temas(curso, [tema], por=professor)
    _publica(curso, aluno, professor, coordenador)

    nova = services.abrir_nova_versao(curso, por=coordenador, motivo="Atualizar.")

    assert list(nova.temas.all()) == [tema]
    assert list(nova.competencias.all()) == [competencia]
    assert nova.referencial_id == referencial.pk


@pytest.mark.django_db
def test_nova_versao_e_encontrada_pela_busca_no_nome_do_tema(
    dados_curso, aluno, professor, coordenador
):
    """Coluna gerada nao alcanca M2M (spec 4.4): quem copia os temas precisa
    reindexar `vetor_temas`, ou a nova versao some da busca por tema - foi
    exatamente esse o CRITICAL do Plano 2."""
    tema = Tema.objects.create(nome="Robótica Educacional", slug="robotica-educacional")
    curso = services.criar_curso(**dados_curso)
    services.definir_temas(curso, [tema], por=professor)
    _publica(curso, aluno, professor, coordenador)

    nova = services.abrir_nova_versao(curso, por=coordenador, motivo="Atualizar.")

    assert buscar(Curso.objects.filter(pk=nova.pk), "robotica").exists()


# --- Regras 6 a 9: as guardas de abertura ---------------------------------


@pytest.mark.django_db
def test_motivo_e_obrigatorio(curso_publicado, coordenador):
    with pytest.raises(ValidationError):
        services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="  ")
    assert Curso.objects.count() == 1


@pytest.mark.django_db
def test_so_se_abre_versao_de_curso_publicado(dados_curso, coordenador):
    """Um curso ainda em producao e recusado - mas por DUAS guardas ao mesmo
    tempo (a de status e a de "ja existe versao em producao", que enxerga o
    proprio curso em RASCUNHO). Os dois testes abaixo isolam a guarda de status
    com entradas que a trava de producao deixa passar."""
    curso = services.criar_curso(**dados_curso)
    with pytest.raises(ValidationError):
        services.abrir_nova_versao(curso, por=coordenador, motivo="Ainda nao publicado.")


@pytest.mark.django_db
def test_nao_se_abre_versao_de_curso_despublicado(curso_publicado, coordenador):
    """DESPUBLICADO esta fora da trava de "versao em producao" - de proposito,
    pela regra 20. Entao quem recusa aqui e so a guarda de status, sozinha: sem
    ela, despublicar um curso viraria um atalho para clonar o que a spec 4.5 so
    autoriza clonar a partir do catalogo."""
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Erro na ementa.")

    with pytest.raises(ValidationError):
        services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Aproveitar.")

    assert Curso.objects.count() == 1


@pytest.mark.django_db
def test_nao_se_abre_versao_de_versao_ja_substituida(
    curso_publicado, coordenador, professor, outro_aluno
):
    """SUBSTITUIDO tambem escapa da trava de producao: na linhagem inteira, a v1
    esta SUBSTITUIDO e a v2 PUBLICADO, e nenhuma das duas conta como "em
    producao". Sem a guarda de status, a v1 morta geraria uma v3 - duas versoes
    vivas na mesma linhagem, cada uma partindo de um ponto da historia."""
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    _publica(nova, outro_aluno, professor, coordenador)
    curso_publicado.refresh_from_db()

    with pytest.raises(ValidationError):
        services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Ressuscitar a v1.")

    assert Curso.objects.count() == 2


@pytest.mark.django_db
def test_aluno_nao_abre_versao(curso_publicado, aluno):
    """Confere a MENSAGEM, e nao so o tipo da excecao: `definir_temas`, chamado
    la dentro da clonagem, tambem levanta PermissionDenied para um aluno
    ("Curso de outro professor."). Um `pytest.raises(PermissionDenied)` pelado
    passaria verde com a guarda de entrada apagada - o curso seria criado, os
    cinco entregaveis tambem, e so no fim a transacao voltaria atras com o erro
    errado na tela."""
    with pytest.raises(PermissionDenied, match="abre nova versão"):
        services.abrir_nova_versao(curso_publicado, por=aluno, motivo="Quero mexer.")

    assert Curso.objects.count() == 1


@pytest.mark.django_db
def test_outro_professor_nao_abre_versao(curso_publicado, outro_professor):
    """Mesmo motivo do teste acima. Aqui a mensagem prende tambem a metade
    `e_responsavel` de `pode_abrir_versao`: um `pode_abrir_versao` que
    devolvesse True para qualquer professor cairia no PermissionDenied de
    `definir_temas`, com outra mensagem, e um teste sem `match` nao veria
    diferenca."""
    with pytest.raises(PermissionDenied, match="abre nova versão"):
        services.abrir_nova_versao(curso_publicado, por=outro_professor, motivo="Quero mexer.")

    assert Curso.objects.count() == 1


@pytest.mark.django_db
def test_professor_responsavel_abre_versao(curso_publicado, professor):
    nova = services.abrir_nova_versao(
        curso_publicado, por=professor, motivo="Atualizar bibliografia."
    )
    assert nova.versao == 2


@pytest.mark.django_db
def test_duas_versoes_em_producao_ao_mesmo_tempo_sao_recusadas(curso_publicado, coordenador):
    services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Primeira tentativa.")
    with pytest.raises(ValidationError):
        services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Segunda tentativa.")
    assert Curso.objects.count() == 2


@pytest.mark.django_db
def test_publicada_a_nova_a_linhagem_aceita_outra_versao(
    curso_publicado, coordenador, professor, outro_aluno
):
    """O contraponto do teste acima: a trava e "em producao", nao "ja houve uma
    segunda versao" - senao uma linhagem so poderia ser revisada uma vez."""
    segunda = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Segunda.")
    _publica(segunda, outro_aluno, professor, coordenador)

    terceira = services.abrir_nova_versao(segunda, por=coordenador, motivo="Terceira.")

    assert terceira.versao == 3


# --- Regras 16, 17 e 21: publicar a nova, substituir a velha --------------


@pytest.mark.django_db
def test_versao_anterior_continua_publicada_durante_o_trabalho(curso_publicado, coordenador):
    services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    curso_publicado.refresh_from_db()
    assert curso_publicado.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_publicar_a_nova_substitui_a_anterior(
    curso_publicado, coordenador, professor, outro_aluno
):
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    _publica(nova, outro_aluno, professor, coordenador)

    curso_publicado.refresh_from_db()
    nova.refresh_from_db()
    assert nova.status == StatusCurso.PUBLICADO
    assert curso_publicado.status == StatusCurso.SUBSTITUIDO


@pytest.mark.django_db
def test_substituicao_fica_no_historico(curso_publicado, coordenador, professor, outro_aluno):
    """Toda mudanca de situacao passa pelo _transicionar e grava log (spec 11):
    um `.update()` na versao velha economizaria uma linha e deixaria buraco no
    historico administrativo."""
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    _publica(nova, outro_aluno, professor, coordenador)

    log = LogTransicaoCurso.objects.get(
        curso=curso_publicado, para_status=StatusCurso.SUBSTITUIDO
    )
    assert log.de_status == StatusCurso.PUBLICADO
    assert log.usuario == coordenador
    assert "2" in log.observacao


@pytest.mark.django_db
def test_abertura_de_versao_fica_no_historico(curso_publicado, coordenador):
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Faltam praticas.")

    log = LogTransicaoCurso.objects.get(curso=nova)
    assert log.usuario == coordenador
    assert "Faltam praticas." in log.observacao


# --- Regras 18, 19 e 20: substituicao x despublicacao ---------------------


@pytest.mark.django_db
def test_publicar_a_nova_substitui_ate_a_anterior_despublicada(
    curso_publicado, coordenador, professor, outro_aluno
):
    """Ser superada e fato da linhagem, nao do estado do catalogo no instante em
    que a nova publica. Se a v1 estivesse apenas despublicada e continuasse
    despublicada, ela seguiria republicavel para sempre (spec 5: DESPUBLICADO
    "pode ser republicado") e voltaria ao catalogo ao lado da v2 - dois cursos
    iguais, a invariante de uma versao publicada por linhagem no chao."""
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Erro na ementa.")

    _publica(nova, outro_aluno, professor, coordenador)

    curso_publicado.refresh_from_db()
    assert curso_publicado.status == StatusCurso.SUBSTITUIDO


@pytest.mark.django_db
def test_versao_velha_despublicada_nao_volta_ao_ar_depois_que_a_nova_publicou(
    curso_publicado, coordenador, professor, outro_aluno
):
    """O par que o Plano 3 abriu sem querer ao deixar publicar_curso aceitar
    DESPUBLICADO como origem: republicar a v1 enquanto a v2 esta no ar poria a
    versao VELHA substituindo a NOVA - a seta de spec 5 aponta so num sentido
    ("nova v PUBLICADO ==> versao anterior vira SUBSTITUIDO"). A recusa vem de a
    v1 ja ser terminal."""
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Erro na ementa.")
    _publica(nova, outro_aluno, professor, coordenador)
    curso_publicado.refresh_from_db()

    with pytest.raises(ValidationError):
        services.publicar_curso(curso_publicado, por=coordenador)

    curso_publicado.refresh_from_db()
    nova.refresh_from_db()
    assert curso_publicado.status == StatusCurso.SUBSTITUIDO
    assert nova.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_republicar_nao_atropela_a_versao_em_producao(curso_publicado, coordenador):
    """A substituicao alcanca versoes que estiveram no catalogo (PUBLICADO ou
    DESPUBLICADO), nunca uma que esta sendo produzida: matar a v2 em RASCUNHO
    jogaria fora o trabalho da equipe nova e ainda a deixaria terminal."""
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Erro na ementa.")

    services.publicar_curso(curso_publicado, por=coordenador)

    nova.refresh_from_db()
    curso_publicado.refresh_from_db()
    assert nova.status == StatusCurso.RASCUNHO
    assert curso_publicado.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_republicar_nao_substitui_o_proprio_curso(curso_publicado, coordenador):
    """Na republicacao o curso chega a `_substituir_versoes_anteriores` com
    status DESPUBLICADO - ou seja, ele se encaixa no proprio filtro. Sem o
    `.exclude(pk=curso.pk)`, ele se marcaria SUBSTITUIDO antes de se publicar: o
    status final sairia certo, e o LogTransicaoCurso ficaria com um "substituido
    pela versao 1" que nunca aconteceu. O historico da spec 11 e o unico lugar
    onde essa mentira apareceria, seis meses depois."""
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Erro na ementa.")

    services.publicar_curso(curso_publicado, por=coordenador)

    curso_publicado.refresh_from_db()
    assert curso_publicado.status == StatusCurso.PUBLICADO
    assert not LogTransicaoCurso.objects.filter(
        curso=curso_publicado, para_status=StatusCurso.SUBSTITUIDO
    ).exists()


# --- Regra 22: a invariante tambem no banco -------------------------------


@pytest.mark.django_db
def test_banco_recusa_duas_versoes_publicadas_na_mesma_linhagem(curso_publicado, coordenador):
    """Defesa em profundidade. Hoje so `services.publicar_curso` escreve status,
    e o laco de substituicao mantem a invariante; a constraint existe para o dia
    em que um comando, uma migracao de dados ou um `.update()` esquecer o laco -
    o catalogo mostrando o mesmo curso duas vezes e falha silenciosa.

    Escreve por `.update()` de proposito: e justamente o caminho que nao passa
    por service nenhum."""
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Curso.objects.filter(pk=nova.pk).update(status=StatusCurso.PUBLICADO)


@pytest.mark.django_db
def test_banco_aceita_duas_linhagens_publicadas_ao_mesmo_tempo(
    dados_curso, aluno, outro_aluno, professor, coordenador
):
    """O contraponto: a chave da constraint e a linhagem, nao o status. Uma
    constraint desatenta (unica por status, ou por `raiz` cru - que e NULL na v1)
    ou fecharia o catalogo inteiro ou nao fecharia nada.

    O `refresh_from_db` no fim nao e cerimonia: sem ele o teste lia o status que
    `_publica` deixou em memoria antes da segunda publicacao, e uma substituicao
    que perdesse o recorte de linhagem (varrendo todo curso publicado, e nao so
    a linhagem do que esta publicando) passaria despercebida bem aqui, no teste
    escrito para isso."""
    primeiro = _publica(services.criar_curso(**dados_curso), aluno, professor, coordenador)
    segundo = _publica(
        services.criar_curso(**{**dados_curso, "titulo": "Outro curso"}),
        outro_aluno, professor, coordenador,
    )

    primeiro.refresh_from_db()
    segundo.refresh_from_db()
    assert primeiro.status == StatusCurso.PUBLICADO
    assert segundo.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_nao_se_apaga_a_raiz_de_uma_linhagem(curso_publicado, coordenador):
    """`raiz` e PROTECT (regra 24). Com CASCADE, apagar a v1 - uma linha so, no
    Admin ou num shell - levaria junto todas as versoes seguintes, com os
    entregaveis, as secoes e os anexos delas, sem nenhum aviso. PROTECT
    transforma isso num erro na cara de quem tentou."""
    services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")

    with pytest.raises(ProtectedError):
        curso_publicado.delete()

    assert Curso.objects.count() == 2


# --- Regra 23: quem alcanca o material da versao substituida --------------


@pytest.fixture
def linhagem_substituida(curso_publicado, coordenador, professor, outro_aluno):
    """v1 publicada e substituida pela v2, produzida por outra equipe."""
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    _publica(nova, outro_aluno, professor, coordenador)
    curso_publicado.refresh_from_db()
    return curso_publicado, nova


@pytest.fixture
def url_do_material(curso_publicado):
    anexo = curso_publicado.entregaveis.get(tipo=TipoEntregavel.SLIDES).anexos.get()
    return reverse("baixar", args=[anexo.arquivo.identificador])


@pytest.mark.django_db
def test_equipe_antiga_continua_baixando_o_material_da_versao_substituida(
    client, settings, linhagem_substituida, url_do_material, aluno
):
    """SUBSTITUIDO "permanece consultavel como historico" (spec 4.5): quem
    produziu aquele material continua alcancando-o. Substituicao e fato do
    catalogo, nao revogacao de acesso de quem fez o trabalho."""
    settings.USAR_X_ACCEL = True
    client.force_login(aluno)

    assert client.get(url_do_material).status_code == 200


@pytest.mark.django_db
def test_equipe_nova_baixa_o_material_pela_propria_versao(
    client, settings, linhagem_substituida, url_do_material, outro_aluno
):
    """A equipe nova nao e membro da v1: ela chega ao mesmo `Arquivo` pelo anexo
    clonado na v2. E por isso que `pode_baixar_arquivo` pergunta por ALGUM curso
    e nao pelo primeiro anexo (Task 4)."""
    settings.USAR_X_ACCEL = True
    client.force_login(outro_aluno)

    assert client.get(url_do_material).status_code == 200


@pytest.mark.django_db
def test_equipe_nova_nao_enxerga_a_versao_substituida(linhagem_substituida, outro_aluno):
    """O acesso da equipe nova vem da v2, nunca da v1: se ela perder o anexo na
    v2, perde o arquivo junto. Sem este teste, "a equipe nova baixa" passaria
    tambem se a substituicao tivesse aberto a v1 inteira para ela."""
    from apps.cursos import permissions

    velha, _ = linhagem_substituida

    assert permissions.pode_ver_curso(outro_aluno, velha) is False


@pytest.mark.django_db
def test_quem_nao_produziu_nenhuma_das_versoes_nao_baixa(
    client, settings, linhagem_substituida, url_do_material, outro_professor
):
    settings.USAR_X_ACCEL = True
    client.force_login(outro_professor)

    assert client.get(url_do_material).status_code == 403


@pytest.mark.django_db
def test_coordenacao_alcanca_o_material_da_versao_substituida(
    client, settings, linhagem_substituida, url_do_material, coordenador
):
    settings.USAR_X_ACCEL = True
    client.force_login(coordenador)

    assert client.get(url_do_material).status_code == 200
