"""Testes dos artefatos de produção.

**O que estes testes provam e o que não provam.** Todos eles leem arquivos do
repositório. Eles garantem que o `deploy/` versionado está certo — não que o
servidor no ar esteja rodando esses arquivos. As duas conferências que só um
servidor de verdade dá (o `internal;` do nginx e a restauração do backup) estão
em `docs/operacao.md` como passos que o operador executa, e não têm, nem podem
ter, teste aqui.
"""

import os
import re
from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.views.defaults import page_not_found, permission_denied, server_error

from django.conf import settings

RAIZ = Path(settings.BASE_DIR)
DEPLOY = RAIZ / "deploy"
TEMPLATES = RAIZ / "templates"


def sem_comentarios(texto):
    """Comentário não configura nada: um `internal;` comentado tem que reprovar.

    Vale para nginx, crontab, shell e .env — todos comentam com `#`. Sem isto,
    metade destes testes passaria só porque a diretiva aparece no comentário que
    a explica; foi assim, aliás, que este arquivo estava quando foi escrito.
    """
    return "\n".join(linha.split("#")[0] for linha in texto.splitlines())


def bloco(conf, cabecalho):
    """Recorta o corpo de um bloco do nginx contando chaves.

    Afirmar sobre o arquivo inteiro é o defeito que o relatório da Task 4
    previu: com `assert "internal;" in conf`, mover a diretiva para o
    `location /static/` deixa o teste verde e o `/protegido/` escancarado.
    """
    conf = sem_comentarios(conf)
    assert cabecalho in conf, f"{cabecalho!r} não existe no nginx.conf"
    inicio = conf.index(cabecalho) + len(cabecalho)
    profundidade = 1
    for i in range(inicio, len(conf)):
        if conf[i] == "{":
            profundidade += 1
        elif conf[i] == "}":
            profundidade -= 1
            if profundidade == 0:
                return conf[inicio:i]
    raise AssertionError(f"o bloco {cabecalho!r} não fecha")


@pytest.fixture
def nginx():
    return (DEPLOY / "nginx.conf").read_text()


# --- nginx: a entrega protegida ---------------------------------------------


def test_nginx_marca_a_midia_como_internal(nginx):
    """Sem internal, a URL direta burla toda a checagem de permissão (spec 10).

    A afirmação é sobre o CORPO do location /protegido/, não sobre o arquivo:
    é a única forma de o teste morrer quando a diretiva muda de bloco.
    """
    assert "internal;" in bloco(nginx, "location /protegido/ {")


def test_o_internal_nao_vale_em_outro_bloco(nginx):
    """O modo de falha previsto: `internal;` migra para o /static/, o arquivo
    inteiro continua contendo a palavra, e o material fica público."""
    assert "internal;" not in bloco(nginx, "location /static/ {")


def test_o_bloco_protegido_aponta_para_o_media(nginx):
    """O alias tem que ser o MEDIA_ROOT do servidor; errar aqui dá 404 em todo
    download com a suíte verde. O teste prende a forma (termina em /media/);
    conferir o caminho real é passo de docs/operacao.md."""
    corpo = bloco(nginx, "location /protegido/ {")
    assert re.search(r"alias\s+\S*/media/;", corpo), corpo


def test_nao_existe_rota_publica_para_a_midia(nginx):
    """Anexo de curso em produção não é servido por MEDIA_URL (spec 10). Um
    `location /media/` reabriria por fora tudo o que o /protegido/ fecha."""
    assert "location /media/" not in sem_comentarios(nginx)


# --- nginx: upload, timeouts e cabeçalhos ------------------------------------


def test_nginx_aceita_o_bloco_de_upload(nginx):
    """client_max_body_size precisa ser >= o teto do Django, senão o nginx corta
    antes com 413 e a mensagem da aplicação nunca chega ao navegador."""
    achado = re.search(r"client_max_body_size\s+(\d+)M;", nginx)
    assert achado, "client_max_body_size ausente ou em outra unidade"
    assert int(achado.group(1)) * 1024 * 1024 >= settings.DATA_UPLOAD_MAX_MEMORY_SIZE


def test_o_timeout_do_gunicorn_nao_e_menor_que_o_do_nginx(nginx):
    """Se o worker morre antes de o proxy desistir, o upload de um bloco de 5 MB
    numa conexão ruim vira 502 no meio."""
    proxy = int(re.search(r"proxy_read_timeout\s+(\d+)s;", nginx).group(1))
    servico = (DEPLOY / "integrasi.service").read_text()
    gunicorn = int(re.search(r"--timeout (\d+)", servico).group(1))
    assert gunicorn >= proxy


def test_o_proxy_sobrescreve_o_x_forwarded_for(nginx):
    """`$proxy_add_x_forwarded_for` ACRESCENTA o IP real ao que o cliente mandou;
    o cabeçalho chega como "9.9.9.9, <ip real>" e continua contendo texto do
    atacante. Com `$remote_addr` ele tem um elemento só, e é nosso (spec 10)."""
    corpo = bloco(nginx, "location / {")
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in corpo
    assert "$proxy_add_x_forwarded_for" not in sem_comentarios(nginx)


def test_o_proxy_repassa_o_esquema(nginx):
    """SECURE_PROXY_SSL_HEADER lê X-Forwarded-Proto. Sem este cabeçalho, o Django
    acha que a requisição é http, redireciona para https, o nginx repassa em http
    de novo, e o navegador entra em laço de redirecionamento."""
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in bloco(nginx, "location / {")


def test_http_vai_para_https(nginx):
    """HTTPS obrigatório (spec 13). A porta 80 existe só para redirecionar."""
    conf = sem_comentarios(nginx)
    assert "listen 80;" in conf
    assert "return 301 https://$host$request_uri;" in conf


# --- systemd -----------------------------------------------------------------


def test_o_servico_sobe_o_gunicorn_com_o_ambiente_do_arquivo():
    servico = sem_comentarios((DEPLOY / "integrasi.service").read_text())
    assert "gunicorn config.wsgi:application" in servico
    # Configuração vem toda de variável de ambiente (CLAUDE.md); sem
    # EnvironmentFile o serviço sobe sem SECRET_KEY e sem DATABASE_URL.
    assert "EnvironmentFile=/srv/integrasi/.env" in servico
    assert "Restart=always" in servico


def test_gunicorn_esta_nas_dependencias():
    """Na lista de dependências, não no comentário ao lado dela."""
    assert re.search(r'^\s*"gunicorn', (RAIZ / "pyproject.toml").read_text(), re.MULTILINE)


# --- cron --------------------------------------------------------------------


@pytest.fixture
def crontab():
    return (DEPLOY / "crontab").read_text()


def tarefas(crontab):
    """Só as linhas de tarefa: o comentário do arquivo cita as rotinas pelo nome,
    e um grep no arquivo inteiro continuaria verde com a linha do cron apagada."""
    return [
        linha
        for linha in sem_comentarios(crontab).splitlines()
        if linha.strip() and "MAILTO" not in linha
    ]


@pytest.mark.parametrize(
    "rotina", ["enviar_notificacoes", "limpar_uploads", "limpar_arquivos_orfaos"]
)
def test_cron_tem_as_tres_rotinas(crontab, rotina):
    assert any(rotina in linha for linha in tarefas(crontab))


def test_cron_roda_o_backup(crontab):
    assert any("backup.sh" in linha for linha in tarefas(crontab))


def test_o_erro_de_uma_rotina_vira_alerta(crontab):
    """Decisão desta tarefa (a Task 7 deixou em aberto): o stderr das rotinas é o
    alerta. Um PermissionError dentro do on_commit de limpar_arquivos_orfaos
    apaga as linhas e deixa os bytes órfãos no disco, sem nada apontando para
    eles; com `2>&1` o traceback iria para um arquivo que ninguém lê. Sem
    redirecionar o stderr, o cron manda por e-mail para o MAILTO."""
    linhas = tarefas(crontab)
    assert linhas, "nenhuma tarefa no crontab"
    assert re.search(r"^MAILTO=\S+@\S+$", crontab, re.MULTILINE), "sem destinatário de alerta"
    for linha in linhas:
        assert "2>&1" not in linha, f"stderr enterrado no log, sem alerta: {linha}"


# --- backup ------------------------------------------------------------------


def test_backup_cobre_banco_e_midia():
    """São dois problemas distintos (spec 13): pg_dump salva de erro humano, a
    cópia incremental salva a mídia, que é grande e cresce.

    A afirmação é sobre os COMANDOS, no início da linha. `"restic" in script`
    — como este teste estava — continuava verde com os dois `restic` apagados,
    porque a palavra sobrevivia dentro de `.restic-senha`: a campanha de
    deleção pegou isso, a enumeração de regras não pegaria."""
    script = sem_comentarios((DEPLOY / "backup.sh").read_text())
    assert re.search(r"(?m)^pg_dump\b", script)
    assert re.search(r"(?m)^restic backup\b", script)


def test_o_repositorio_da_midia_nao_cresce_para_sempre():
    """Sem `restic forget`, o repositório externo acumula todo instantâneo já
    feito e um dia o backup para por falta de espaço lá."""
    script = sem_comentarios((DEPLOY / "backup.sh").read_text())
    assert re.search(r"(?m)^restic forget\b.*--keep-daily", script)


def test_backup_guarda_o_banco_por_trinta_dias():
    """Retenção declarada de 30 dias (spec 13): sem o `find -mtime`, o disco de
    backup enche e o backup para de acontecer."""
    script = sem_comentarios((DEPLOY / "backup.sh").read_text())
    assert re.search(r"find .*-mtime \+30 -delete", script)


def test_o_backup_para_no_primeiro_erro():
    """Sem `set -e`, um pg_dump que falha ainda deixa o restic rodar em seguida e
    o script termina com sucesso: o operador acha que tem backup e não tem."""
    assert "set -euo pipefail" in sem_comentarios((DEPLOY / "backup.sh").read_text())


def test_a_restauracao_de_teste_confere_banco_e_midia():
    """Backup que nunca foi restaurado não é backup (spec 13)."""
    script = sem_comentarios((DEPLOY / "restaurar-teste.sh").read_text())
    assert re.search(r"(?m)^createdb\b", script)
    # O dump entra mesmo no banco: um `psql` qualquer não basta, o script tem
    # outros dois só para contar linhas depois.
    assert re.search(r"gunzip -c .*\| psql", script)
    assert re.search(r"(?m)^restic restore\b", script)


@pytest.mark.parametrize("script", ["backup.sh", "restaurar-teste.sh"])
def test_os_scripts_sao_executaveis(script):
    """O cron chama backup.sh direto, sem `bash` na frente."""
    assert os.access(DEPLOY / script, os.X_OK), f"{script} sem bit de execução"


# --- .env.example ------------------------------------------------------------


@pytest.mark.parametrize(
    "chave",
    [
        "SECRET_KEY",
        "DATABASE_URL",
        "ALLOWED_HOSTS",
        "USAR_X_ACCEL",
        "SEGURANCA_HTTPS",
        "CONFIAR_NO_PROXY",
    ],
)
def test_env_example_documenta_as_chaves(chave):
    """Como linha de atribuição, não como menção no comentário que a explica."""
    exemplo = (RAIZ / ".env.example").read_text()
    assert re.search(rf"^{chave}=", exemplo, re.MULTILINE)


# --- páginas de erro (spec 11) -----------------------------------------------


@pytest.mark.parametrize("codigo", ["403", "404"])
def test_paginas_de_erro_herdam_a_base(codigo):
    conteudo = (TEMPLATES / f"{codigo}.html").read_text()
    assert "{% extends" in conteudo
    assert "Traceback" not in conteudo


def test_a_pagina_500_nao_depende_de_nada():
    """Não estende base.html e não usa tag de template nenhuma: o 500 aparece
    justamente quando o banco, o context processor ou o static pararam. Um
    template que dependa de qualquer um deles falha de novo, e o visitante vê a
    página branca do servidor."""
    quinhentos = (TEMPLATES / "500.html").read_text()
    assert "{%" not in quinhentos
    assert "<!doctype html>" in quinhentos.lower()


def test_a_pagina_403_renderiza(rf):
    resposta = permission_denied(rf.get("/qualquer"), PermissionDenied())
    conteudo = resposta.content.decode()
    assert resposta.status_code == 403
    # Uma frase do CORPO, não do título: a página tem que dizer a quem recorrer
    # (spec 11), e não só trocar o texto do cabeçalho.
    assert "coordenação" in conteudo
    assert "Traceback" not in conteudo


def test_a_pagina_404_renderiza(rf):
    resposta = page_not_found(rf.get("/qualquer"), Http404())
    conteudo = resposta.content.decode()
    assert resposta.status_code == 404
    assert "saiu do catálogo" in conteudo
    assert "Ver os cursos disponíveis" in conteudo


def test_a_pagina_500_renderiza_sem_request(rf):
    """`server_error` renderiza o template SEM request de propósito. Se o 500.html
    precisasse de um context processor, é aqui que o erro apareceria."""
    resposta = server_error(rf.get("/qualquer"))
    assert resposta.status_code == 500
    assert "algo deu errado" in resposta.content.decode().lower()


# --- docs/operacao.md --------------------------------------------------------
# Estes testes são grep no repositório. Eles não provam que o passo foi
# executado no servidor; provam que o passo não sumiu do roteiro.


@pytest.fixture
def operacao():
    return (RAIZ / "docs" / "operacao.md").read_text()


def test_operacao_manda_conferir_o_internal_no_servidor(operacao):
    """A única prova real do `internal;` é um curl contra o servidor no ar."""
    assert "/protegido/" in operacao
    assert "curl" in operacao


def test_operacao_instala_a_extensao_unaccent(operacao):
    """Dívida do Plano 1: a busca depende de `portugues_unaccent`, e a migração
    0008 roda `CREATE EXTENSION unaccent` — que exige privilégio no PostgreSQL.
    Sem isso o `migrate` falha na instalação."""
    assert "unaccent" in operacao
    assert "CREATE EXTENSION" in operacao


def test_operacao_manda_restaurar_o_backup(operacao):
    assert "restaurar-teste.sh" in operacao
