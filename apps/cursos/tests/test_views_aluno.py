import hashlib
import os

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import Rotulo, StatusEntregavel, TipoEntregavel, TipoMidia, TipoPratica
from apps.cursos.models import Anexo, Arquivo


@pytest.fixture
def curso_com_equipe(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso


@pytest.mark.django_db
def test_meus_cursos_lista_so_os_do_aluno(client, curso_com_equipe, aluno, outro_aluno):
    client.force_login(outro_aluno)
    resposta = client.get(reverse("meus_cursos"))
    assert curso_com_equipe.titulo not in resposta.content.decode()
    client.force_login(aluno)
    resposta = client.get(reverse("meus_cursos"))
    assert curso_com_equipe.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_curso_de_outra_equipe_devolve_403(client, curso_com_equipe, outro_aluno):
    client.force_login(outro_aluno)
    resposta = client.get(reverse("curso", args=[curso_com_equipe.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_painel_do_curso_mostra_os_seis_entregaveis(client, curso_com_equipe, aluno):
    client.force_login(aluno)
    resposta = client.get(reverse("curso", args=[curso_com_equipe.pk]))
    conteudo = resposta.content.decode()
    assert conteudo.count("entregavel-card") == 6


@pytest.mark.django_db
def test_painel_do_curso_nao_cresce_uma_consulta_por_membro(
    client, curso_com_equipe, aluno, outro_aluno
):
    # curso.membros.all no template, sem select_related("aluno"), dispara uma
    # consulta a mais por membro so para ler membro.aluno.nome_completo -
    # fila_revisao.html ja faz isto certo (item 9 da revisao de branco). Em vez de
    # cravar um numero fixo de consultas (fragil a qualquer outra mudanca na tela),
    # confere que o numero de consultas nao muda ao adicionar um segundo membro.
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client.force_login(aluno)
    with CaptureQueriesContext(connection) as consultas_um_membro:
        client.get(reverse("curso", args=[curso_com_equipe.pk]))

    services.adicionar_membro(curso_com_equipe, outro_aluno, por=curso_com_equipe.professor_responsavel)

    with CaptureQueriesContext(connection) as consultas_dois_membros:
        client.get(reverse("curso", args=[curso_com_equipe.pk]))

    assert len(consultas_dois_membros) == len(consultas_um_membro)


@pytest.mark.django_db
def test_entregavel_mostra_o_que_falta(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.get(reverse("entregavel", args=[slides.pk]))
    assert "Anexe ao menos um arquivo de slides." in resposta.content.decode()


@pytest.mark.django_db
def test_entregavel_de_outra_equipe_devolve_403(client, curso_com_equipe, outro_aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(outro_aluno)
    resposta = client.get(reverse("entregavel", args=[slides.pk]))
    assert resposta.status_code == 403


def escrever_o_plano_inteiro(plano):
    """Preenche as sete secoes, para o plano poder ir a revisao.

    O envio passou a exigir TODAS as secoes escritas. Estes testes sao sobre o
    congelamento do entregavel em revisao, e nao sobre a regra do plano: sem este
    preparo eles falhariam por um motivo que nao e o que medem.
    """
    for secao in plano.secoes.all():
        secao.conteudo = f"<p>Conteúdo de {secao.titulo}.</p>"
        secao.save()


@pytest.mark.django_db
def test_anexar_em_entregavel_em_revisao_e_bloqueado(client, curso_com_equipe, aluno, arquivo_qualquer):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    escrever_o_plano_inteiro(plano)
    services.enviar_para_revisao(plano, por=aluno)
    client.force_login(aluno)
    resposta = client.post(reverse("anexar", args=[plano.pk]), {"titulo": "Outro", "url": "https://exemplo.org"})
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_salvar_secao_guarda_o_conteudo_e_o_autor(client, curso_com_equipe, aluno):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    client.force_login(aluno)
    resposta = client.post(reverse("salvar_secao", args=[secao.pk]), {"conteudo": "<p>Ementa nova</p>"})
    assert resposta.status_code == 200
    secao.refresh_from_db()
    assert "Ementa nova" in secao.conteudo
    assert secao.atualizado_por == aluno


@pytest.mark.django_db
def test_salvar_secao_mostra_o_erro_real_do_formulario(client, curso_com_equipe, aluno, monkeypatch):
    # salvar_secao descartava os erros do form e sempre mostrava a mesma string fixa
    # "Não foi possível salvar." (item 6 da revisao de branco). SecaoForm hoje so tem
    # o campo "conteudo", que e blank=True - nao ha entrada real que o invalide -
    # entao o form e substituido por um dublê sempre invalido, so para provar que a
    # view passa adiante os erros de verdade, e nao a string fixa.
    import apps.cursos.views.aluno as views_aluno

    class FormularioSempreInvalido:
        def __init__(self, *args, **kwargs):
            self.errors = {"conteudo": ["Erro fabricado para o teste."]}

        def is_valid(self):
            return False

    monkeypatch.setattr(views_aluno, "SecaoForm", FormularioSempreInvalido)

    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    client.force_login(aluno)
    resposta = client.post(reverse("salvar_secao", args=[secao.pk]), {"conteudo": "x"})
    conteudo = resposta.content.decode()
    assert "Erro fabricado para o teste." in conteudo
    assert "Não foi possível salvar." not in conteudo


@pytest.mark.django_db
def test_salvar_secao_de_entregavel_em_revisao_e_bloqueado(client, curso_com_equipe, aluno):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    escrever_o_plano_inteiro(plano)
    services.enviar_para_revisao(plano, por=aluno)
    client.force_login(aluno)
    resposta = client.post(reverse("salvar_secao", args=[secao.pk]), {"conteudo": "<p>Mudanca</p>"})
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_enviar_para_revisao_pela_tela(client, curso_com_equipe, aluno, arquivo_qualquer):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    client.force_login(aluno)
    resposta = client.post(reverse("enviar_entregavel", args=[slides.pk]), follow=True)
    assert resposta.status_code == 200
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.EM_REVISAO
    conteudo = resposta.content.decode()
    assert conteudo.count("Entregável enviado para revisão do professor.") == 1


@pytest.mark.django_db
def test_enviar_com_pendencia_mostra_a_lista(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.post(reverse("enviar_entregavel", args=[slides.pk]), follow=True)
    assert "Anexe ao menos um arquivo de slides." in resposta.content.decode()
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.RASCUNHO


@pytest.mark.django_db
def test_secao_de_entregavel_congelado_mostra_conteudo_sem_formulario(
    client, curso_com_equipe, aluno
):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    escrever_o_plano_inteiro(plano)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa fixada</p>"
    secao.save()
    services.enviar_para_revisao(plano, por=aluno)
    client.force_login(aluno)
    resposta = client.get(reverse("entregavel", args=[plano.pk]))
    conteudo = resposta.content.decode()
    assert "Ementa fixada" in conteudo
    assert "Salvar seção" not in conteudo


@pytest.mark.django_db
def test_salvar_secao_de_outra_equipe_e_bloqueado(client, curso_com_equipe, outro_aluno):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    assert plano.editavel
    secao = plano.secoes.first()
    client.force_login(outro_aluno)
    resposta = client.post(reverse("salvar_secao", args=[secao.pk]), {"conteudo": "<p>Invasao</p>"})
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_anexar_de_outra_equipe_e_bloqueado(client, curso_com_equipe, outro_aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    assert slides.editavel
    client.force_login(outro_aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]),
        {
            "titulo": "Invasao", "url": "https://exemplo.org",
            "rotulo": Rotulo.NENHUM, "tipo_pratica": TipoPratica.NENHUM,
        },
    )
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_enviar_entregavel_de_outra_equipe_e_bloqueado(client, curso_com_equipe, outro_aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    assert slides.editavel
    client.force_login(outro_aluno)
    resposta = client.post(reverse("enviar_entregavel", args=[slides.pk]))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_enviar_entregavel_via_get_e_rejeitado(client, curso_com_equipe, aluno, arquivo_qualquer):
    # A vulnerabilidade que este teste crava: sem @require_POST, um GET (por exemplo
    # <img src="/entregaveis/N/enviar/"> numa pagina qualquer que o aluno logado
    # visite) bastava para committar RASCUNHO -> EM_REVISAO, porque CSRF nao se
    # aplica a GET.
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    client.force_login(aluno)
    resposta = client.get(reverse("enviar_entregavel", args=[slides.pk]))
    assert resposta.status_code == 405
    slides.refresh_from_db()
    assert slides.status == StatusEntregavel.RASCUNHO


@pytest.mark.django_db
def test_salvar_secao_via_get_e_rejeitado(client, curso_com_equipe, aluno):
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    client.force_login(aluno)
    resposta = client.get(reverse("salvar_secao", args=[secao.pk]))
    assert resposta.status_code == 405


@pytest.mark.django_db
def test_anexar_via_get_e_rejeitado(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.get(reverse("anexar", args=[slides.pk]))
    assert resposta.status_code == 405


@pytest.mark.django_db
def test_anexar_arquivo_cria_o_anexo(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    upload = SimpleUploadedFile(
        "slides.pdf", b"%PDF-1.7\n%conteudo de teste\n", content_type="application/pdf"
    )
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]),
        {
            "titulo": "Slides da aula 1", "rotulo": Rotulo.NENHUM, "tipo_pratica": TipoPratica.NENHUM,
            "upload": upload,
        },
        follow=True,
    )
    assert resposta.status_code == 200
    anexo = slides.anexos.get(titulo="Slides da aula 1")
    assert anexo.tipo_midia == TipoMidia.ARQUIVO
    assert anexo.arquivo is not None
    assert anexo.arquivo.mime == "application/pdf"
    assert len(anexo.arquivo.hash_conteudo) == 64
    assert resposta.content.decode().count("Material anexado.") == 1


@pytest.mark.django_db
def test_anexar_arquivo_grande_preserva_hash_e_conteudo(client, curso_com_equipe, aluno):
    """conteudo = upload.read() carregava o arquivo inteiro na memoria so para
    calcular o hash - bastava para os 50 MB de hoje, mas e o mesmo caminho que o
    upload de 1 GB do Plano 4 vai herdar (item 8 da revisao de branco). A troca para
    leitura em pedacos (apps.cursos.arquivos.calcula_hash, testada isoladamente em
    test_anexo.py) precisa devolver o ponteiro do upload ao inicio antes de
    arquivo.arquivo.save() le-lo de novo - senao o arquivo gravado em disco viria
    truncado ou vazio mesmo com o hash certo. Usa um conteudo maior que um pedaco
    para que a leitura em pedacos realmente aconteca mais de uma vez."""
    conteudo = b"%PDF-1.7\n" + (b"A" * (300 * 1024))
    upload = SimpleUploadedFile("slides-grandes.pdf", conteudo, content_type="application/pdf")

    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]),
        {
            "titulo": "Slides grandes", "rotulo": Rotulo.NENHUM, "tipo_pratica": TipoPratica.NENHUM,
            "upload": upload,
        },
        follow=True,
    )
    assert resposta.status_code == 200
    anexo = slides.anexos.get(titulo="Slides grandes")
    assert anexo.arquivo.hash_conteudo == hashlib.sha256(conteudo).hexdigest()
    with anexo.arquivo.arquivo.open("rb") as arquivo_salvo:
        assert arquivo_salvo.read() == conteudo


@pytest.mark.django_db
def test_anexar_link_cria_o_anexo_sem_arquivo(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]),
        {
            "titulo": "Slides no Drive", "url": "https://exemplo.org/slides",
            "rotulo": Rotulo.NENHUM, "tipo_pratica": TipoPratica.NENHUM,
        },
        follow=True,
    )
    assert resposta.status_code == 200
    anexo = slides.anexos.get(titulo="Slides no Drive")
    assert anexo.tipo_midia == TipoMidia.LINK
    assert anexo.arquivo is None
    assert not Arquivo.objects.exists()


@pytest.mark.django_db
def test_anexar_arquivo_e_link_juntos_e_recusado_sem_quebrar(client, curso_com_equipe, aluno):
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    upload = SimpleUploadedFile(
        "slides.pdf", b"%PDF-1.7\n%conteudo de teste\n", content_type="application/pdf"
    )
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]),
        {
            "titulo": "Slides duplos", "url": "https://exemplo.org/slides",
            "rotulo": Rotulo.NENHUM, "tipo_pratica": TipoPratica.NENHUM,
            "upload": upload,
        },
        follow=True,
    )
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Anexo de arquivo não tem link." in conteudo
    assert not Anexo.objects.filter(titulo="Slides duplos").exists()
    # A rejeicao nao pode deixar o Arquivo (linha e arquivo em disco) pra tras: o
    # aluno so tentou de novo, mas sem isso cada tentativa acumularia um registro e
    # um arquivo orfaos, e limpar_arquivos_orfaos so existe no Plano 4.
    assert Arquivo.objects.count() == 0
    arquivos_em_disco = [
        nome for _, _, nomes in os.walk(settings.MEDIA_ROOT) for nome in nomes
    ]
    assert arquivos_em_disco == []


@pytest.mark.django_db
def test_responsavel_ve_o_proprio_curso_em_meus_cursos(client, dados_curso, professor):
    """Depois que o `Q(professor_responsavel=...)` saiu da consulta de meus_cursos,
    e o vinculo de equipe que poe o curso nesta tela. Se alguem criar Curso sem o
    MembroEquipe do responsavel, este teste e quem avisa."""
    curso = services.criar_curso(**dados_curso)
    client.force_login(professor)
    resposta = client.get(reverse("meus_cursos"))
    assert curso.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_card_do_entregavel_traz_a_etapa_em_selo(client, curso_com_equipe, aluno):
    """"Etapa 1" num selo, e o nome sem o numero: o numero solto no titulo nao
    dizia que aquilo era uma sequencia."""
    client.force_login(aluno)
    html = client.get(reverse("curso", args=[curso_com_equipe.pk])).content.decode()
    assert "Etapa 1" in html
    assert "Etapa 6" in html
    # O titulo do card nao repete o numero.
    assert "1 - Plano de Ensino" not in html


@pytest.mark.django_db
def test_telas_de_trabalho_tem_volta(client, curso_com_equipe, aluno):
    """Toda tela funda precisa de saida. Sem ela, a unica volta e o botao do
    navegador, que perde o que foi digitado num formulario aberto."""
    from apps.cursos.choices import TipoEntregavel

    entregavel = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[entregavel.pk])).content.decode()
    assert "voltar" in html.lower()
    assert reverse("curso", args=[curso_com_equipe.pk]) in html


@pytest.mark.django_db
def test_as_tres_telas_de_trabalho_usam_o_mesmo_painel(
    client, curso_com_equipe, aluno, professor
):
    """Curso, entregável e revisão desenhavam a mesma lista de tres jeitos: bloco
    no topo, coluna esquerda, lateral. Passam a incluir o mesmo painel, na mesma
    coluna, e este teste e o que impede a proxima tela de reinventar.

    A assercao e sobre a marcacao compartilhada (`painel-pendencias` dentro de
    `coluna-pendencias`), e nao sobre o texto, que muda por tela de proposito.
    """
    from apps.cursos.choices import StatusEntregavel, TipoEntregavel

    entregavel = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    entregavel.status = StatusEntregavel.EM_REVISAO
    entregavel.save(update_fields=["status"])

    client.force_login(aluno)
    telas = {
        "curso": client.get(reverse("ficha", args=[curso_com_equipe.pk])),
        "entregavel": client.get(reverse("entregavel", args=[entregavel.pk])),
    }
    client.force_login(professor)
    telas["revisao"] = client.get(reverse("revisar", args=[entregavel.pk]))

    for nome, resposta in telas.items():
        html = resposta.content.decode()
        assert resposta.status_code == 200, nome
        assert "painel-pendencias" in html, nome
        assert "coluna-pendencias" in html, nome
        assert "duas-colunas" in html, nome
        # O painel fica DEPOIS do corpo no HTML, ou seja, na coluna da direita.
        assert html.index("duas-colunas") < html.index("painel-pendencias"), nome


@pytest.mark.django_db
def test_secoes_do_plano_ficam_em_cartao(client, curso_com_equipe, aluno):
    """As secoes do Plano de Ensino renderizavam soltas, sem cartao, enquanto a
    tela de editar curso punha tudo em cartao. Era a maior parte da diferenca
    visual entre as duas telas, e nada no sistema garantia o contrario.

    O cartao precisa estar no proprio <section>, e nao num embrulho por fora: e
    esse elemento que o HTMX troca por outerHTML ao salvar, e um embrulho ficaria
    para tras na primeira edicao.
    """
    import re

    from apps.cursos.choices import TipoEntregavel

    entregavel = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[entregavel.pk])).content.decode()
    secoes = re.findall(r'<section id="secao-\d+"[^>]*class="([^"]*)"', html)
    assert secoes, "nenhuma seção renderizada"
    assert all("bloco" in c for c in secoes), secoes


@pytest.mark.django_db
def test_plano_de_ensino_nao_oferece_materiais(client, curso_com_equipe, aluno):
    """O plano e escrito nas secoes, e nao anexado: a tela nao mostra Materiais
    nem Anexar material."""
    from apps.cursos.choices import TipoEntregavel

    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[plano.pk])).content.decode()
    assert "Anexar material" not in html
    assert "<h2>Materiais</h2>" not in html


@pytest.mark.django_db
def test_os_outros_entregaveis_continuam_oferecendo(client, curso_com_equipe, aluno):
    """Prende o outro lado: so o plano perdeu os materiais."""
    from apps.cursos.choices import TipoEntregavel

    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[slides.pk])).content.decode()
    assert "Anexar material" in html
    assert "<h2>Materiais</h2>" in html
