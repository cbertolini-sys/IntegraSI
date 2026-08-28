"""Entrega protegida de arquivos (Plano 4, Task 4).

As regras que este arquivo prende, na ordem em que aparecem:

 1. A rota `baixar` acha o Arquivo pelo `identificador` (UUID, nao pk);
    identificador desconhecido -> 404.
 2. Visitante anonimo vai para o login (302 para LOGIN_URL) — nao 403, nao os bytes.
 3. Metodo errado -> 405.
 4. Autoriza quem pode ver ALGUM curso que anexa o arquivo. A partir da Task 5 um
    mesmo Arquivo e compartilhado por varias versoes do curso; olhar so o primeiro
    anexo recusaria quem tem acesso por outra versao (e liberaria por uma versao
    que a pessoa nao deveria ver).
 5. Quem nao pode ver nenhum dos cursos que anexam o arquivo -> 403.
 6. Arquivo sem anexo nenhum -> 403 (nao ha curso por onde autorizar).
 7. Curso publicado nao libera o material de producao para estranho: o catalogo
    publico e outra porta, `pode_ver_curso` nao olha o status.
 8. Com USAR_X_ACCEL, o corpo vai vazio e quem transmite e o nginx
    (`X-Accel-Redirect`); o Django nao abre o arquivo.
 9. O caminho do `X-Accel-Redirect` deriva do nome gravado pelo FileField
    (`materiais/<hex>/...`), NUNCA do `nome_original`, que e texto do usuario.
10. `Content-Disposition: inline` so para PDF e MP4 (spec 8).
11. PNG e JPEG saem como `attachment`: sao de renderizar, mas ficam de fora de
    proposito — a lista e de tipos seguros de abrir, nao de tipos exibiveis.
12. Mime que nao esta na lista (ex.: SVG) sai como `attachment`.
13. O nome exibido no `Content-Disposition` e o `nome_original`, percent-encoded
    em `filename*=UTF-8''`.
14. Sem USAR_X_ACCEL (desenvolvimento) o proprio Django entrega os bytes, com o
    mesmo cabecalho de disposicao e passando pelo mesmo portao de permissao.
15. As telas de entregavel e de revisao linkam o anexo pela rota protegida.

Regra 16 — `USAR_X_ACCEL` nasce ligado quando `DEBUG` esta desligado — mora em
`tests/test_configuracao.py`: e uma settings, e o unico jeito de ver o padrao e
importar as settings fora do pytest-django, que forca DEBUG=False.

O que nenhum teste daqui alcanca: se o `location /protegido/` do nginx nao
estiver marcado `internal;`, qualquer pessoa pede `/protegido/<caminho>` direto e
pula a view inteira. A view continua correta e o sistema fica aberto. E
obrigacao da Task 8.
"""

import uuid

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo


def _anexa(curso, arquivo, enviado_por, titulo="Slides"):
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    return Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo=titulo,
        arquivo=arquivo, enviado_por=enviado_por,
    )


@pytest.fixture
def anexo(dados_curso, aluno, arquivo_qualquer):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return _anexa(curso, arquivo_qualquer, aluno)


@pytest.fixture
def url(anexo):
    return reverse("baixar", args=[anexo.arquivo.identificador])


# --- Regras 1 a 3: rota, portao de login e metodo --------------------------


@pytest.mark.django_db
def test_identificador_desconhecido_e_404(client, aluno):
    client.force_login(aluno)

    assert client.get(reverse("baixar", args=[uuid.uuid4()])).status_code == 404


@pytest.mark.django_db
def test_anonimo_vai_para_o_login(client, url):
    """Sem @login_required, `pode_ver_curso` leria `AnonymousUser.e_coordenador` e
    o visitante levaria 500. Pinado no comportamento exato, e nao em `302 ou 403`:
    um assert que aceita os dois nao percebe quando um vira o outro."""
    resposta = client.get(url)

    assert resposta.status_code == 302
    assert resposta.url.startswith(reverse("login"))


@pytest.mark.django_db
@pytest.mark.parametrize("metodo", ["post", "put", "delete"])
def test_metodo_errado_e_rejeitado(client, aluno, url, metodo):
    client.force_login(aluno)

    assert getattr(client, metodo)(url).status_code == 405


# --- Regras 4 a 7: quem pode baixar ----------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("usar_x_accel", [True, False])
def test_aluno_de_outra_equipe_nao_baixa(client, url, outro_aluno, settings, usar_x_accel):
    """Parametrizado nos dois modos de entrega para que o portao nao possa cair
    dentro do ramo do X-Accel e deixar o ramo do Django servindo a quem quiser."""
    settings.USAR_X_ACCEL = usar_x_accel
    client.force_login(outro_aluno)

    assert client.get(url).status_code == 403


@pytest.mark.django_db
def test_arquivo_sem_anexo_nenhum_nao_baixa(client, aluno, arquivo_qualquer, settings):
    """Arquivo orfao (nenhum anexo o referencia) nao tem curso por onde autorizar."""
    settings.USAR_X_ACCEL = True
    client.force_login(aluno)

    resposta = client.get(reverse("baixar", args=[arquivo_qualquer.identificador]))

    assert resposta.status_code == 403


@pytest.mark.django_db
def test_membro_baixa(client, url, aluno, settings):
    settings.USAR_X_ACCEL = True
    client.force_login(aluno)

    resposta = client.get(url)

    assert resposta.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("quem", ["aluno", "outro_aluno"])
def test_arquivo_compartilhado_libera_por_qualquer_curso(
    client, settings, request, dados_curso, aluno, outro_aluno, arquivo_qualquer, quem
):
    """O mesmo Arquivo em dois cursos, cada um com um aluno diferente: os dois
    baixam. Autorizar contra `arquivo.anexos.first()` recusaria um deles — qual,
    depende da ordenacao do Anexo, por isso o teste cobra os dois lados. E o
    caso que a Task 5 torna rotina: versoes de um curso compartilham o mesmo
    Arquivo em vez de clonar os bytes (spec 4.6)."""
    settings.USAR_X_ACCEL = True
    primeiro = services.criar_curso(**dados_curso)
    services.adicionar_membro(primeiro, aluno, por=primeiro.professor_responsavel)
    _anexa(primeiro, arquivo_qualquer, aluno)
    segundo = services.criar_curso(**{**dados_curso, "titulo": "Outro curso, mesmo material"})
    services.adicionar_membro(segundo, outro_aluno, por=segundo.professor_responsavel)
    _anexa(segundo, arquivo_qualquer, outro_aluno)

    client.force_login(request.getfixturevalue(quem))

    resposta = client.get(reverse("baixar", args=[arquivo_qualquer.identificador]))

    assert resposta.status_code == 200


@pytest.mark.django_db
def test_curso_publicado_nao_libera_material_para_estranho(
    client, anexo, url, outro_aluno, professor, coordenador
):
    curso = anexo.entregavel.curso
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    client.force_login(outro_aluno)

    assert client.get(url).status_code == 403


# --- Regras 8 e 9: quem transmite, e por qual caminho ----------------------


@pytest.mark.django_db
def test_em_producao_o_corpo_vai_vazio_e_o_nginx_transmite(client, url, anexo, aluno, settings):
    """1 GB pelo processo Python prende um worker por dez minutos (spec 8)."""
    settings.USAR_X_ACCEL = True
    client.force_login(aluno)

    resposta = client.get(url)

    assert resposta.content == b""
    assert resposta["X-Accel-Redirect"] == f"/protegido/{anexo.arquivo.arquivo.name}"


@pytest.mark.django_db
def test_o_caminho_interno_vem_do_filefield_e_nao_do_nome_original(
    client, url, anexo, aluno, settings
):
    """`nome_original` e texto que o usuario escolheu. Montar o
    `X-Accel-Redirect` com ele deixaria a pessoa apontar o nginx para outro
    lugar do disco; o nome gravado pelo FileField vem de `caminho_do_arquivo`,
    derivado do UUID."""
    settings.USAR_X_ACCEL = True
    arquivo = anexo.arquivo
    arquivo.nome_original = "../../../etc/passwd"
    arquivo.save(update_fields=["nome_original"])
    client.force_login(aluno)

    caminho = client.get(url)["X-Accel-Redirect"]

    assert caminho == f"/protegido/{arquivo.arquivo.name}"
    assert caminho.startswith("/protegido/materiais/")
    assert "passwd" not in caminho
    assert ".." not in caminho


# --- Regras 10 a 13: como o navegador trata o que chega --------------------


@pytest.mark.django_db
def test_pdf_abre_no_navegador(client, url, aluno, settings):
    settings.USAR_X_ACCEL = True
    client.force_login(aluno)

    assert client.get(url)["Content-Disposition"].startswith("inline")


@pytest.mark.django_db
def test_video_abre_no_navegador(client, anexo, aluno, settings):
    settings.USAR_X_ACCEL = True
    arquivo = anexo.arquivo
    arquivo.mime = "video/mp4"
    arquivo.save(update_fields=["mime"])
    client.force_login(aluno)

    resposta = client.get(reverse("baixar", args=[arquivo.identificador]))

    assert resposta["Content-Disposition"].startswith("inline")


@pytest.mark.django_db
@pytest.mark.parametrize("mime", ["image/png", "image/jpeg"])
def test_imagem_vai_como_anexo(client, anexo, aluno, settings, mime):
    """Deliberado, nao esquecimento: a lista de `inline` e de tipos que abrir no
    nosso dominio nao cria risco, e a spec 8 fecha em PDF e video."""
    settings.USAR_X_ACCEL = True
    arquivo = anexo.arquivo
    arquivo.mime = mime
    arquivo.save(update_fields=["mime"])
    client.force_login(aluno)

    resposta = client.get(reverse("baixar", args=[arquivo.identificador]))

    assert resposta["Content-Disposition"].startswith("attachment")


@pytest.mark.django_db
def test_tipo_nao_confiavel_vai_como_anexo(client, anexo, aluno, settings):
    """SVG servido inline a partir do nosso dominio e vetor de XSS. O estado e
    inalcancavel por upload — `detecta_mime` nunca devolve image/svg+xml e o mime
    e gravado por ela —, entao isto e defesa em profundidade: prende o
    comportamento para o dia em que um tipo novo entrar em ASSINATURAS."""
    settings.USAR_X_ACCEL = True
    arquivo = anexo.arquivo
    arquivo.mime = "image/svg+xml"
    arquivo.save(update_fields=["mime"])
    client.force_login(aluno)

    resposta = client.get(reverse("baixar", args=[arquivo.identificador]))

    assert resposta["Content-Disposition"].startswith("attachment")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "nome,esperado",
    [
        ("aula prática.pdf", "aula%20pr%C3%A1tica.pdf"),
        # Barra tambem e codificada: o nome escolhido pelo usuario nao pode
        # aparecer cru num cabecalho de resposta, nem parecendo caminho.
        ("pasta/aula.pdf", "pasta%2Faula.pdf"),
    ],
)
def test_o_nome_exibido_e_o_nome_original_codificado(
    client, url, anexo, aluno, settings, nome, esperado
):
    settings.USAR_X_ACCEL = True
    arquivo = anexo.arquivo
    arquivo.nome_original = nome
    arquivo.save(update_fields=["nome_original"])
    client.force_login(aluno)

    disposicao = client.get(url)["Content-Disposition"]

    assert disposicao == f"inline; filename*=UTF-8''{esperado}"


# --- Regra 14: desenvolvimento sem nginx na frente -------------------------


@pytest.mark.django_db
def test_em_desenvolvimento_o_django_entrega_o_arquivo(client, url, aluno, settings):
    settings.USAR_X_ACCEL = False
    client.force_login(aluno)

    resposta = client.get(url)
    # Consumido ANTES dos asserts: e o que fecha o arquivo aberto pelo
    # FileResponse. Um assert que falha antes do fim do iterador deixaria o
    # descritor aberto, e o ResourceWarning (filterwarnings = ["error"]) cairia
    # sobre um teste posterior sem relacao nenhuma com este.
    corpo = b"".join(resposta.streaming_content)

    assert resposta.status_code == 200
    assert "X-Accel-Redirect" not in resposta
    assert resposta["Content-Disposition"].startswith("inline")
    assert b"PDF" in corpo


@pytest.mark.django_db
def test_em_desenvolvimento_a_disposicao_tambem_vale(client, anexo, aluno, settings):
    settings.USAR_X_ACCEL = False
    arquivo = anexo.arquivo
    arquivo.mime = "image/png"
    arquivo.save(update_fields=["mime"])
    client.force_login(aluno)

    resposta = client.get(reverse("baixar", args=[arquivo.identificador]))
    b"".join(resposta.streaming_content)  # fecha o arquivo aberto pelo FileResponse

    assert resposta["Content-Disposition"].startswith("attachment")


# --- Regra 15: as telas apontam para a rota protegida ----------------------


@pytest.mark.django_db
def test_tela_do_entregavel_linka_o_arquivo(client, anexo, aluno):
    client.force_login(aluno)

    resposta = client.get(reverse("entregavel", args=[anexo.entregavel.pk]))

    assert reverse("baixar", args=[anexo.arquivo.identificador]) in resposta.content.decode()


@pytest.mark.django_db
def test_tela_de_revisao_linka_o_arquivo(client, anexo, professor):
    client.force_login(professor)

    resposta = client.get(reverse("revisar", args=[anexo.entregavel.pk]))

    assert reverse("baixar", args=[anexo.arquivo.identificador]) in resposta.content.decode()


@pytest.mark.django_db
def test_anexo_de_link_continua_apontando_para_fora(client, dados_curso, aluno):
    """A rota protegida e para arquivo nosso; anexo de link (TipoMidia.LINK) nao
    tem Arquivo e continua indo para o endereco de terceiro."""
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    anexo = Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.LINK, titulo="Vídeo externo",
        url="https://exemplo.ufsm.br/aula", enviado_por=aluno,
    )
    client.force_login(aluno)

    corpo = client.get(reverse("entregavel", args=[slides.pk])).content.decode()

    assert "https://exemplo.ufsm.br/aula" in corpo
    assert anexo.titulo in corpo
