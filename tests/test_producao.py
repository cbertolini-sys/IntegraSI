"""Testes dos artefatos de produção.

**O que estes testes provam e o que não provam.** Quase todos leem arquivos do
repositório. Eles garantem que o `deploy/` versionado está certo - não que o
servidor no ar esteja rodando esses arquivos. A conferência que só um servidor de
verdade dá (o `internal;` do nginx, com um `curl` de fora) está em
`docs/operacao.md` como passo do operador, e não tem, nem pode ter, teste aqui.

A exceção é o drill de restauração: os testes do fim deste arquivo **executam**
`deploy/restaurar-teste.sh`, com `psql`, `dropdb` e `createdb` de mentira no
PATH. Grep não enxerga SIGPIPE nem `trap`, e era exatamente disso que o script
morria: até a revisão de branco ele abortava no meio, deixando o banco de teste
para trás, enquanto o teste que o cobria (um grep) passava.

O que continua sem teste é a outra metade inteira do backup. A mídia e o disco
são cobertos pelo **backup diário da VM, mantido pelo CPD da UFSM**, e nada aqui
alcança aquilo: conferi-lo é pedir uma restauração de teste ao CPD, e está em
`docs/operacao.md` como passo do operador. Se essa VM deixar de ser copiada, esta
suíte continua verde e o sistema fica sem backup de disco.
"""

import gzip
import os
import re
import subprocess
import time
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

    Vale para nginx, crontab, shell e .env - todos comentam com `#`. Sem isto,
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
    e um grep no arquivo inteiro continuaria verde com a linha do cron apagada.
    As atribuições de ambiente (MAILTO) também saem - elas são configuração do
    cron, não tarefa, e têm testes próprios."""
    return [
        linha
        for linha in sem_comentarios(crontab).splitlines()
        if linha.strip() and not re.match(r"^[A-Z_]+=", linha.strip())
    ]


@pytest.mark.parametrize(
    "rotina", ["enviar_notificacoes", "limpar_uploads", "limpar_arquivos_orfaos"]
)
def test_cron_tem_as_tres_rotinas(crontab, rotina):
    assert any(rotina in linha for linha in tarefas(crontab))


def test_o_envio_de_notificacoes_passa_a_cada_minuto(crontab):
    """Convite de primeiro acesso e coisa que se espera de olho na caixa. Com
    `*/5` a pessoa via "convite na fila" e cinco minutos de silencio, o que
    parece defeito - aconteceu em producao no primeiro convite de verdade.

    A afirmacao e sobre a LINHA da rotina, e nao sobre o arquivo conter `* * * * *`
    em algum lugar: outras rotinas tem cadencia propria, e um `in` no arquivo
    inteiro passaria verde com esta aqui de volta em `*/5`."""
    linha = next(l for l in tarefas(crontab) if "enviar_notificacoes" in l)
    assert linha.startswith("* * * * * "), linha


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


def test_backup_gera_o_dump_diario_do_banco():
    """A metade que este script cobre (spec 13): `pg_dump` salva de erro humano.
    A afirmação é sobre o COMANDO, no início da linha - a palavra "pg_dump"
    sobrevive nos comentários que explicam o script, e um `in` continuaria verde
    com a linha apagada."""
    script = sem_comentarios((DEPLOY / "backup.sh").read_text())
    assert re.search(r"(?m)^pg_dump\b", script)


def test_backup_guarda_o_banco_por_trinta_dias():
    """Retenção declarada de 30 dias (spec 13): sem o `find -mtime`, o disco de
    backup enche e o backup para de acontecer."""
    script = sem_comentarios((DEPLOY / "backup.sh").read_text())
    assert re.search(r"find .*-mtime \+30 -delete", script)


def test_o_backup_para_no_primeiro_erro():
    """Sem `set -e`, um `pg_dump` que falha ainda deixa a retenção apagar os dumps
    antigos em seguida e o script termina com sucesso: o operador acha que tem
    backup, e o que ele tem é um arquivo truncado no lugar do de ontem."""
    assert "set -euo pipefail" in sem_comentarios((DEPLOY / "backup.sh").read_text())


def test_a_restauracao_de_teste_confere_o_banco():
    """Backup que nunca foi restaurado não é backup (spec 13)."""
    script = sem_comentarios((DEPLOY / "restaurar-teste.sh").read_text())
    assert re.search(r"(?m)^createdb\b", script)
    # O dump entra mesmo no banco: um `psql` qualquer não basta, o script tem
    # outros dois só para contar linhas depois.
    assert re.search(r"gunzip -c .*\| psql", script)


@pytest.mark.parametrize("script", ["backup.sh", "restaurar-teste.sh"])
def test_os_scripts_sao_executaveis(script):
    """O cron chama backup.sh direto, sem `bash` na frente."""
    assert os.access(DEPLOY / script, os.X_OK), f"{script} sem bit de execução"


# --- o drill de restauração, executado de verdade -----------------------------
# Estes são os únicos testes deste arquivo que rodam o artefato em vez de lê-lo.

DRILL = DEPLOY / "restaurar-teste.sh"

STUB_DROPDB = """#!/usr/bin/env bash
echo "$@" >> "$REGISTRO_DROPDB"
"""

STUB_CREATEDB = """#!/usr/bin/env bash
exit 0
"""

# Finge o psql inclusive no defeito que importa: sem `-v ON_ERROR_STOP=1` ele sai
# 0 mesmo com erro de SQL no meio do dump. É esse comportamento que faz o teste do
# dump quebrado morrer quando a opção some do script.
STUB_PSQL = """#!/usr/bin/env bash
for arg in "$@"; do
  case "$arg" in
    "select count(*) from cursos_curso") echo "${STUB_CURSOS:-3}"; exit 0;;
    "select count(*) from contas_usuario") echo "${STUB_USUARIOS:-7}"; exit 0;;
  esac
done
cat > "${REGISTRO_PSQL:-/dev/null}"
if [ "${STUB_DUMP_QUEBRADO:-0}" = 1 ]; then
  echo "ERROR: syntax error at or near" >&2
  for arg in "$@"; do
    if [ "$arg" = "ON_ERROR_STOP=1" ]; then exit 1; fi
  done
fi
exit 0
"""


@pytest.fixture
def drill(tmp_path):
    """Devolve um executor do `restaurar-teste.sh` num mundo de mentira.

    Trinta dias de retenção diária são poucos arquivos; os 2000 dumps aqui são o
    que faz o `ls -t | head -1` da primeira linha do script chegar a levar
    SIGPIPE. O dump de verdade (gzip real, gunzip real) é o mais recente.
    """
    binarios = tmp_path / "bin"
    binarios.mkdir()
    for nome, corpo in [
        ("dropdb", STUB_DROPDB),
        ("createdb", STUB_CREATEDB),
        ("psql", STUB_PSQL),
    ]:
        stub = binarios / nome
        stub.write_text(corpo)
        stub.chmod(0o755)

    dumps = tmp_path / "sql"
    dumps.mkdir()
    antigo = time.time() - 86400
    for i in range(2000):
        velho = dumps / f"integrasi-2026{i:04d}.sql.gz"
        velho.write_bytes(b"")
        os.utime(velho, (antigo, antigo))
    with gzip.open(dumps / "integrasi-20260830.sql.gz", "wb") as saida:
        saida.write(
            b"-- dump do integrasi\n"
            b"CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public;\n"
            b"COMMENT ON EXTENSION unaccent IS 'text search dictionary';\n"
            b"SELECT 1;\n"
            # Linha de DADO com a mesma frase no meio: o filtro do drill nao pode
            # levar esta junto. Um titulo de curso pode conter qualquer texto.
            b"1\tCOMMENT ON EXTENSION como titulo de curso\t\n"
        )

    registro = tmp_path / "dropdb.log"

    def executar(**extra):
        ambiente = {
            **os.environ,
            "PATH": f"{binarios}:{os.environ['PATH']}",
            "INTEGRASI_BANCO_TESTE": "integrasi_restauracao",
            "INTEGRASI_BACKUP_SQL": str(dumps),
            "REGISTRO_DROPDB": str(registro),
            **extra,
        }
        # Passar None remove a variavel: e o unico jeito de o teste enxergar o
        # DEFAULT do script. Com a fixture sempre exportando, um teste sobre o nome
        # do banco confere o valor que ele mesmo forneceu.
        ambiente = {c: v for c, v in ambiente.items() if v is not None}
        return subprocess.run(
            ["bash", str(DRILL)], capture_output=True, text=True, env=ambiente
        )

    executar.registro = registro
    executar.dumps = dumps
    executar.tmp = tmp_path
    return executar


def test_o_drill_chega_ao_fim_e_diz_que_deu_certo(drill):
    """O achado da revisão: `find ... | head -3` sob `pipefail` matava o script
    com 141 antes da mensagem final, do `dropdb` e do `rm -rf`. O operador via o
    drill FALHAR justamente na entrega que a spec 13 chama de obrigatória."""
    resultado = drill()

    assert resultado.returncode == 0, resultado.stderr
    assert "concluida com sucesso" in resultado.stdout


def test_o_drill_apaga_o_banco_de_teste(drill):
    """Sem isto, cada semestre deixa um `integrasi_restauracao` no servidor."""
    drill()

    # Duas: a de antes de restaurar (linha 41) e a da limpeza (o trap). Afirmar
    # apenas que o nome APARECE deixa a limpeza solta -- a chamada pre-restauracao
    # roda antes de qualquer ponto de falha e sozinha satisfaz um `in`.
    assert len(drill.registro.read_text().splitlines()) == 2


def test_o_drill_limpa_mesmo_quando_reprova(drill):
    """Falhar no meio é o desfecho normal de um drill que está fazendo o trabalho
    dele: é justamente aí que a limpeza não pode ser pulada. O dump quebrado é o
    ponto de falha mais distante do fim que o drill tem, e portanto o que deixaria
    mais coisa para trás."""
    resultado = drill(STUB_DUMP_QUEBRADO="1")

    assert resultado.returncode != 0
    # A falha e depois do dropdb pre-restauracao, entao aqui tambem sao duas: se o
    # trap nao rodasse, seria uma so, e o banco de teste sobreviveria ao semestre.
    assert len(drill.registro.read_text().splitlines()) == 2


def test_o_drill_nao_manda_o_comentario_da_extensao_para_o_psql(drill):
    """`COMMENT ON EXTENSION` so o dono da extensao executa, e o dono é o
    `postgres` que a instalou no `template1`. Rodando como o papel da aplicação, o
    drill morria em "must be owner of extension unaccent" antes de restaurar uma
    linha. O `CREATE EXTENSION` ao lado dele continua passando: é ele que faz o
    resto do dump encontrar a configuração de texto."""
    registro = drill.tmp / "psql-recebeu.sql"
    resultado = drill(REGISTRO_PSQL=str(registro))

    assert resultado.returncode == 0, resultado.stderr
    recebido = registro.read_text()
    assert "COMMENT ON EXTENSION unaccent IS" not in recebido
    assert "CREATE EXTENSION IF NOT EXISTS unaccent" in recebido


def test_o_filtro_do_drill_nao_corta_linha_de_dado(drill):
    """O filtro é ancorado em `^` de propósito. Sem a âncora ele recusaria
    qualquer linha que contivesse a frase, e uma linha de COPY com um título de
    curso dentro sairia calada do banco restaurado: o drill diria "concluida com
    sucesso" tendo perdido dado, que é o desfecho exato que ele existe para
    impedir."""
    registro = drill.tmp / "psql-recebeu.sql"
    drill(REGISTRO_PSQL=str(registro))

    assert "COMMENT ON EXTENSION como titulo de curso" in registro.read_text()


def test_banco_restaurado_vazio_reprova(drill):
    """As contagens eram impressas e nunca conferidas: `0 cursos, 0 usuarios`
    terminava com "concluida com sucesso". Backup que nunca foi restaurado não é
    backup, e restauração que ninguém confere é a mesma coisa (spec 13)."""
    resultado = drill(STUB_USUARIOS="0")

    assert resultado.returncode != 0
    assert "concluida com sucesso" not in resultado.stdout
    assert "Restauracao vazia" in resultado.stderr


def test_dump_com_erro_de_sql_no_meio_reprova(drill):
    """`psql` sem `-v ON_ERROR_STOP=1` sai 0 com o dump quebrado, e nem `set -e`
    nem `pipefail` veem nada: a restauração parcial passava por completa."""
    resultado = drill(STUB_DUMP_QUEBRADO="1")

    assert resultado.returncode != 0
    assert "concluida com sucesso" not in resultado.stdout


def test_sem_dump_nenhum_o_drill_reprova(drill):
    """Proteger o `ls | head` do SIGPIPE com `|| true` não pode virar silêncio:
    sem dump, o script tem que dizer isso e sair."""
    vazio = drill.tmp / "sem-dumps"
    vazio.mkdir()

    resultado = drill(INTEGRASI_BACKUP_SQL=str(vazio))

    assert resultado.returncode != 0
    assert "nao ha o que restaurar" in resultado.stderr


def test_o_drill_nunca_derruba_o_banco_de_producao(drill):
    """A promessa do cabeçalho do script. Um `dropdb` com o nome errado num drill
    semestral é a pior forma possível de descobrir que o backup funciona.

    Roda com `INTEGRASI_BANCO_TESTE` **removida**, de propósito: é o default do
    script que precisa ser seguro, e é justamente ele que nenhum teste enxergava.
    Com a fixture exportando a variável, este teste conferia o valor que ele mesmo
    tinha fornecido - trocar o default do script para o banco de produção deixava
    a suíte inteira verde, este teste incluído.
    """
    drill(INTEGRASI_BANCO_TESTE=None)

    linhas = drill.registro.read_text().splitlines()
    assert linhas, "o drill não chamou dropdb nenhuma vez"
    for linha in linhas:
        alvo = linha.split()[-1]
        assert alvo == "integrasi_restauracao", f"dropdb em {alvo!r}"


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
    0008 roda `CREATE EXTENSION unaccent` - que exige privilégio no PostgreSQL.
    Sem isso o `migrate` falha na instalação."""
    assert "unaccent" in operacao
    assert "CREATE EXTENSION" in operacao


def test_operacao_manda_restaurar_o_backup(operacao):
    assert "restaurar-teste.sh" in operacao


def test_operacao_diz_quem_cobre_a_metade_que_o_backup_sh_nao_cobre(operacao):
    """`backup.sh` faz o `pg_dump` e mais nada. A outra metade da spec §13, salvar
    de perder a máquina, é o backup diário da VM mantido pelo CPD da UFSM: uma
    dependência externa que nenhum teste deste repositório alcança.

    Sem isto escrito, quem abrir o `backup.sh` daqui a dois anos vê um script que
    só copia o banco, o cron verde ao lado, e conclui que o sistema tem backup de
    disco. O aviso é a parte que salva, e por isso está afirmado junto: a ausência
    do backup do CPD não faz nenhum teste, nenhum drill e nenhum cron reprovar."""
    assert "CPD" in operacao
    assert "máquina virtual" in operacao
    assert "nada aqui avisa" in operacao


def test_o_cron_confere_a_entrega_protegida():
    """A checagem que a suite nao alcanca precisa acontecer sozinha em algum
    lugar. Sem esta linha no cron, ela depende de alguem lembrar."""
    crontab = (DEPLOY / "crontab").read_text()
    assert "conferir_entrega_protegida" in crontab
