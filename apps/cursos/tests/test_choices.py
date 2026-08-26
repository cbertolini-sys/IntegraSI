from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel


def test_os_cinco_entregaveis_do_roteiro():
    assert [t.value for t in TipoEntregavel] == [
        "PLANO_ENSINO",
        "CARDS",
        "CADERNO",
        "VIDEOS",
        "SLIDES",
    ]


def test_estados_do_entregavel():
    assert set(StatusEntregavel.values) == {"RASCUNHO", "EM_REVISAO", "APROVADO", "DEVOLVIDO"}


def test_estados_do_curso_incluem_substituido():
    assert "SUBSTITUIDO" in StatusCurso.values


def test_tema_continua_importavel_do_pacote_de_modelos():
    from apps.cursos.models import Tema

    assert Tema._meta.model_name == "tema"
