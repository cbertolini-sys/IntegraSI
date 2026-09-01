import pytest
from django.core.exceptions import PermissionDenied

from apps.cursos import permissions, services
from apps.cursos.choices import TipoEntregavel


@pytest.fixture
def curso_com_equipe(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso


@pytest.mark.django_db
def test_membro_ve_o_curso(curso_com_equipe, aluno):
    assert permissions.pode_ver_curso(aluno, curso_com_equipe)


@pytest.mark.django_db
def test_aluno_de_fora_nao_ve_o_curso(curso_com_equipe, outro_aluno):
    assert permissions.pode_ver_curso(outro_aluno, curso_com_equipe) is False


@pytest.mark.django_db
def test_professor_de_outro_curso_nao_ve(curso_com_equipe, outro_professor):
    assert permissions.pode_ver_curso(outro_professor, curso_com_equipe) is False


@pytest.mark.django_db
def test_coordenador_ve_tudo(curso_com_equipe, coordenador):
    assert permissions.pode_ver_curso(coordenador, curso_com_equipe)


@pytest.mark.django_db
def test_professor_responsavel_ve_o_curso(curso_com_equipe, professor):
    assert permissions.pode_ver_curso(professor, curso_com_equipe)


@pytest.mark.django_db
def test_aluno_de_fora_nao_edita_producao(curso_com_equipe, outro_aluno):
    """Metade nao coberta por test_entregavel_em_revisao_nao_e_editavel_nem_pelo_membro:
    aquele teste so passa membro da equipe para pode_editar_producao. Sem este teste,
    apagar o `return e_membro_da_equipe(...)` (por um `return True` incondicional) nao
    quebraria nada."""
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    assert slides.editavel
    assert permissions.pode_editar_producao(outro_aluno, slides) is False


@pytest.mark.django_db
def test_aluno_nao_revisa(curso_com_equipe, aluno):
    assert permissions.pode_revisar(aluno, curso_com_equipe) is False


@pytest.mark.django_db
def test_professor_responsavel_revisa(curso_com_equipe, professor):
    assert permissions.pode_revisar(professor, curso_com_equipe)


@pytest.mark.django_db
def test_pode_revisar_e_independente_de_pode_gerir_equipe(curso_com_equipe, professor, monkeypatch):
    """pode_revisar era um alias puro de pode_gerir_equipe: as duas regras da spec
    sao independentes (quem monta equipe x quem aprova entregavel), mesmo que hoje
    coincidam. Se o Plano 3 mudar quem monta equipe, isso nao pode arrastar quem
    revisa so porque uma funcao chamava a outra por baixo (item 7 da revisao de
    branco). Troca pode_gerir_equipe por uma versao que recusa todo mundo e confere
    que pode_revisar nao sente nada."""
    monkeypatch.setattr(permissions, "pode_gerir_equipe", lambda usuario, curso: False)
    assert permissions.pode_revisar(professor, curso_com_equipe) is True


@pytest.mark.django_db
def test_aluno_de_fora_nao_envia_para_revisao(curso_com_equipe, outro_aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    with pytest.raises(PermissionDenied) as erro:
        services.enviar_para_revisao(slides, por=outro_aluno)
    assert str(erro.value) == "Você não participa da equipe deste curso."


@pytest.mark.django_db
def test_aluno_nao_aprova_o_proprio_entregavel(curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    with pytest.raises(PermissionDenied) as erro:
        services.aprovar_entregavel(slides, por=aluno)
    assert str(erro.value) == "Somente o professor responsável revisa."


@pytest.mark.django_db
def test_aluno_nao_devolve_o_proprio_entregavel(curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    with pytest.raises(PermissionDenied):
        services.devolver_entregavel(slides, por=aluno, comentario="Corrija algo.")


@pytest.mark.django_db
def test_aluno_nao_monta_equipe(curso_com_equipe, aluno, outro_aluno):
    with pytest.raises(PermissionDenied) as erro:
        services.adicionar_membro(curso_com_equipe, outro_aluno, por=aluno)
    assert str(erro.value) == "Somente o professor responsável monta a equipe."


@pytest.mark.django_db
def test_entregavel_em_revisao_nao_e_editavel_nem_pelo_membro(curso_com_equipe, aluno, arquivo_qualquer):
    from apps.cursos.choices import TipoMidia
    from apps.cursos.models import Anexo

    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    assert permissions.pode_editar_producao(aluno, slides)
    services.enviar_para_revisao(slides, por=aluno)
    assert permissions.pode_editar_producao(aluno, slides) is False


@pytest.mark.django_db
def test_aluno_de_fora_recebe_permission_denied_nao_estado_do_entregavel(curso_com_equipe, outro_aluno):
    """Propriedade de seguranca (nao so estilo): a checagem de permissao em
    enviar_para_revisao precisa vir antes da checagem de editavel. Invertida,
    um aluno de fora que chuta um id de entregavel em EM_REVISAO receberia um
    ValidationError contando o estado do entregavel - vazando a existencia e a
    situacao de um curso que ele nem deveria enxergar - em vez de ser barrado
    por PermissionDenied sem informacao nenhuma."""
    from apps.cursos.choices import StatusEntregavel

    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    slides.status = StatusEntregavel.EM_REVISAO
    slides.save(update_fields=["status"])

    with pytest.raises(PermissionDenied):
        services.enviar_para_revisao(slides, por=outro_aluno)


@pytest.mark.django_db
def test_professor_nao_responsavel_nao_gerencia_equipe(curso_com_equipe, aluno):
    from apps.contas.models import Usuario

    outro_professor = Usuario.objects.create_user(
        email="outro.prof2@ufsm.br", nome_completo="Elisa Esteves", cpf="222.333.444-05",
        papel=Usuario.PROFESSOR, siape="8888888", password="senha-de-teste-123",
    )
    with pytest.raises(PermissionDenied):
        services.adicionar_membro(curso_com_equipe, aluno, por=outro_professor)


def _envia_slides_para_revisao(curso, aluno, arquivo_qualquer):
    from apps.cursos.choices import TipoMidia
    from apps.cursos.models import Anexo

    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    services.enviar_para_revisao(slides, por=aluno)
    return slides


@pytest.mark.django_db
def test_professor_nao_responsavel_nao_aprova(curso_com_equipe, aluno, arquivo_qualquer):
    from apps.contas.models import Usuario

    outro_professor = Usuario.objects.create_user(
        email="outro.prof3@ufsm.br", nome_completo="Elisa Esteves", cpf="555.666.777-20",
        papel=Usuario.PROFESSOR, siape="7777777", password="senha-de-teste-123",
    )
    slides = _envia_slides_para_revisao(curso_com_equipe, aluno, arquivo_qualquer)
    with pytest.raises(PermissionDenied):
        services.aprovar_entregavel(slides, por=outro_professor)


@pytest.mark.django_db
def test_professor_nao_responsavel_nao_devolve(curso_com_equipe, aluno, arquivo_qualquer):
    from apps.contas.models import Usuario

    outro_professor = Usuario.objects.create_user(
        email="outro.prof4@ufsm.br", nome_completo="Elisa Esteves", cpf="888.999.000-78",
        papel=Usuario.PROFESSOR, siape="6666666", password="senha-de-teste-123",
    )
    slides = _envia_slides_para_revisao(curso_com_equipe, aluno, arquivo_qualquer)
    with pytest.raises(PermissionDenied):
        services.devolver_entregavel(slides, por=outro_professor, comentario="Corrija algo.")


@pytest.mark.django_db
def test_coordenador_gerencia_equipe(curso_com_equipe, coordenador, outro_aluno):
    services.adicionar_membro(curso_com_equipe, outro_aluno, por=coordenador)
    assert curso_com_equipe.tem_membro(outro_aluno)


@pytest.mark.django_db
def test_coordenador_revisa(curso_com_equipe, coordenador, aluno, arquivo_qualquer):
    from apps.cursos.choices import StatusEntregavel

    slides = _envia_slides_para_revisao(curso_com_equipe, aluno, arquivo_qualquer)
    services.aprovar_entregavel(slides, por=coordenador)
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.APROVADO


@pytest.mark.django_db
def test_criar_curso_e_o_unico_servico_sem_checagem_propria_ate_aqui(dados_curso, aluno):
    """criar_curso confiava inteiramente no gate da view (Task 2 da revisao de
    branco): todo outro servico abre com permissions.garante(...). Um aluno chamando
    o servico direto - o que a view nunca deixaria acontecer, mas nada no servico
    impedia - precisa ser barrado aqui, nao so na view."""
    dados_curso["professor_responsavel"] = aluno
    with pytest.raises(PermissionDenied) as erro:
        services.criar_curso(**dados_curso)
    assert str(erro.value) == "Somente professor cria curso."


@pytest.mark.django_db
def test_coordenador_cria_curso_via_servico(dados_curso, coordenador):
    """Inverteu no Plano 5. Ate o Plano 4 este teste se chamava
    `test_coordenador_nao_cria_curso_via_servico` e prendia o oposto: coordenador
    nao criava curso, porque `e_professor` era `papel == PROFESSOR`.

    A regra 1 do Plano 5 diz que todo coordenador e tambem professor, e
    `pode_criar_curso` passou a valer para ele. Nao reverta isto achando que e
    regressao -- a mudanca foi deliberada, e esta registrada na spec 2.
    """
    dados_curso["professor_responsavel"] = coordenador
    curso = services.criar_curso(**dados_curso)
    assert curso.professor_responsavel == coordenador
    assert curso.entregaveis.count() == 6


@pytest.mark.django_db
def test_professor_cria_curso_via_servico(dados_curso):
    curso = services.criar_curso(**dados_curso)
    assert curso.pk is not None


@pytest.mark.django_db
def test_outro_aluno_e_outro_professor_convivem_num_mesmo_teste(outro_aluno, outro_professor):
    """111.444.777-35 era o CPF de outro_aluno E, hand-criado, de outro_professor em
    quatro lugares (test_permissions.py e tres vezes em test_views_professor.py).
    Nada falhava porque nenhum teste usava as duas fixtures juntas - o primeiro que
    precisasse de ambas colidiria em unicidade de CPF por um motivo que nada tem a
    ver com o que estaria sendo testado (item 10 da revisao de branco). Este teste e
    exatamente esse "primeiro caso": so pedir as duas fixtures juntas ja bastava
    para estourar ValidationError de unicidade antes da correcao."""
    assert outro_aluno.cpf != outro_professor.cpf


@pytest.mark.django_db
def test_coordenador_leva_o_proprio_curso_do_rascunho_ao_catalogo(
    dados_curso, coordenador, aluno
):
    """A combinacao que a heranca cria e que nenhum teste exercitava: a mesma
    pessoa e o professor responsavel E quem publica.

    Ate o Plano 4 isso era impossivel, entao o ciclo completo nunca foi percorrido
    por um so usuario. Se alguma guarda de publicacao supuser que o responsavel e
    o publicador sao pessoas diferentes -- por exemplo recusando que o coordenador
    aprove o proprio trabalho -- e aqui que aparece.
    """
    from apps.cursos.choices import StatusCurso, StatusEntregavel

    dados_curso["professor_responsavel"] = coordenador
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=coordenador)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()

    services.submeter_ao_coordenador(curso, por=coordenador)
    services.publicar_curso(curso, por=coordenador)

    curso.refresh_from_db()
    assert curso.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_professor_colaborador_ve_o_curso(curso, outro_professor):
    """Professor alocado na equipe de curso alheio enxerga o curso que produz."""
    from apps.cursos.models import MembroEquipe

    MembroEquipe.objects.create(curso=curso, pessoa=outro_professor)
    assert permissions.pode_ver_curso(outro_professor, curso) is True


@pytest.mark.django_db
def test_professor_de_fora_nao_ve_o_curso(curso, outro_professor):
    """Prende o outro lado: sem vinculo nenhum, professor nao entra em curso alheio."""
    assert permissions.pode_ver_curso(outro_professor, curso) is False
