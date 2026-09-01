from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel


def test_os_seis_entregaveis_do_roteiro():
    """A ordem de declaracao E a ordem da tela: ORDEM_DO_ROTEIRO monta a ordenacao
    a partir dela. Por isso a assercao e por lista, e nao por conjunto."""
    assert [t.value for t in TipoEntregavel] == [
        "PLANO_ENSINO",
        "SLIDES",
        "VIDEOS",
        "CARDS",
        "CADERNO",
        "AVALIACAO",
    ]


def test_a_numeracao_vive_no_rotulo_e_nao_no_valor():
    """Renumerar mexeu no rotulo. Se algum dia mexer no valor, toda linha ja
    gravada vira lixo, e e regra do projeto nunca fazer isso."""
    for tipo in TipoEntregavel:
        assert tipo.label[0].isdigit()
        assert not tipo.value[0].isdigit()


def test_estados_do_entregavel():
    assert set(StatusEntregavel.values) == {"RASCUNHO", "EM_REVISAO", "APROVADO", "DEVOLVIDO"}


def test_estados_do_curso_incluem_substituido():
    assert "SUBSTITUIDO" in StatusCurso.values


def test_tema_continua_importavel_do_pacote_de_modelos():
    from apps.cursos.models import Tema

    assert Tema._meta.model_name == "tema"
