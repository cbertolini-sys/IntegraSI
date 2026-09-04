import os
import subprocess
import sys

import pytest
from django.conf import settings


def _importar_settings_em_subprocesso(remover=(), acrescentar=None, expressao="settings.DEBUG"):
    """Importa config.settings num subprocesso com ambiente limpo, fora do
    alcance de pytest-django (que força settings.DEBUG = False para toda a
    sessão de testes via setup_test_environment()).

    `expressao` é o que o subprocesso imprime: qualquer setting cujo padrão
    dependa de DEBUG só pode ser observado assim."""
    ambiente = {k: v for k, v in os.environ.items() if k not in remover}
    ambiente["DJANGO_SETTINGS_MODULE"] = "config.settings"
    # Sem isto o `load_dotenv` do settings.py reabre o .env DESTA MAQUINA dentro
    # do subprocesso e repoe exatamente as variaveis que `remover` acabou de
    # tirar. O teste passava a medir o .env do desenvolvedor em vez do padrao do
    # codigo, e reprovava em qualquer instalacao que definisse SEGURANCA_HTTPS -
    # a do servidor, por exemplo, que roda sem TLS por decisao registrada.
    # SECRET_KEY e DATABASE_URL continuam vindo do ambiente herdado, que o
    # processo do pytest ja carregou.
    # Antes de `acrescentar`, para que um teste possa apontar para outro arquivo.
    ambiente["ARQUIVO_ENV"] = os.devnull
    ambiente.update(acrescentar or {})
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); from django.conf import settings; "
            f"print({expressao})",
        ],
        capture_output=True,
        text=True,
        env=ambiente,
    )


def test_debug_desligado_quando_a_variavel_nao_e_definida():
    """pytest-django força DEBUG=False durante os testes, então a única forma de
    verificar o padrão de produção é importar as settings fora dele."""
    resultado = _importar_settings_em_subprocesso(remover={"DEBUG"})
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


def test_banco_e_postgresql():
    assert "postgresql" in settings.DATABASES["default"]["ENGINE"]


def test_idioma_e_fuso_do_projeto():
    assert settings.LANGUAGE_CODE == "pt-br"
    assert settings.TIME_ZONE == "America/Sao_Paulo"
    assert settings.USE_TZ is True


def test_x_accel_nasce_ligado_quando_debug_esta_desligado():
    """Em produção quem transmite arquivo é o nginx (spec 8). O padrão precisa ser
    o seguro: quem esquecer de definir USAR_X_ACCEL no servidor não pode acabar
    com o Django transmitindo 1 GB de dentro de um worker."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG", "USAR_X_ACCEL"}, expressao="settings.USAR_X_ACCEL"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "True"


def test_x_accel_nasce_desligado_em_desenvolvimento():
    """Sem nginx na frente, um X-Accel-Redirect chega ao navegador como resposta
    vazia: na máquina de quem desenvolve, quem entrega é o próprio Django."""
    resultado = _importar_settings_em_subprocesso(
        remover={"USAR_X_ACCEL"}, acrescentar={"DEBUG": "True"}, expressao="settings.USAR_X_ACCEL"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


# --- Segurança de produção ----------------------------------------------------
# Dívida registrada no CLAUDE.md desde o Plano 1: "Segurança de produção (HTTPS,
# cookies seguros, HSTS) é do Plano 4, dono do deploy". Como o padrão depende de
# DEBUG, e pytest-django força DEBUG=False na sessão inteira, a única forma de
# observar o padrão é a mesma de USAR_X_ACCEL: importar as settings num
# subprocesso com ambiente de produção.

SEGURANCA_EM_PRODUCAO = {
    "SECURE_SSL_REDIRECT": "True",
    "SESSION_COOKIE_SECURE": "True",
    "CSRF_COOKIE_SECURE": "True",
    "SECURE_HSTS_SECONDS": "31536000",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": "True",
    "SECURE_HSTS_PRELOAD": "True",
    "SECURE_PROXY_SSL_HEADER": "('HTTP_X_FORWARDED_PROTO', 'https')",
}


@pytest.mark.parametrize("chave,esperado", sorted(SEGURANCA_EM_PRODUCAO.items()))
def test_seguranca_de_producao_nasce_ligada(chave, esperado):
    """Quem esquecer SEGURANCA_HTTPS no servidor não pode acabar servindo o
    sistema em http, com cookie de sessão viajando em claro e sem HSTS."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG", "SEGURANCA_HTTPS", "CONFIAR_NO_PROXY"},
        expressao=f"settings.{chave}",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == esperado


@pytest.mark.parametrize("chave", sorted(SEGURANCA_EM_PRODUCAO))
def test_seguranca_de_producao_nasce_desligada_em_desenvolvimento(chave):
    """Sem TLS na máquina de quem desenvolve, SECURE_SSL_REDIRECT devolveria 301
    para uma porta https que não existe: o runserver ficaria inutilizável."""
    resultado = _importar_settings_em_subprocesso(
        remover={"SEGURANCA_HTTPS", "CONFIAR_NO_PROXY"},
        acrescentar={"DEBUG": "True"},
        expressao=f"settings.{chave}",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() in ("False", "0", "None")


def test_a_seguranca_pode_ser_desligada_por_variavel():
    """Um servidor de homologação sem certificado precisa subir; o desligamento é
    explícito e por variável, nunca por acidente."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG"},
        acrescentar={"SEGURANCA_HTTPS": "False"},
        expressao="settings.SECURE_SSL_REDIRECT",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


def test_confiar_no_proxy_nasce_ligado_em_producao():
    """Atrás do nginx, REMOTE_ADDR é sempre 127.0.0.1: sem esta chave o limite por
    IP do formulário público viraria um limite global (spec 10)."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG", "CONFIAR_NO_PROXY"}, expressao="settings.CONFIAR_NO_PROXY"
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "True"


def test_confiar_no_proxy_nasce_desligado_em_desenvolvimento():
    """Sem proxy na frente, X-Forwarded-For é texto escrito pelo cliente."""
    resultado = _importar_settings_em_subprocesso(
        remover={"CONFIAR_NO_PROXY"},
        acrescentar={"DEBUG": "True"},
        expressao="settings.CONFIAR_NO_PROXY",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


# --- Rotas de autenticação que o projeto não desenhou -------------------------


@pytest.mark.django_db
def test_o_projeto_nao_expoe_rota_de_auth_que_nao_desenhou(client):
    """`include("django.contrib.auth.urls")` trazia cinco rotas públicas junto
    com o logout.

    A de recuperação de senha respondia 200 servindo o template do Django Admin
    (título "Recuperar senha | Site de administração do Django"), sem link em
    tela nenhuma, e mandava e-mail com `send_mail` direto - por fora da fila de
    `notificacoes`, que existe para SMTP fora do ar não derrubar operação. A de
    troca de senha duplicava o que /perfil/ faz com a marca do sistema.
    """
    for rota in (
        "/contas/password_reset/",
        "/contas/password_reset/done/",
        "/contas/reset/done/",
        "/contas/password_change/",
        "/contas/password_change/done/",
    ):
        assert client.get(rota).status_code == 404, rota


@pytest.mark.django_db
def test_o_logout_continua_de_pe(client, django_user_model):
    """O `include` saiu, mas o logout era o único nome dele que o sistema usa:
    `base.html` o chama por `{% url 'logout' %}` e `LOGOUT_REDIRECT_URL` aponta
    para o login."""
    from django.urls import reverse

    pessoa = django_user_model.objects.create_user(
        email="sai@ufsm.br", nome_completo="Quem Sai", cpf="529.982.247-25",
        papel="COORDENADOR", siape="7654321", password="senha-de-teste-123",
    )
    client.force_login(pessoa)
    resposta = client.post(reverse("logout"), follow=True)
    assert resposta.status_code == 200
    assert not resposta.context["user"].is_authenticated


# --- Log e aviso de erro ------------------------------------------------------


def test_sem_a_variavel_o_projeto_sobe_sem_log_de_arquivo():
    """Ligado por variável, e não por `not DEBUG` como as três chaves de
    segurança: aquelas produzem a configuração SEGURA quando esquecidas, esta
    abre um arquivo no disco. Caminho errado, diretório inexistente ou sem
    permissão fazem o processo não subir, porque o handler é construído na carga
    das settings. Melhor ficar sem log do que não subir."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG", "CAMINHO_DO_LOG"},
        expressao="bool(getattr(settings, 'LOGGING', None))",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


def test_com_a_variavel_o_erro_vai_para_arquivo_e_para_os_admins(tmp_path):
    """Antes, `django.request` ficava com o padrão do Django: stderr e um
    `AdminEmailHandler` apontando para ADMINS vazio. Um 500 não deixava rastro em
    arquivo nenhum e não avisava ninguém."""
    caminho = tmp_path / "integrasi.log"
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG"},
        acrescentar={"CAMINHO_DO_LOG": str(caminho), "ADMINS": "Ops:ops@ufsm.br"},
        expressao=(
            "(settings.ADMINS, "
            "[h['class'] for h in settings.LOGGING['handlers'].values()], "
            "settings.LOGGING['loggers']['django.request']['handlers'])"
        ),
    )
    assert resultado.returncode == 0, resultado.stderr
    admins, classes, do_request = eval(resultado.stdout)
    assert admins == [("Ops", "ops@ufsm.br")]
    assert "logging.handlers.RotatingFileHandler" in classes
    assert "django.utils.log.AdminEmailHandler" in classes
    assert set(do_request) == {"arquivo", "email_admin"}


def test_o_email_de_erro_nao_leva_o_traceback_em_html(tmp_path):
    """`include_html` do `AdminEmailHandler` monta o traceback com as VARIÁVEIS
    LOCAIS de cada quadro, e nesta base as locais de uma view de convite ou de
    perfil carregam CPF, e-mail e telefone de terceiro (spec 10). Ligado, o
    sistema mandaria dado pessoal por e-mail a cada erro."""
    resultado = _importar_settings_em_subprocesso(
        remover={"DEBUG"},
        acrescentar={"CAMINHO_DO_LOG": str(tmp_path / "x.log"), "ADMINS": "Ops:ops@ufsm.br"},
        expressao="settings.LOGGING['handlers']['email_admin'].get('include_html')",
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "False"


# --- Verificação de saúde -----------------------------------------------------


@pytest.mark.django_db
def test_a_verificacao_de_saude_responde_sem_login(client):
    """Pública de propósito: monitoração não faz login, e a rota não diz nada que
    já não se saiba de fora. Restringir, se for o caso, é trabalho do nginx."""
    from django.urls import reverse

    resposta = client.get(reverse("saude"))
    assert resposta.status_code == 200
    assert resposta.content == b"ok"


@pytest.mark.django_db
def test_a_verificacao_de_saude_toca_o_banco(client):
    """Um 200 de graça é pior que rota nenhuma: a monitoração passaria a dizer
    que está tudo bem com o banco fora do ar, que é justamente o caso que o
    `Restart=always` do systemd não enxerga (processo vivo e inútil)."""
    from unittest import mock

    from django.urls import reverse

    with mock.patch(
        "django.db.connection.ensure_connection", side_effect=Exception("sem banco")
    ):
        resposta = client.get(reverse("saude"))
    assert resposta.status_code == 503


@pytest.mark.django_db
def test_a_saude_nao_conta_o_que_deu_errado(client):
    """A mensagem do banco é informação de dentro do servidor. Quem monitora
    precisa do código de status; o traceback vai para o log."""
    from unittest import mock

    from django.urls import reverse

    with mock.patch(
        "django.db.connection.ensure_connection",
        side_effect=Exception("FATAL: password authentication failed for user"),
    ):
        corpo = client.get(reverse("saude")).content.decode()
    assert "password" not in corpo
    assert "FATAL" not in corpo


def test_o_arquivo_de_ambiente_pode_ser_apontado_por_variavel(tmp_path):
    """`ARQUIVO_ENV` e o que permite aos testes de seguranca acima observarem o
    PADRAO do codigo em vez do .env desta maquina.

    Sem esta afirmacao, apagar o suporte no settings.py so reprovaria em maquinas
    cujo .env por acaso definisse a variavel em questao - passaria verde aqui e
    quebraria no servidor, que e exatamente o defeito que o suporte corrige.
    """
    alternativo = tmp_path / "outro.env"
    alternativo.write_text("ALLOWED_HOSTS=so.deste.arquivo\n")

    resultado = _importar_settings_em_subprocesso(
        remover={"ALLOWED_HOSTS"},
        acrescentar={"ARQUIVO_ENV": str(alternativo)},
        expressao="settings.ALLOWED_HOSTS",
    )

    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "['so.deste.arquivo']"
