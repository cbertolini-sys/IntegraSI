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
    """No caderno, e nao no plano de ensino: o plano deixou de receber anexo, e a
    recusa viria dai mesmo com a guarda de estado apagada. Duas guardas que
    respondem 403 nao se distinguem por um POST so (CLAUDE.md)."""
    caderno = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    caderno.status = StatusEntregavel.EM_REVISAO
    caderno.save(update_fields=["status", "atualizado_em"])
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[caderno.pk]), {"titulo": "Outro", "url": "https://exemplo.org"}
    )
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
            "titulo": "Slides da aula 1", "descricao": "Os slides da primeira aula.",
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
            "titulo": "Slides grandes", "descricao": "Slides com muitas imagens.",
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
    assert "<h3>Materiais</h3>" in html


@pytest.mark.django_db
def test_secoes_do_plano_explicam_o_que_escrever(client, curso_com_equipe, aluno):
    """As secoes eram a unica area de escrita sem balao: `_secao.html` e escrito a
    mao, sem `help_text`, entao nem o gatilho do template nem a conversao do JS
    alcancavam. A explicacao vive ao lado da lista que cria as secoes."""
    import re

    from apps.cursos.choices import TipoEntregavel

    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[plano.pk])).content.decode()
    ajudas = re.findall(r'class="ajuda-campo"\s+data-ajuda="([^"]+)"', html)
    assert len(ajudas) == 7, f"{len(ajudas)} balões para 7 seções"
    assert any("verbo" in a for a in ajudas)


@pytest.mark.django_db
def test_toda_secao_padrao_tem_explicacao():
    """As sete criadas por `criar_curso` precisam estar todas explicadas: uma nova
    na lista sem entrada no dicionario passaria despercebida, e a tela ficaria com
    seis balões e um buraco."""
    from apps.cursos.services import AJUDA_DAS_SECOES, SECOES_PLANO_ENSINO

    sem = [t for t in SECOES_PLANO_ENSINO if not AJUDA_DAS_SECOES.get(t)]
    assert sem == [], f"seções sem explicação: {sem}"


@pytest.mark.django_db
def test_o_campo_enviado_continua_sendo_o_textarea(client, curso_com_equipe, aluno):
    """O Quill entra na frente do textarea, que fica escondido mas presente: e ele
    que o Django recebe, e e ele que salva quando o JS nao roda. Trocar por um
    <div> deixaria a tela sem saida nesse caso."""
    from apps.cursos.choices import TipoEntregavel

    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[plano.pk])).content.decode()
    assert html.count('<textarea name="conteudo" rows="10" data-editor>') == 7


@pytest.mark.django_db
def test_slides_pede_so_o_essencial_para_anexar(client, curso_com_equipe, aluno):
    """Cada entregavel tem regras proprias, e o formulario oferecia os campos de
    todos: referencia bibliografica e dos cards, rotulo e tipo de pratica sao do
    caderno de exercicios. Nos slides eram quatro campos que nao servem a nada.

    O link sai junto por um motivo de regra, e nao de tela: `_slides` conta apenas
    anexo que NAO e link, entao hoje da para anexar um link aos slides e ele nao
    conta para o envio. Tirar o campo fecha essa armadilha."""
    from apps.cursos.choices import TipoEntregavel

    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[slides.pk])).content.decode()
    for campo in ("referencia_bibliografica", "rotulo", "tipo_pratica", "url"):
        assert f'name="{campo}"' not in html, campo
    for campo in ("titulo", "descricao", "upload"):
        assert f'name="{campo}"' in html, campo


@pytest.mark.django_db
def test_os_outros_entregaveis_mantem_os_campos(client, curso_com_equipe, aluno):
    """Prende o outro lado do enxugamento: o caderno guarda rotulo e tipo de
    pratica porque `_caderno` cobra os dois (versao com e sem gabarito, atividade
    plugada e desplugada). Sao os unicos campos que sobreviveram nele."""
    from apps.cursos.choices import TipoEntregavel

    caderno = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[caderno.pk])).content.decode()
    for campo in ("titulo", "descricao", "rotulo", "tipo_pratica", "upload"):
        assert f'name="{campo}"' in html, campo
    for campo in ("referencia_bibliografica", "url"):
        assert f'name="{campo}"' not in html, campo


@pytest.mark.django_db
def test_anexar_slides_sem_arquivo_avisa_sem_falar_em_link(client, curso_com_equipe, aluno):
    """A mensagem antiga dizia "envie um arquivo ou informe um link" num
    formulario que nao tem mais campo de link: instrucao para um campo que a
    pessoa nao encontra e pior que nenhuma."""
    from apps.cursos.choices import TipoEntregavel

    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[slides.pk]), {"titulo": "Aula 1"}, follow=True
    )
    texto = resposta.content.decode()
    assert "Envie o arquivo." in texto
    assert "informe um link" not in texto


# --- Video-Aulas: so o envio fatiado --------------------------------------


@pytest.mark.django_db
def test_videos_nao_oferecem_o_formulario_generico_de_anexar(client, curso_com_equipe, aluno):
    """A tela tinha dois caminhos para o mesmo fim e um deles nao levava a lugar
    nenhum: o video precisa de `TipoMidia.VIDEO`, que so o envio em blocos cria
    (`services.concluir_upload`). Anexo comum nao contava para `_videos`, entao a
    pessoa anexava, via o material na lista e continuava sem poder enviar."""
    videos = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[videos.pk])).content.decode()
    assert "Anexar material" not in html
    assert 'action="/entregaveis/%d/anexar/"' % videos.pk not in html
    # O que fica: o envio de video e a lista do que ja foi enviado.
    assert "Enviar vídeo-aula" in html
    assert "data-upload-video" in html
    assert "Materiais" in html


@pytest.mark.django_db
def test_a_tela_de_videos_nao_imprime_o_comentario_do_template(client, curso_com_equipe, aluno):
    """O comentario de cerquilha de varias linhas saia renderizado como texto na
    pagina: `{#` so fecha na mesma linha. Era o "erro" que aparecia na tela."""
    videos = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[videos.pk])).content.decode()
    assert "Upload fatiado" not in html
    assert "spec 8" not in html


@pytest.mark.django_db
def test_anexar_em_videos_e_recusado_mesmo_com_o_formulario_fora_da_tela(
    client, curso_com_equipe, aluno
):
    """Sumir da tela nao fecha a rota. Sem esta guarda o POST continua valendo, e
    com o formulario vazio de campos ele passaria a criar Anexo em branco."""
    videos = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.VIDEOS)
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[videos.pk]),
        {"titulo": "Aula 1", "url": "https://exemplo.org/aula"},
    )
    assert resposta.status_code == 403
    assert not videos.anexos.exists()


@pytest.mark.django_db
def test_anexar_no_plano_de_ensino_e_recusado(client, curso_com_equipe, aluno):
    """Mesmo buraco: a tela do plano deixou de oferecer materiais, mas a rota
    seguia aberta. O entregavel esta em RASCUNHO, entao a recusa nao pode vir da
    guarda de estado."""
    plano = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    assert plano.status == StatusEntregavel.RASCUNHO
    client.force_login(aluno)
    resposta = client.post(
        reverse("anexar", args=[plano.pk]),
        {"titulo": "Plano", "url": "https://exemplo.org/plano"},
    )
    assert resposta.status_code == 403
    assert not plano.anexos.exists()


@pytest.mark.django_db
def test_o_formulario_de_anexo_nasce_vazio_onde_a_lista_e_vazia():
    """Prende a leitura de CAMPOS_DO_ANEXO na propria funcao, e nao so nas telas.

    `if permitidos:` tratava lista vazia como "sem restricao" e devolvia o
    formulario inteiro - o oposto do que a lista vazia quer dizer. As views nao
    revelam isso, porque nem chegam a construir o formulario nesses casos; um
    chamador futuro chegaria.
    """
    from apps.cursos.forms import AnexoForm

    assert list(AnexoForm(tipo=TipoEntregavel.VIDEOS).fields) == []
    assert list(AnexoForm(tipo=TipoEntregavel.PLANO_ENSINO).fields) == []
    assert list(AnexoForm(tipo=TipoEntregavel.SLIDES).fields) == [
        "titulo", "descricao", "upload",
    ]
    assert list(AnexoForm(tipo=TipoEntregavel.CADERNO).fields) == [
        "titulo", "descricao", "rotulo", "tipo_pratica", "upload",
    ]
    # Sem tipo, o formulario inteiro. Hoje os seis entregaveis estao no mapa, entao
    # este e o unico jeito de alcancar o padrao - que continua existindo para que
    # um entregavel novo apareca com todos os campos, e nao com nenhum.
    assert len(AnexoForm().fields) > 5


# --- Infograficos e Cards: sem rotulo, sem link, pratica em caixas de marcar ---


def anexa_card(client, cards, **extra):
    upload = SimpleUploadedFile(
        "card.pdf", b"%PDF-1.7\n%conteudo de teste\n", content_type="application/pdf"
    )
    dados = {
        "titulo": "Card 1",
        "descricao": "Um card sobre senhas fortes.",
        "referencia_bibliografica": "BNCC, 2018.",
        "tipo_pratica": [TipoPratica.DESPLUGADA],
        "upload": upload,
    }
    dados.update(extra)
    return client.post(reverse("anexar", args=[cards.pk]), dados, follow=True)


@pytest.mark.django_db
def test_cards_nao_pedem_rotulo_nem_link(client, curso_com_equipe, aluno):
    """Rotulo diz se o arquivo e a versao com ou sem gabarito: e do caderno de
    exercicios, e num card nao quer dizer nada. O link era pior que ruido, como
    nos slides: `_cards` conta so anexo que NAO e link (`_arquivos()` exclui
    TipoMidia.LINK), entao dava para anexar um link, ve-lo na lista e continuar
    sem poder enviar para revisao."""
    cards = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.CARDS)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[cards.pk])).content.decode()
    for campo in ("rotulo", "url"):
        assert f'name="{campo}"' not in html, campo
    for campo in ("titulo", "descricao", "referencia_bibliografica", "tipo_pratica", "upload"):
        assert f'name="{campo}"' in html, campo


@pytest.mark.django_db
def test_o_caderno_continua_pedindo_rotulo(client, curso_com_equipe, aluno):
    """A outra metade: `_caderno` cobra a versao com e a sem gabarito, e sem o
    campo a equipe nao teria como dizer qual e qual."""
    caderno = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.CADERNO)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[caderno.pk])).content.decode()
    assert 'name="rotulo"' in html


@pytest.mark.django_db
def test_tipo_de_pratica_e_duas_caixas_de_marcar(client, curso_com_equipe, aluno):
    """O <select> de quatro opcoes precisava de uma entrada so para dizer "as
    duas", e a pessoa tinha que procurar por ela. Duas caixas dizem o mesmo sem
    vocabulario proprio."""
    cards = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.CARDS)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[cards.pk])).content.decode()
    assert '<select name="tipo_pratica"' not in html
    assert html.count('type="checkbox" name="tipo_pratica"') == 2
    assert 'value="PLUGADA"' in html
    assert 'value="DESPLUGADA"' in html
    # Os rotulos sao os curtos, e nao os do enum ("Atividade plugada"): ao lado de
    # uma caixa de marcar a palavra "Atividade" nao acrescenta nada.
    assert "Atividade plugada" not in html


@pytest.mark.django_db
def test_marcar_as_duas_praticas_grava_ambas(client, curso_com_equipe, aluno):
    """O valor gravado nao mudou (CLAUDE.md: valor gravado nunca e alterado): as
    duas caixas marcadas continuam virando AMBAS, que e o que `_caderno` e
    `Curso.praticas` leem."""
    cards = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.CARDS)
    client.force_login(aluno)
    anexa_card(client, cards, tipo_pratica=[TipoPratica.PLUGADA, TipoPratica.DESPLUGADA])
    assert cards.anexos.get().tipo_pratica == TipoPratica.AMBAS


@pytest.mark.django_db
def test_marcar_uma_pratica_grava_so_ela(client, curso_com_equipe, aluno):
    cards = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.CARDS)
    client.force_login(aluno)
    anexa_card(client, cards, tipo_pratica=[TipoPratica.DESPLUGADA])
    assert cards.anexos.get().tipo_pratica == TipoPratica.DESPLUGADA


def test_o_campo_de_pratica_ainda_sabe_traduzir_nenhuma_marcada():
    """A tela nao alcanca mais este caminho - nos entregaveis o campo e
    obrigatorio -, mas a traducao continua sendo o contrato do campo: sem marca
    nenhuma o valor gravado e NENHUM, que e o padrao do modelo. Provado aqui, e
    nao pela tela, porque a tela recusa antes (`test_marcar_nenhuma_pratica_
    deixa_de_ser_aceito`, em test_campo_obrigatorio.py)."""
    from apps.cursos.forms import TipoPraticaField

    campo = TipoPraticaField()
    assert campo.clean([]) == TipoPratica.NENHUM
    assert campo.clean([TipoPratica.PLUGADA]) == TipoPratica.PLUGADA
    assert campo.clean(
        [TipoPratica.PLUGADA, TipoPratica.DESPLUGADA]
    ) == TipoPratica.AMBAS


# --- Caderno e Avaliacao: so o que a regra de cada um usa ----------------------


@pytest.mark.django_db
def test_avaliacao_pede_so_o_essencial(client, curso_com_equipe, aluno):
    """Referencia bibliografica e dos cards, rotulo e tipo de pratica sao do
    caderno. Na avaliacao os quatro nao dizem nada sobre um instrumento."""
    avaliacao = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.AVALIACAO)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[avaliacao.pk])).content.decode()
    for campo in ("referencia_bibliografica", "rotulo", "tipo_pratica", "url"):
        assert f'name="{campo}"' not in html, campo
    for campo in ("titulo", "descricao", "upload"):
        assert f'name="{campo}"' in html, campo


@pytest.mark.django_db
def test_so_os_cards_pedem_referencia_bibliografica(client, curso_com_equipe, aluno):
    """`_cards` e a unica regra que cobra a referencia. Nos outros ela era campo
    que ninguem le: aparecia na tela, ia para o banco e nao entrava em decisao
    nenhuma."""
    client.force_login(aluno)
    for tipo in TipoEntregavel:
        entregavel = curso_com_equipe.entregaveis.get(tipo=tipo)
        html = client.get(reverse("entregavel", args=[entregavel.pk])).content.decode()
        tem = 'name="referencia_bibliografica"' in html
        assert tem == (tipo == TipoEntregavel.CARDS), tipo


@pytest.mark.django_db
def test_nenhum_entregavel_oferece_campo_de_link(client, curso_com_equipe, aluno):
    """Consequencia assumida de tirar o link da avaliacao, escrita para nao ficar
    calada: nenhuma tela do sistema cria mais anexo de link.

    `validacoes._avaliacao` continua ACEITANDO link (um instrumento pode ser um
    formulario online), e `test_avaliacao_aceita_link` continua provando isso do
    lado do modelo. O que sumiu foi o caminho da interface ate la. Se o campo
    voltar a algum entregavel, este teste e o primeiro a reprovar, e ai a decisao
    volta a ser tomada de propria vontade em vez de por descuido."""
    client.force_login(aluno)
    for tipo in TipoEntregavel:
        entregavel = curso_com_equipe.entregaveis.get(tipo=tipo)
        html = client.get(reverse("entregavel", args=[entregavel.pk])).content.decode()
        assert 'name="url"' not in html, tipo


# --- As seis telas seguem a estrutura do Plano de Ensino ----------------------
#
# O Plano de Ensino e o padrao: `<section class="bloco">` com `<h3>` e o gatilho
# de ajuda no titulo, campos no `.campo` com tooltip, e botao de acao com a classe
# `.botao`. As outras cinco telas usavam `<div class="bloco">` com `<h2>`, o
# formulario de anexar saia pelo `as_p` do Django (com a ajuda em paragrafo
# visivel, e nao em balao) e os botoes iam sem classe nenhuma.


def coluna_de_trabalho(html):
    """So a coluna da esquerda: a lateral e o cabecalho ja eram iguais nas seis."""
    return html[html.index("coluna-trabalho") : html.index("<aside")]


def tela_do_entregavel(client, curso, tipo):
    entregavel = curso.entregaveis.get(tipo=tipo)
    return client.get(reverse("entregavel", args=[entregavel.pk])).content.decode()


@pytest.mark.django_db
def test_os_cartoes_das_seis_telas_sao_section_com_h3(client, curso_com_equipe, aluno):
    """`.bloco` e `<section>` com `<h3>` no Plano de Ensino, e o CSS desenha o
    titulo do cartao por `.bloco > h3`. Com `<h2>`, os outros cinco pegavam outro
    tamanho de fonte no mesmo lugar da tela."""
    client.force_login(aluno)
    for tipo in TipoEntregavel:
        corpo = coluna_de_trabalho(tela_do_entregavel(client, curso_com_equipe, tipo))
        assert '<div class="bloco"' not in corpo, tipo
        assert "<h2" not in corpo, tipo
        assert corpo.count('class="bloco"') >= 1, tipo
        # Todo `.bloco` da coluna e <section>: no Plano de Ensino ele vem com id
        # antes da classe (`<section id="secao-N" class="bloco">`), entao a conta
        # e sobre a classe, e o <div> e proibido pela linha acima.
        assert corpo.count('class="bloco"') == corpo.count("<section")


@pytest.mark.django_db
def test_o_formulario_de_anexar_usa_o_campo_padrao_com_tooltip(client, curso_com_equipe, aluno):
    """O `as_p` do Django punha a ajuda como paragrafo visivel sob cada campo, sem
    `.campo` e sem balao: a mesma explicacao aparecia de dois jeitos na mesma tela,
    porque o formulario de video ja passava pelo `_campo.html`."""
    client.force_login(aluno)
    for tipo, quantos in (
        (TipoEntregavel.SLIDES, 3),
        (TipoEntregavel.CARDS, 5),
        (TipoEntregavel.CADERNO, 5),
        (TipoEntregavel.AVALIACAO, 3),
    ):
        corpo = coluna_de_trabalho(tela_do_entregavel(client, curso_com_equipe, tipo))
        assert corpo.count('class="ajuda-campo"') == quantos, tipo
        assert corpo.count('<div class="campo') == quantos, tipo
        # A ajuda vai para o balao; o texto continua no HTML so para o leitor de
        # tela, escondido. Visivel, ele dobrava a altura do formulario.
        assert 'class="helptext"' not in corpo, tipo


@pytest.mark.django_db
def test_todo_botao_de_acao_das_telas_de_entregavel_tem_a_classe(client, curso_com_equipe, aluno):
    """`Anexar` e `Enviar vídeo` iam sem classe. O CSS pinta todo `<button>`, entao
    eles PARECIAM certos: a diferenca so aparece quando `.botao` ganha um estado
    novo (foco, carregando) e esses dois ficam para tras."""
    import re

    client.force_login(aluno)
    for tipo in TipoEntregavel:
        corpo = coluna_de_trabalho(tela_do_entregavel(client, curso_com_equipe, tipo))
        for abertura in re.findall(r"<button[^>]*>", corpo):
            assert "class=" in abertura, f"{tipo}: {abertura}"


@pytest.mark.django_db
def test_a_descricao_tem_o_mesmo_editor_em_todo_entregavel(client, curso_com_equipe, aluno):
    """`Anexo.descricao` e o mesmo campo, sanitizado do mesmo jeito e mostrado com
    |safe na mesma lista. Ter editor so na video-aula fazia a mesma coisa aceitar
    formatacao numa tela e nao aceitar na de baixo."""
    client.force_login(aluno)
    for tipo in (
        TipoEntregavel.SLIDES, TipoEntregavel.VIDEOS, TipoEntregavel.CARDS,
        TipoEntregavel.CADERNO, TipoEntregavel.AVALIACAO,
    ):
        corpo = coluna_de_trabalho(tela_do_entregavel(client, curso_com_equipe, tipo))
        assert 'name="descricao"' in corpo, tipo
        assert "data-editor" in corpo, tipo


@pytest.mark.django_db
def test_o_curso_aparece_como_migalha_e_nao_como_link_solto(client, curso_com_equipe, aluno):
    """O nome do curso ficava num `<p class="sub">` com um `<a>` cru embaixo do
    titulo: azul, sublinhado, sem dizer que era o caminho de volta. Vira a mesma
    migalha que o catalogo ja usa, com o selo da etapa dentro dela - curso,
    depois etapa, depois o nome do entregavel no `<h1>`.
    """
    slides = curso_com_equipe.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    client.force_login(aluno)
    html = client.get(reverse("entregavel", args=[slides.pk])).content.decode()
    cabecalho = html[html.index("cabecalho-pagina") : html.index("corpo-trabalho")]

    assert 'class="migalha"' in cabecalho
    migalha = cabecalho[cabecalho.index('class="migalha"') : cabecalho.index("</p>", cabecalho.index('class="migalha"'))]
    assert curso_com_equipe.titulo in migalha
    assert reverse("curso", args=[curso_com_equipe.pk]) in migalha
    assert "selo-etapa" in migalha, "o selo da etapa faz parte do caminho"
    assert 'class="sub"' not in cabecalho, "a linha solta sob o título saiu"


def test_a_migalha_nao_depende_do_fundo_escuro_do_catalogo():
    """A cor branca da migalha era da regra base, feita para o herói do catálogo.

    Reusada no cabeçalho branco do entregável, ela ficaria branca sobre branco:
    invisível. A cor clara passa a viver no contexto (`.topo-curso .migalha`), e a
    regra base fica com a cor do texto comum.
    """
    from pathlib import Path

    from django.conf import settings

    css = (Path(settings.BASE_DIR) / "static" / "css" / "integrasi.css").read_text(
        encoding="utf-8"
    )
    base = css[css.index(".migalha {") : css.index("}", css.index(".migalha {"))]
    assert "255, 255, 255" not in base, "a regra base voltou a ser branca"
    assert ".topo-curso .migalha" in css, "o herói do catálogo perdeu a cor clara"
