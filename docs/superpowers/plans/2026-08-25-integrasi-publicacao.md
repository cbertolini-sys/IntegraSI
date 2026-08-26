# IntegraSI — Plano 3: Publicação, Catálogo e Demanda

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar o ciclo: o professor submete o curso pronto, o coordenador publica, o curso aparece num catálogo público com busca, e um interessado externo solicita a realização — o que vira uma turma agendada dentro do sistema.

**Architecture:** `catalogo` é um app somente-leitura sobre `cursos` que também recebe as solicitações externas; `turmas` nasce de uma solicitação aceita e é a fronteira com o futuro módulo de execução; `notificacoes` é uma fila em tabela esvaziada por cron, para que SMTP fora do ar nunca trave uma aprovação.

**Tech Stack:** Django 5.x, PostgreSQL 16 (busca de texto completo com dicionário português), pytest + pytest-django, HTMX.

**Spec:** `docs/superpowers/specs/2026-08-25-integrasi-design.md`

**Depende de:** Planos 1 e 2 completos.

## Global Constraints

- Módulo de produção apenas. `Turma` e `Participante` ficam na forma mínima: agendamento e lista. **Nenhum campo de frequência, nota ou certificado** — qualquer um deles é sinal de que a fronteira do §1.1 foi atravessada.
- `turmas` lê `cursos`; `cursos` e `catalogo` **não** conhecem `turmas`.
- Só `services.py` altera campo de status; toda transição em `transaction.atomic` (spec §7.2, §5).
- Somente o coordenador publica, devolve ou despublica (spec §5).
- Visitante enxerga exclusivamente cursos `PUBLICADO` (spec §10).
- Nenhum filtro ou tela pode pressupor BNCC; público-alvo é o filtro que sempre funciona (spec §4.2, §4.4).
- Dados de solicitantes e participantes são de terceiros: finalidade declarada no formulário, acesso restrito ao professor da turma e ao coordenador (spec §10).
- E-mail nunca é enviado dentro da requisição que muda estado (spec §9).
- **Enumere as regras da tarefa antes de conferir os testes contra elas**, e prove cada teste de invariante quebrando a guarda que ele prende. Partir dos testes só acha teste fraco; partir das regras também acha regra sem teste. Ver `CLAUDE.md`, seção Testes — o padrão apareceu sete vezes no Plano 2.

---

### Task 1: Fila de notificações

**Files:**
- Create: `apps/notificacoes/` (app completo), `apps/notificacoes/models.py`, `apps/notificacoes/services.py`, `apps/notificacoes/management/commands/enviar_notificacoes.py`
- Modify: `config/settings.py` (INSTALLED_APPS, e-mail)
- Test: `apps/notificacoes/tests/__init__.py`, `apps/notificacoes/tests/test_fila.py`

**Interfaces:**
- Consumes: nada.
- Produces: `apps.notificacoes.models.Notificacao` (`destinatario`, `assunto`, `corpo`, `evento`, `tentativas`, `enviado_em`, `ultimo_erro`, `criado_em`); `apps.notificacoes.services.enfileirar(evento, destinatarios, assunto, corpo) -> list[Notificacao]`; comando `python manage.py enviar_notificacoes [--lote N]`; constante `LIMITE_TENTATIVAS = 5`.

- [ ] **Step 1: Criar o app**

```bash
mkdir -p apps/notificacoes/tests apps/notificacoes/management/commands
python manage.py startapp notificacoes apps/notificacoes
touch apps/notificacoes/tests/__init__.py apps/notificacoes/management/__init__.py apps/notificacoes/management/commands/__init__.py
```

Em `apps/notificacoes/apps.py`, troque `name = "notificacoes"` por `name = "apps.notificacoes"`, e acrescente `"apps.notificacoes"` a `INSTALLED_APPS`.

Em `config/settings.py`, depois de `MEDIA_ROOT`:

```python
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "integrasi@ufsm.br")
```

E ao `.env.example`:

```
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=integrasi@ufsm.br
```

- [ ] **Step 2: Escrever o teste (vai falhar)**

`apps/notificacoes/tests/test_fila.py`:

```python
from unittest import mock

import pytest
from django.core import mail
from django.core.management import call_command

from apps.notificacoes import services
from apps.notificacoes.models import Notificacao


@pytest.mark.django_db
def test_enfileirar_cria_uma_notificacao_por_destinatario():
    services.enfileirar(
        evento="ENTREGAVEL_DEVOLVIDO",
        destinatarios=["a@ufsm.br", "b@ufsm.br"],
        assunto="Entregavel devolvido",
        corpo="Confira a devolutiva.",
    )
    assert Notificacao.objects.count() == 2
    assert Notificacao.objects.filter(enviado_em__isnull=True).count() == 2


@pytest.mark.django_db
def test_enfileirar_ignora_destinatario_vazio():
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br", "", None], assunto="A", corpo="B")
    assert Notificacao.objects.count() == 1


@pytest.mark.django_db
def test_comando_envia_e_marca_como_enviada(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="Assunto", corpo="Corpo")
    call_command("enviar_notificacoes")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "Assunto"
    assert Notificacao.objects.filter(enviado_em__isnull=False).count() == 1


@pytest.mark.django_db
def test_comando_respeita_o_tamanho_do_lote(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(
        evento="X", destinatarios=[f"a{n}@ufsm.br" for n in range(5)], assunto="A", corpo="B"
    )
    call_command("enviar_notificacoes", lote=2)
    assert Notificacao.objects.filter(enviado_em__isnull=False).count() == 2


@pytest.mark.django_db
def test_falha_de_envio_registra_o_erro_e_nao_marca_como_enviada(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="A", corpo="B")
    with mock.patch("apps.notificacoes.management.commands.enviar_notificacoes.send_mail",
                    side_effect=OSError("smtp fora do ar")):
        call_command("enviar_notificacoes")
    notificacao = Notificacao.objects.get()
    assert notificacao.enviado_em is None
    assert notificacao.tentativas == 1
    assert "smtp" in notificacao.ultimo_erro


@pytest.mark.django_db
def test_notificacao_no_limite_de_tentativas_e_abandonada(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    services.enfileirar(evento="X", destinatarios=["a@ufsm.br"], assunto="A", corpo="B")
    Notificacao.objects.update(tentativas=services.LIMITE_TENTATIVAS)
    call_command("enviar_notificacoes")
    assert len(mail.outbox) == 0
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `pytest apps/notificacoes/tests -v`
Expected: FAIL — `ImportError: cannot import name 'enfileirar'`.

- [ ] **Step 4: Implementar o modelo e o serviço**

`apps/notificacoes/models.py`:

```python
from django.db import models


class Notificacao(models.Model):
    """Fila persistente de e-mail. A acao grava aqui e commita; o envio acontece
    depois, por cron. SMTP fora do ar nao pode travar uma aprovacao (spec 9)."""

    destinatario = models.EmailField("destinatario")
    assunto = models.CharField("assunto", max_length=200)
    corpo = models.TextField("corpo")
    evento = models.CharField("evento", max_length=50)
    tentativas = models.PositiveSmallIntegerField("tentativas", default=0)
    enviado_em = models.DateTimeField("enviado em", null=True, blank=True)
    ultimo_erro = models.TextField("ultimo erro", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "notificacao"
        verbose_name_plural = "notificacoes"
        ordering = ["criado_em"]
        indexes = [models.Index(fields=["enviado_em", "tentativas"])]

    def __str__(self):
        return f"{self.assunto} para {self.destinatario}"
```

`apps/notificacoes/services.py`:

```python
from apps.notificacoes.models import Notificacao

LIMITE_TENTATIVAS = 5


def enfileirar(evento, destinatarios, assunto, corpo):
    """Grava as notificacoes a enviar. Nunca envia dentro da requisicao."""
    unicos = sorted({d for d in destinatarios if d})
    return Notificacao.objects.bulk_create(
        [
            Notificacao(destinatario=d, assunto=assunto, corpo=corpo, evento=evento)
            for d in unicos
        ]
    )
```

- [ ] **Step 5: Implementar o comando**

`apps/notificacoes/management/commands/enviar_notificacoes.py`:

```python
import fcntl
from pathlib import Path

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notificacoes.models import Notificacao
from apps.notificacoes.services import LIMITE_TENTATIVAS

TRAVA = Path(settings.BASE_DIR) / "enviar_notificacoes.lock"


class Command(BaseCommand):
    help = "Envia as notificacoes pendentes. Rode por cron."

    def add_arguments(self, parser):
        parser.add_argument("--lote", type=int, default=50, help="Maximo de envios por execucao.")

    def handle(self, *args, **opcoes):
        with open(TRAVA, "w") as trava:
            try:
                # Sem a trava, uma execucao lenta se sobrepoe a seguinte e o mesmo
                # e-mail sai duas vezes (spec 9).
                fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.stdout.write("Outra execucao esta em andamento; saindo.")
                return
            self._enviar(opcoes["lote"])

    def _enviar(self, lote):
        pendentes = Notificacao.objects.filter(
            enviado_em__isnull=True, tentativas__lt=LIMITE_TENTATIVAS
        )[:lote]
        enviadas = 0
        for notificacao in pendentes:
            try:
                send_mail(
                    subject=notificacao.assunto,
                    message=notificacao.corpo,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[notificacao.destinatario],
                    fail_silently=False,
                )
            except Exception as erro:
                notificacao.tentativas += 1
                notificacao.ultimo_erro = str(erro)
                notificacao.save(update_fields=["tentativas", "ultimo_erro"])
                continue
            notificacao.enviado_em = timezone.now()
            notificacao.tentativas += 1
            notificacao.ultimo_erro = ""
            notificacao.save(update_fields=["enviado_em", "tentativas", "ultimo_erro"])
            enviadas += 1
        self.stdout.write(self.style.SUCCESS(f"{enviadas} notificacoes enviadas."))
```

- [ ] **Step 6: Migrar, rodar e commitar**

```bash
python manage.py makemigrations notificacoes
pytest apps/notificacoes/tests -v
echo "enviar_notificacoes.lock" >> .gitignore
git add apps/notificacoes config/settings.py .env.example .gitignore
git commit -m "feat(notificacoes): fila em tabela com envio por cron sob trava"
```

Expected: PASS (6 testes).

---

### Task 2: Submissão, publicação e histórico administrativo

**Files:**
- Create: `apps/cursos/models/historico.py`
- Modify: `apps/cursos/models/__init__.py`, `apps/cursos/services.py`, `apps/cursos/permissions.py`
- Test: `apps/cursos/tests/test_publicacao.py`

**Interfaces:**
- Consumes: `Curso`, `services`, `permissions` (Plano 2); `notificacoes.services.enfileirar` (Task 1).
- Produces: `apps.cursos.models.LogTransicaoCurso` (`curso`, `de_status`, `para_status`, `usuario`, `observacao`, `criado_em`); `services.submeter_ao_coordenador(curso, por)`, `services.publicar_curso(curso, por)`, `services.devolver_curso(curso, por, comentario)`, `services.despublicar_curso(curso, por, motivo)`; `permissions.pode_publicar(usuario) -> bool`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_publicacao.py`:

```python
import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel
from apps.cursos.models import LogTransicaoCurso
from apps.notificacoes.models import Notificacao


@pytest.fixture
def curso_pronto(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    return curso


@pytest.mark.django_db
def test_submeter_exige_os_cinco_aprovados(dados_curso, professor):
    curso = services.criar_curso(**dados_curso)
    with pytest.raises(ValidationError):
        services.submeter_ao_coordenador(curso, por=professor)


@pytest.mark.django_db
def test_submeter_muda_o_estado_e_registra_o_log(curso_pronto, professor):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.AGUARDANDO_COORDENADOR
    log = LogTransicaoCurso.objects.get(curso=curso_pronto)
    assert log.de_status == StatusCurso.EM_PRODUCAO
    assert log.usuario == professor


@pytest.mark.django_db
def test_submeter_revalida_os_dados_do_curso(curso_pronto, professor):
    """O curso pode ser editado depois do plano de ensino aprovado (spec 6)."""
    curso_pronto.carga_horaria = 1
    curso_pronto.save()
    curso_pronto.referencial = None
    curso_pronto.save()
    from apps.cursos.models import Curso

    Curso.objects.filter(pk=curso_pronto.pk).update(carga_horaria=None)
    curso_pronto.refresh_from_db()
    with pytest.raises(ValidationError):
        services.submeter_ao_coordenador(curso_pronto, por=professor)


@pytest.mark.django_db
def test_professor_nao_publica(curso_pronto, professor):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    with pytest.raises(PermissionDenied):
        services.publicar_curso(curso_pronto, por=professor)


@pytest.mark.django_db
def test_coordenador_publica_e_avisa_a_equipe(curso_pronto, professor, coordenador, aluno):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.PUBLICADO
    assert curso_pronto.publicado_em is not None
    destinatarios = set(Notificacao.objects.values_list("destinatario", flat=True))
    assert {aluno.email, professor.email} <= destinatarios


@pytest.mark.django_db
def test_publicar_curso_que_nao_foi_submetido_e_recusado(curso_pronto, coordenador):
    with pytest.raises(ValidationError):
        services.publicar_curso(curso_pronto, por=coordenador)


@pytest.mark.django_db
def test_devolver_ao_professor_exige_comentario(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    with pytest.raises(ValidationError):
        services.devolver_curso(curso_pronto, por=coordenador, comentario=" ")


@pytest.mark.django_db
def test_devolvido_volta_a_producao_ao_ser_submetido_de_novo(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.devolver_curso(curso_pronto, por=coordenador, comentario="Faltou detalhar o cronograma.")
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.DEVOLVIDO
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.AGUARDANDO_COORDENADOR


@pytest.mark.django_db
def test_despublicar_registra_o_motivo(curso_pronto, professor, coordenador):
    services.submeter_ao_coordenador(curso_pronto, por=professor)
    services.publicar_curso(curso_pronto, por=coordenador)
    services.despublicar_curso(curso_pronto, por=coordenador, motivo="Material desatualizado.")
    curso_pronto.refresh_from_db()
    assert curso_pronto.status == StatusCurso.DESPUBLICADO
    log = LogTransicaoCurso.objects.filter(para_status=StatusCurso.DESPUBLICADO).get()
    assert log.observacao == "Material desatualizado."
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_publicacao.py -v`
Expected: FAIL — `ImportError: cannot import name 'LogTransicaoCurso'`.

- [ ] **Step 3: Implementar o histórico**

`apps/cursos/models/historico.py`:

```python
from django.conf import settings
from django.db import models

from apps.cursos.choices import StatusCurso


class LogTransicaoCurso(models.Model):
    """Rastro administrativo das mudancas de situacao do curso. Responde
    'por que este curso saiu do ar?' seis meses depois (spec 11)."""

    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.CASCADE, related_name="transicoes", verbose_name="curso"
    )
    de_status = models.CharField("de", max_length=30, choices=StatusCurso.choices)
    para_status = models.CharField("para", max_length=30, choices=StatusCurso.choices)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="transicoes_de_curso"
    )
    observacao = models.TextField("observacao", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "transicao de curso"
        verbose_name_plural = "transicoes de curso"
        ordering = ["criado_em"]

    def __str__(self):
        return f"{self.curso}: {self.de_status} -> {self.para_status}"
```

Acrescente ao `apps/cursos/models/__init__.py` a importação de `LogTransicaoCurso` e o nome em `__all__`.

- [ ] **Step 4: Acrescentar as transições ao serviço**

Ao fim de `apps/cursos/services.py`:

```python
from django.utils import timezone

from apps.cursos.models import LogTransicaoCurso
from apps.notificacoes.services import enfileirar


def _transicionar(curso, para, por, observacao=""):
    de = curso.status
    curso.status = para
    if para == StatusCurso.PUBLICADO:
        curso.publicado_em = timezone.now()
    curso.save()
    LogTransicaoCurso.objects.create(
        curso=curso, de_status=de, para_status=para, usuario=por, observacao=observacao
    )


def _emails_da_equipe(curso):
    return [m.aluno.email for m in curso.membros.select_related("aluno")]


@transaction.atomic
def submeter_ao_coordenador(curso, por):
    permissions.garante(permissions.pode_gerir_equipe(por, curso), "Somente o professor responsavel submete.")
    if curso.status not in (StatusCurso.EM_PRODUCAO, StatusCurso.DEVOLVIDO):
        raise ValidationError("Este curso nao esta em producao.")
    if not curso.pronto_para_o_coordenador:
        raise ValidationError("Todos os cinco entregaveis precisam estar aprovados.")
    faltas = validacoes.dados_do_curso(curso)
    if faltas:
        raise ValidationError(faltas)
    _transicionar(curso, StatusCurso.AGUARDANDO_COORDENADOR, por)
    enfileirar(
        evento="CURSO_SUBMETIDO",
        destinatarios=_emails_dos_coordenadores(),
        assunto=f"Curso aguardando aprovacao: {curso.titulo}",
        corpo=f"O professor {por.nome_completo} submeteu o curso {curso.titulo} para aprovacao.",
    )
    return curso


@transaction.atomic
def publicar_curso(curso, por):
    permissions.garante(permissions.pode_publicar(por), "Somente o coordenador publica.")
    if curso.status != StatusCurso.AGUARDANDO_COORDENADOR:
        raise ValidationError("So se publica curso que foi submetido pelo professor.")
    _transicionar(curso, StatusCurso.PUBLICADO, por)
    enfileirar(
        evento="CURSO_PUBLICADO",
        destinatarios=_emails_da_equipe(curso) + [curso.professor_responsavel.email],
        assunto=f"Curso publicado: {curso.titulo}",
        corpo=f"O curso {curso.titulo} foi aprovado pela coordenacao e esta no catalogo publico.",
    )
    return curso


@transaction.atomic
def devolver_curso(curso, por, comentario):
    permissions.garante(permissions.pode_publicar(por), "Somente o coordenador devolve o curso.")
    if curso.status != StatusCurso.AGUARDANDO_COORDENADOR:
        raise ValidationError("So se devolve curso que esta aguardando aprovacao.")
    if not (comentario or "").strip():
        raise ValidationError("Escreva o que precisa ser corrigido antes de devolver.")
    _transicionar(curso, StatusCurso.DEVOLVIDO, por, observacao=comentario)
    enfileirar(
        evento="CURSO_DEVOLVIDO",
        destinatarios=[curso.professor_responsavel.email],
        assunto=f"Curso devolvido: {curso.titulo}",
        corpo=comentario,
    )
    return curso


@transaction.atomic
def despublicar_curso(curso, por, motivo):
    permissions.garante(permissions.pode_publicar(por), "Somente o coordenador despublica.")
    if curso.status != StatusCurso.PUBLICADO:
        raise ValidationError("Este curso nao esta publicado.")
    if not (motivo or "").strip():
        raise ValidationError("Informe o motivo da despublicacao.")
    _transicionar(curso, StatusCurso.DESPUBLICADO, por, observacao=motivo)
    return curso


def _emails_dos_coordenadores():
    from apps.contas.models import Usuario

    return list(
        Usuario.objects.filter(papel=Usuario.COORDENADOR, is_active=True).values_list("email", flat=True)
    )
```

Em `apps/cursos/permissions.py`:

```python
def pode_publicar(usuario):
    return usuario.e_coordenador
```

Em `apps/cursos/validacoes.py`, renomeie `_dados_do_curso` para `dados_do_curso` (sem sublinhado, porque agora é chamada de fora) e ajuste a chamada dentro de `_plano_de_ensino`.

- [ ] **Step 5: Migrar, rodar e commitar**

```bash
python manage.py makemigrations cursos
pytest apps/cursos/tests/test_publicacao.py -v
git add apps/cursos
git commit -m "feat(cursos): submissao, publicacao e historico administrativo"
```

Expected: PASS (9 testes).

---

### Task 3: Telas do coordenador

**Files:**
- Create: `apps/cursos/views/coordenador.py`, `templates/cursos/fila_coordenacao.html`, `templates/cursos/analisar_curso.html`
- Modify: `apps/cursos/views/__init__.py`, `apps/cursos/urls.py`, `apps/cursos/views/professor.py`, `templates/cursos/curso.html`, `templates/painel.html`
- Test: `apps/cursos/tests/test_views_coordenador.py`

**Interfaces:**
- Consumes: serviços da Task 2.
- Produces: rotas `fila_coordenacao`, `analisar_curso` (`<int:pk>`), `decidir_curso` (`<int:pk>`), `submeter_curso` (`<int:pk>`).

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_views_coordenador.py`:

```python
import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel


@pytest.fixture
def curso_submetido(dados_curso, aluno, professor):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    return curso


@pytest.mark.django_db
def test_professor_submete_pela_tela(client, dados_curso, aluno, professor):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    client.force_login(professor)
    client.post(reverse("submeter_curso", args=[curso.pk]), follow=True)
    curso.refresh_from_db()
    assert curso.status == StatusCurso.AGUARDANDO_COORDENADOR


@pytest.mark.django_db
def test_fila_da_coordenacao_lista_o_curso(client, coordenador, curso_submetido):
    client.force_login(coordenador)
    resposta = client.get(reverse("fila_coordenacao"))
    assert curso_submetido.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_professor_nao_entra_na_fila_da_coordenacao(client, professor, curso_submetido):
    client.force_login(professor)
    resposta = client.get(reverse("fila_coordenacao"))
    assert resposta.status_code == 403


@pytest.mark.django_db
def test_publicar_pela_tela(client, coordenador, curso_submetido):
    client.force_login(coordenador)
    client.post(reverse("decidir_curso", args=[curso_submetido.pk]), {"decisao": "PUBLICAR"}, follow=True)
    curso_submetido.refresh_from_db()
    assert curso_submetido.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_devolver_sem_comentario_e_barrado(client, coordenador, curso_submetido):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("decidir_curso", args=[curso_submetido.pk]),
        {"decisao": "DEVOLVER", "comentario": ""},
        follow=True,
    )
    assert "Escreva o que precisa ser corrigido" in resposta.content.decode()
    curso_submetido.refresh_from_db()
    assert curso_submetido.status == StatusCurso.AGUARDANDO_COORDENADOR


@pytest.mark.django_db
def test_analise_mostra_todos_os_entregaveis(client, coordenador, curso_submetido):
    client.force_login(coordenador)
    resposta = client.get(reverse("analisar_curso", args=[curso_submetido.pk]))
    assert resposta.content.decode().count("entregavel-analise") == 5
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_views_coordenador.py -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'submeter_curso' not found`.

- [ ] **Step 3: Escrever as views**

`apps/cursos/views/coordenador.py`:

```python
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.cursos import permissions, services
from apps.cursos.choices import StatusCurso
from apps.cursos.models import Curso


@login_required
def fila_coordenacao(request):
    permissions.garante(permissions.pode_publicar(request.user), "Area da coordenacao.")
    cursos = Curso.objects.filter(status=StatusCurso.AGUARDANDO_COORDENADOR).select_related(
        "professor_responsavel", "edicao"
    )
    return render(request, "cursos/fila_coordenacao.html", {"cursos": cursos})


@login_required
def analisar_curso(request, pk):
    permissions.garante(permissions.pode_publicar(request.user), "Area da coordenacao.")
    curso = get_object_or_404(Curso, pk=pk)
    return render(
        request,
        "cursos/analisar_curso.html",
        {"curso": curso, "entregaveis": curso.entregaveis.prefetch_related("secoes", "anexos")},
    )


@login_required
def decidir_curso(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    comentario = request.POST.get("comentario", "")
    try:
        if request.POST.get("decisao") == "PUBLICAR":
            services.publicar_curso(curso, por=request.user)
            messages.success(request, "Curso publicado no catalogo.")
        else:
            services.devolver_curso(curso, por=request.user, comentario=comentario)
            messages.success(request, "Curso devolvido ao professor.")
    except ValidationError as erro:
        messages.error(request, erro.messages[0])
        return redirect("analisar_curso", pk=curso.pk)
    return redirect("fila_coordenacao")
```

Em `apps/cursos/views/professor.py`, acrescente:

```python
@login_required
def submeter_curso(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    try:
        services.submeter_ao_coordenador(curso, por=request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, "Curso enviado para aprovacao da coordenacao.")
    return redirect("curso", pk=curso.pk)
```

Atualize `apps/cursos/views/__init__.py` acrescentando `analisar_curso`, `decidir_curso`, `fila_coordenacao` e `submeter_curso` às importações e ao `__all__`; e `apps/cursos/urls.py`:

```python
    path("cursos/<int:pk>/submeter/", views.submeter_curso, name="submeter_curso"),
    path("coordenacao/", views.fila_coordenacao, name="fila_coordenacao"),
    path("coordenacao/<int:pk>/", views.analisar_curso, name="analisar_curso"),
    path("coordenacao/<int:pk>/decidir/", views.decidir_curso, name="decidir_curso"),
```

- [ ] **Step 4: Escrever os templates**

`templates/cursos/fila_coordenacao.html`:

```html
{% extends "base.html" %}
{% block titulo %}Coordenacao{% endblock %}
{% block conteudo %}
  <h1>Cursos aguardando aprovacao</h1>
  {% for curso in cursos %}
    <article>
      <h2><a href="{% url 'analisar_curso' curso.pk %}">{{ curso.titulo }}</a></h2>
      <p>{{ curso.professor_responsavel.nome_completo }} &middot; {{ curso.edicao }} &middot; {{ curso.publico_alvo }}</p>
    </article>
  {% empty %}
    <p>Nenhum curso aguardando aprovacao.</p>
  {% endfor %}
{% endblock %}
```

`templates/cursos/analisar_curso.html`:

```html
{% extends "base.html" %}
{% block titulo %}Analisar {{ curso.titulo }}{% endblock %}
{% block conteudo %}
  <h1>{{ curso.titulo }}</h1>
  <p>{{ curso.publico_alvo }} &middot; {{ curso.carga_horaria }}h &middot; {{ curso.get_formato_display }}</p>
  <p>{{ curso.resumo }}</p>
  {% for mensagem in messages %}<p class="mensagem">{{ mensagem }}</p>{% endfor %}

  {% for entregavel in entregaveis %}
    <section class="entregavel-analise">
      <h2>{{ entregavel.get_tipo_display }} &mdash; {{ entregavel.get_status_display }}</h2>
      {% for secao in entregavel.secoes.all %}
        <h3>{{ secao.titulo }}</h3><div>{{ secao.conteudo|safe }}</div>
      {% endfor %}
      <ul>{% for anexo in entregavel.anexos.all %}<li>{{ anexo.titulo }}</li>{% endfor %}</ul>
    </section>
  {% endfor %}

  <form method="post" action="{% url 'decidir_curso' curso.pk %}">
    {% csrf_token %}
    <label for="comentario">Comentario</label>
    <textarea id="comentario" name="comentario" rows="5"></textarea>
    <button type="submit" name="decisao" value="PUBLICAR">Publicar</button>
    <button type="submit" name="decisao" value="DEVOLVER">Devolver ao professor</button>
  </form>
{% endblock %}
```

Em `templates/cursos/curso.html`, antes do fim do bloco:

```html
  {% if curso.pronto_para_o_coordenador and user == curso.professor_responsavel %}
    <form method="post" action="{% url 'submeter_curso' curso.pk %}">
      {% csrf_token %}
      <button type="submit">Submeter a coordenacao</button>
    </form>
  {% endif %}
```

Em `templates/painel.html`:

```html
  {% if user.e_coordenador %}
    <p><a href="{% url 'fila_coordenacao' %}">Fila da coordenacao</a></p>
  {% endif %}
```

- [ ] **Step 5: Rodar e commitar**

```bash
pytest apps/cursos/tests/test_views_coordenador.py -v
git add apps/cursos templates
git commit -m "feat(cursos): telas de submissao e aprovacao pela coordenacao"
```

Expected: PASS (6 testes).

---

### Task 4: Índice de busca

**Files:**
- Modify: `apps/cursos/models/curso.py`, `apps/cursos/services.py`, `config/settings.py`
- Create: `apps/cursos/migrations/XXXX_busca.py` (gerada), `apps/cursos/busca.py`
- Test: `apps/cursos/tests/test_busca.py`

**Interfaces:**
- Consumes: `Curso` (Plano 2).
- Produces: colunas `search_vector` (gerada, campos próprios) e `vetor_temas` (mantida por serviço) no `Curso`, ambas com índice GIN; `apps.cursos.busca.CONFIG_TEXTO = "portuguese"`, `apps.cursos.busca.buscar(queryset, termo)`; `services.definir_temas(curso, temas, por)`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_busca.py`:

```python
import pytest

from apps.cursos import busca, services
from apps.cursos.models import Curso, Tema


@pytest.fixture
def curso_robotica(dados_curso, professor):
    dados_curso.update(
        titulo="Robotica com sucata",
        resumo="Oficina de robotica de baixo custo para o 9o ano.",
        palavras_chave="arduino, motores, reciclagem",
        etapa_ano="EF09",
    )
    return services.criar_curso(**dados_curso)


@pytest.mark.django_db
def test_busca_encontra_pelo_titulo(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "robotica").count() == 1


@pytest.mark.django_db
def test_busca_ignora_acento_e_flexao(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "robótica").count() == 1
    assert busca.buscar(Curso.objects.all(), "oficinas").count() == 1


@pytest.mark.django_db
def test_busca_encontra_pela_palavra_chave(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "arduino").count() == 1


@pytest.mark.django_db
def test_busca_nao_encontra_o_que_nao_existe(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "astronomia").count() == 0


@pytest.mark.django_db
def test_busca_encontra_pelo_nome_do_tema(curso_robotica, professor):
    tema = Tema.objects.create(nome="Robotica Educacional")
    outro = Tema.objects.create(nome="Seguranca Digital")
    services.definir_temas(curso_robotica, [outro], por=professor)
    assert busca.buscar(Curso.objects.all(), "seguranca").count() == 1
    services.definir_temas(curso_robotica, [tema], por=professor)
    assert busca.buscar(Curso.objects.all(), "seguranca").count() == 0


@pytest.mark.django_db
def test_termo_vazio_devolve_tudo(curso_robotica):
    assert busca.buscar(Curso.objects.all(), "").count() == 1
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_busca.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.cursos.busca'`.

- [ ] **Step 3: Acrescentar as colunas ao modelo**

Em `config/settings.py`, acrescente a `INSTALLED_APPS`:

```python
    "django.contrib.postgres",
```

Em `apps/cursos/models/curso.py`, acrescente as importações e os campos:

```python
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db.models import F, Value
from django.db.models.functions import Coalesce
```

Dentro da classe `Curso`, junto aos demais campos:

```python
    # Coluna gerada: cobre os campos da propria linha. Coluna gerada nao faz JOIN,
    # entao os temas NAO cabem aqui e vivem em vetor_temas (spec 4.4).
    search_vector = models.GeneratedField(
        expression=SearchVector(
            Coalesce(F("titulo"), Value("")),
            Coalesce(F("resumo"), Value("")),
            Coalesce(F("palavras_chave"), Value("")),
            config="portuguese",
        ),
        output_field=SearchVectorField(),
        db_persist=True,
    )
    vetor_temas = SearchVectorField("vetor dos temas", null=True, editable=False)
```

E dentro de `class Meta`:

```python
        indexes = [
            GinIndex(fields=["search_vector"], name="curso_busca_idx"),
            GinIndex(fields=["vetor_temas"], name="curso_busca_temas_idx"),
        ]
```

- [ ] **Step 4: Escrever o módulo de busca e o serviço de temas**

`apps/cursos/busca.py`:

```python
from django.contrib.postgres.search import SearchQuery
from django.db.models import Q

CONFIG_TEXTO = "portuguese"


def buscar(queryset, termo):
    """Filtra pelo termo usando busca de texto completo em portugues.

    O dicionario portugues e o que faz 'robotica' encontrar 'robótica' e 'oficinas'
    encontrar 'oficina'; LIKE nao faz isso (spec 4.4). Termo vazio nao filtra nada.
    """
    termo = (termo or "").strip()
    if not termo:
        return queryset
    consulta = SearchQuery(termo, config=CONFIG_TEXTO)
    return queryset.filter(Q(search_vector=consulta) | Q(vetor_temas=consulta))
```

Ao fim de `apps/cursos/services.py`:

```python
from django.contrib.postgres.search import SearchVector

from apps.cursos.busca import CONFIG_TEXTO
from apps.cursos.models import Curso


@transaction.atomic
def definir_temas(curso, temas, por):
    """Troca os temas do curso e reindexa. A reindexacao e explicita porque coluna
    gerada nao alcanca M2M (spec 4.4)."""
    permissions.garante(permissions.pode_gerir_equipe(por, curso), "Curso de outro professor.")
    curso.temas.set(temas)
    atualizar_vetor_temas(curso)
    return curso


def atualizar_vetor_temas(curso):
    nomes = " ".join(curso.temas.values_list("nome", flat=True))
    Curso.objects.filter(pk=curso.pk).update(
        vetor_temas=SearchVector(models.Value(nomes), config=CONFIG_TEXTO)
    )
```

Acrescente `from django.db import models, transaction` ao topo de `services.py` se ainda não estiver lá.

**Quando um `Tema` é renomeado**, todos os cursos ligados a ele precisam ser reindexados. Acrescente ao `TemaAdmin` em `apps/cursos/admin.py`:

```python
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from apps.cursos.services import atualizar_vetor_temas

        for curso in obj.cursos.all():
            atualizar_vetor_temas(curso)
```

- [ ] **Step 5: Migrar, rodar e commitar**

```bash
python manage.py makemigrations cursos --name busca
pytest apps/cursos/tests/test_busca.py -v
git add apps/cursos config/settings.py
git commit -m "feat(cursos): busca de texto completo em portugues com temas indexados"
```

Expected: PASS (6 testes).

---

### Task 5: Catálogo público

**Files:**
- Create: `apps/catalogo/` (app completo), `apps/catalogo/views.py`, `apps/catalogo/urls.py`, `templates/catalogo/lista.html`, `templates/catalogo/curso.html`
- Modify: `config/settings.py`, `config/urls.py`, `templates/base.html`
- Test: `apps/catalogo/tests/__init__.py`, `apps/catalogo/tests/test_catalogo.py`

**Interfaces:**
- Consumes: `Curso`, `busca.buscar`, `Tema`, `Referencial` (Planos 1-2, Task 4).
- Produces: rotas públicas `catalogo` (`/`) e `catalogo_curso` (`/cursos/<int:pk>/publico/`); função `apps.catalogo.views.cursos_publicados() -> QuerySet`.

- [ ] **Step 1: Criar o app**

```bash
mkdir -p apps/catalogo/tests
python manage.py startapp catalogo apps/catalogo
touch apps/catalogo/tests/__init__.py
```

Em `apps/catalogo/apps.py`, troque `name = "catalogo"` por `name = "apps.catalogo"`, e acrescente `"apps.catalogo"` a `INSTALLED_APPS`.

- [ ] **Step 2: Escrever o teste (vai falhar)**

`apps/catalogo/tests/test_catalogo.py`:

```python
import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoPublico
from apps.cursos.models import Tema


def publica(curso, professor, coordenador):
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    return curso


@pytest.fixture
def curso_publicado(dados_curso, professor, coordenador):
    curso = services.criar_curso(**dados_curso)
    return publica(curso, professor, coordenador)


@pytest.mark.django_db
def test_catalogo_e_publico(client, curso_publicado):
    resposta = client.get(reverse("catalogo"))
    assert resposta.status_code == 200
    assert curso_publicado.titulo in resposta.content.decode()


@pytest.mark.django_db
def test_curso_em_producao_nao_aparece(client, dados_curso):
    curso = services.criar_curso(**dados_curso)
    resposta = client.get(reverse("catalogo"))
    assert curso.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_curso_despublicado_sai_do_catalogo(client, curso_publicado, coordenador):
    services.despublicar_curso(curso_publicado, por=coordenador, motivo="Desatualizado.")
    resposta = client.get(reverse("catalogo"))
    assert curso_publicado.titulo not in resposta.content.decode()


@pytest.mark.django_db
def test_pagina_publica_de_curso_nao_publicado_devolve_404(client, dados_curso):
    curso = services.criar_curso(**dados_curso)
    resposta = client.get(reverse("catalogo_curso", args=[curso.pk]))
    assert resposta.status_code == 404


@pytest.mark.django_db
def test_pagina_publica_mostra_dados_do_curso_e_nao_os_materiais(client, curso_publicado):
    resposta = client.get(reverse("catalogo_curso", args=[curso_publicado.pk]))
    conteudo = resposta.content.decode()
    assert curso_publicado.resumo in conteudo
    assert "Plano de Ensino" not in conteudo


@pytest.mark.django_db
def test_filtro_por_publico_alvo(client, curso_publicado, dados_curso, professor, coordenador):
    dados_curso.update(
        titulo="Cidadania digital para adultos", tipo_publico=TipoPublico.COMUNITARIO,
        etapa_ano="", publico_descricao="Adultos em vulnerabilidade digital",
    )
    publica(services.criar_curso(**dados_curso), professor, coordenador)

    resposta = client.get(reverse("catalogo"), {"etapa": "EF05"})
    conteudo = resposta.content.decode()
    assert curso_publicado.titulo in conteudo
    assert "Cidadania digital para adultos" not in conteudo


@pytest.mark.django_db
def test_filtro_por_tema(client, curso_publicado, professor):
    tema = Tema.objects.create(nome="Robotica Educacional")
    services.definir_temas(curso_publicado, [tema], por=professor)
    assert curso_publicado.titulo in client.get(reverse("catalogo"), {"tema": tema.slug}).content.decode()
    assert curso_publicado.titulo not in client.get(reverse("catalogo"), {"tema": "outro"}).content.decode()


@pytest.mark.django_db
def test_busca_no_catalogo(client, curso_publicado):
    assert curso_publicado.titulo in client.get(reverse("catalogo"), {"q": "pensamento"}).content.decode()
    assert curso_publicado.titulo not in client.get(reverse("catalogo"), {"q": "astronomia"}).content.decode()


@pytest.mark.django_db
def test_catalogo_nao_expoe_dado_pessoal_da_equipe(client, curso_publicado, aluno, professor):
    services.adicionar_membro(curso_publicado, aluno, por=professor)
    resposta = client.get(reverse("catalogo_curso", args=[curso_publicado.pk]))
    conteudo = resposta.content.decode()
    assert aluno.cpf not in conteudo
    assert aluno.email not in conteudo
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `pytest apps/catalogo/tests -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'catalogo' not found`.

- [ ] **Step 4: Escrever as views**

`apps/catalogo/views.py`:

```python
from django.shortcuts import get_object_or_404, render

from apps.cursos.busca import buscar
from apps.cursos.choices import Formato, StatusCurso, TipoPublico
from apps.cursos.models import Curso, Tema
from apps.referenciais.choices import ETAPAS
from apps.referenciais.models import Referencial


def cursos_publicados():
    """Visitante enxerga exclusivamente cursos PUBLICADO (spec 10)."""
    return Curso.objects.filter(status=StatusCurso.PUBLICADO).select_related("referencial")


def catalogo(request):
    cursos = cursos_publicados()

    etapa = request.GET.get("etapa", "")
    if etapa:
        cursos = cursos.filter(tipo_publico=TipoPublico.ESCOLAR, etapa_ano=etapa)
    if request.GET.get("comunitario"):
        cursos = cursos.filter(tipo_publico=TipoPublico.COMUNITARIO)

    tema = request.GET.get("tema", "")
    if tema:
        cursos = cursos.filter(temas__slug=tema)

    referencial = request.GET.get("referencial", "")
    if referencial:
        cursos = cursos.filter(referencial__sigla=referencial)

    formato = request.GET.get("formato", "")
    if formato:
        cursos = cursos.filter(formato=formato)

    cursos = buscar(cursos, request.GET.get("q", "")).distinct()

    return render(
        request,
        "catalogo/lista.html",
        {
            "cursos": cursos,
            "etapas": ETAPAS,
            "temas": Tema.objects.filter(ativo=True),
            "referenciais": Referencial.objects.filter(ativo=True),
            "formatos": Formato.choices,
            "filtros": request.GET,
        },
    )


def catalogo_curso(request, pk):
    curso = get_object_or_404(cursos_publicados().prefetch_related("temas", "competencias"), pk=pk)
    return render(request, "catalogo/curso.html", {"curso": curso})
```

`apps/catalogo/urls.py`:

```python
from django.urls import path

from apps.catalogo import views

urlpatterns = [
    path("", views.catalogo, name="catalogo"),
    path("cursos/<int:pk>/publico/", views.catalogo_curso, name="catalogo_curso"),
]
```

Em `config/urls.py`, acrescente **antes** das demais rotas de `apps`:

```python
    path("", include("apps.catalogo.urls")),
```

O `painel` já mora em `painel/` desde o Plano 1, então não há conflito de rota: o catálogo assume a raiz e passa a ser a porta de entrada do sistema, inclusive para quem não tem conta.

- [ ] **Step 5: Escrever os templates**

`templates/catalogo/lista.html`:

```html
{% extends "base.html" %}
{% block titulo %}Catalogo de cursos de extensao{% endblock %}
{% block conteudo %}
  <h1>Cursos de extensao</h1>
  <p>Cursos e oficinas produzidos pelo curso de Sistemas de Informacao da UFSM &mdash; Frederico Westphalen.</p>

  <form method="get">
    <input type="search" name="q" value="{{ filtros.q }}" placeholder="Buscar por assunto">
    <select name="etapa">
      <option value="">Qualquer etapa escolar</option>
      {% for codigo, nome in etapas %}
        <option value="{{ codigo }}" {% if filtros.etapa == codigo %}selected{% endif %}>{{ nome }}</option>
      {% endfor %}
    </select>
    <select name="tema">
      <option value="">Qualquer tema</option>
      {% for tema in temas %}
        <option value="{{ tema.slug }}" {% if filtros.tema == tema.slug %}selected{% endif %}>{{ tema.nome }}</option>
      {% endfor %}
    </select>
    <select name="formato">
      <option value="">Qualquer formato</option>
      {% for codigo, nome in formatos %}
        <option value="{{ codigo }}" {% if filtros.formato == codigo %}selected{% endif %}>{{ nome }}</option>
      {% endfor %}
    </select>
    <select name="referencial">
      <option value="">Qualquer referencial</option>
      {% for ref in referenciais %}
        <option value="{{ ref.sigla }}" {% if filtros.referencial == ref.sigla %}selected{% endif %}>{{ ref.nome }}</option>
      {% endfor %}
    </select>
    <button type="submit">Filtrar</button>
  </form>

  {% for curso in cursos %}
    <article>
      <h2><a href="{% url 'catalogo_curso' curso.pk %}">{{ curso.titulo }}</a></h2>
      <p>{{ curso.publico_alvo }} &middot; {{ curso.carga_horaria }}h &middot; {{ curso.get_formato_display }}</p>
      <p>{{ curso.resumo|truncatewords:30 }}</p>
    </article>
  {% empty %}
    <p>Nenhum curso encontrado com esses filtros.</p>
  {% endfor %}
{% endblock %}
```

`templates/catalogo/curso.html`:

```html
{% extends "base.html" %}
{% block titulo %}{{ curso.titulo }}{% endblock %}
{% block conteudo %}
  <h1>{{ curso.titulo }}</h1>
  <p>{{ curso.publico_alvo }} &middot; {{ curso.carga_horaria }} horas &middot; {{ curso.get_formato_display }}</p>
  <p>{{ curso.resumo }}</p>

  {% if curso.pre_requisitos %}<h2>Pre-requisitos</h2><p>{{ curso.pre_requisitos }}</p>{% endif %}

  {% if curso.temas.exists %}
    <h2>Temas</h2>
    <ul>{% for tema in curso.temas.all %}<li>{{ tema.nome }}</li>{% endfor %}</ul>
  {% endif %}

  {% if curso.referencial %}
    <h2>{{ curso.referencial.nome }}</h2>
    <ul>
      {% for competencia in curso.competencias.all %}
        <li>{{ competencia.codigo }} &mdash; {{ competencia.descricao }}</li>
      {% endfor %}
    </ul>
  {% endif %}
{% endblock %}
```

Em `templates/base.html`, troque o link do cabeçalho para apontar ao catálogo:

```html
    <a href="{% url 'catalogo' %}">IntegraSI</a>
```

- [ ] **Step 6: Rodar a suíte inteira e commitar**

```bash
pytest -v
git add apps/catalogo config templates
git commit -m "feat(catalogo): catalogo publico com filtros e busca"
```

Expected: PASS — inclusive os testes do Plano 1 que usavam `reverse("painel")`, que continuam válidos.

---

### Task 6: Solicitação de curso pela comunidade

**Files:**
- Create: `apps/catalogo/models.py`, `apps/catalogo/forms.py`, `templates/catalogo/solicitar.html`, `templates/catalogo/solicitacao_recebida.html`
- Modify: `apps/catalogo/views.py`, `apps/catalogo/urls.py`, `templates/catalogo/curso.html`
- Test: `apps/catalogo/tests/test_solicitacao.py`

**Interfaces:**
- Consumes: `cursos_publicados` (Task 5), `notificacoes.services.enfileirar` (Task 1).
- Produces: `apps.catalogo.models.Solicitacao` (`curso`, `nome`, `email`, `telefone`, `instituicao`, `num_participantes`, `periodo_pretendido`, `mensagem`, `status`, `resposta`, `ip_origem`, `criado_em`), com `Solicitacao.RECEBIDA/EM_ANALISE/ACEITA/RECUSADA`; rota `solicitar` (`<int:pk>`); constante `LIMITE_POR_IP_POR_HORA = 5`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/catalogo/tests/test_solicitacao.py`:

```python
import pytest
from django.urls import reverse

from apps.catalogo.models import Solicitacao
from apps.cursos import services
from apps.cursos.choices import StatusEntregavel
from apps.notificacoes.models import Notificacao


@pytest.fixture
def curso_publicado(dados_curso, professor, coordenador):
    curso = services.criar_curso(**dados_curso)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    return curso


def dados_validos():
    return {
        "nome": "Escola Municipal Sao Jose",
        "email": "direcao@escola.exemplo.br",
        "telefone": "55999999999",
        "instituicao": "EMEF Sao Jose",
        "num_participantes": 25,
        "periodo_pretendido": "Marco de 2027",
        "mensagem": "Gostariamos de oferecer a oficina para o 5o ano.",
        "confirmacao": "",
    }


@pytest.mark.django_db
def test_visitante_solicita_sem_login(client, curso_publicado):
    resposta = client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos(), follow=True)
    assert resposta.status_code == 200
    solicitacao = Solicitacao.objects.get()
    assert solicitacao.curso == curso_publicado
    assert solicitacao.status == Solicitacao.RECEBIDA


@pytest.mark.django_db
def test_solicitacao_avisa_professor_e_coordenador(client, curso_publicado, professor, coordenador):
    client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos())
    destinatarios = set(Notificacao.objects.values_list("destinatario", flat=True))
    assert {professor.email, coordenador.email} <= destinatarios


@pytest.mark.django_db
def test_nao_se_solicita_curso_nao_publicado(client, dados_curso):
    curso = services.criar_curso(**dados_curso)
    resposta = client.post(reverse("solicitar", args=[curso.pk]), dados_validos())
    assert resposta.status_code == 404
    assert Solicitacao.objects.count() == 0


@pytest.mark.django_db
def test_honeypot_preenchido_e_descartado_em_silencio(client, curso_publicado):
    dados = dados_validos()
    dados["confirmacao"] = "sou um robo"
    resposta = client.post(reverse("solicitar", args=[curso_publicado.pk]), dados, follow=True)
    assert resposta.status_code == 200
    assert Solicitacao.objects.count() == 0


@pytest.mark.django_db
def test_limite_por_ip(client, curso_publicado):
    from apps.catalogo.views import LIMITE_POR_IP_POR_HORA

    for _ in range(LIMITE_POR_IP_POR_HORA):
        client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos())
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA
    resposta = client.post(reverse("solicitar", args=[curso_publicado.pk]), dados_validos(), follow=True)
    assert "muitas solicitacoes" in resposta.content.decode().lower()
    assert Solicitacao.objects.count() == LIMITE_POR_IP_POR_HORA


@pytest.mark.django_db
def test_mensagem_gigante_e_recusada(client, curso_publicado):
    dados = dados_validos()
    dados["mensagem"] = "x" * 5000
    client.post(reverse("solicitar", args=[curso_publicado.pk]), dados)
    assert Solicitacao.objects.count() == 0


@pytest.mark.django_db
def test_formulario_declara_a_finalidade_dos_dados(client, curso_publicado):
    resposta = client.get(reverse("solicitar", args=[curso_publicado.pk]))
    conteudo = resposta.content.decode().lower()
    assert "finalidade" in conteudo or "seus dados" in conteudo
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/catalogo/tests/test_solicitacao.py -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'solicitar' not found`.

- [ ] **Step 3: Implementar o modelo**

`apps/catalogo/models.py`:

```python
from django.db import models


class Solicitacao(models.Model):
    """Pedido de realizacao de um curso, vindo da comunidade externa.

    Guarda dado pessoal de terceiro: finalidade declarada no formulario, acesso
    restrito ao professor responsavel e ao coordenador (spec 10).
    """

    RECEBIDA = "RECEBIDA"
    EM_ANALISE = "EM_ANALISE"
    ACEITA = "ACEITA"
    RECUSADA = "RECUSADA"
    SITUACOES = [
        (RECEBIDA, "Recebida"),
        (EM_ANALISE, "Em analise"),
        (ACEITA, "Aceita"),
        (RECUSADA, "Recusada"),
    ]

    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.PROTECT, related_name="solicitacoes", verbose_name="curso"
    )
    nome = models.CharField("nome do solicitante", max_length=150)
    email = models.EmailField("e-mail")
    telefone = models.CharField("telefone", max_length=20, blank=True)
    instituicao = models.CharField("instituicao", max_length=150, blank=True)
    num_participantes = models.PositiveSmallIntegerField("participantes previstos")
    periodo_pretendido = models.CharField("periodo pretendido", max_length=100, blank=True)
    mensagem = models.TextField("mensagem", max_length=2000, blank=True)
    status = models.CharField("situacao", max_length=20, choices=SITUACOES, default=RECEBIDA)
    resposta = models.TextField("resposta", blank=True)
    ip_origem = models.GenericIPAddressField("IP de origem", null=True, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "solicitacao"
        verbose_name_plural = "solicitacoes"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.nome} pediu {self.curso.titulo}"
```

O `ip_origem` existe só para conter abuso do formulário aberto; não é usado para nada além disso e entra na política de retenção junto com o restante da solicitação.

- [ ] **Step 4: Escrever o formulário com honeypot**

`apps/catalogo/forms.py`:

```python
from django import forms

from apps.catalogo.models import Solicitacao


class SolicitacaoForm(forms.ModelForm):
    # Campo invisivel para pessoas. Robo preenche tudo que encontra; se vier
    # preenchido, descartamos em silencio (spec 10).
    confirmacao = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Solicitacao
        fields = [
            "nome", "email", "telefone", "instituicao",
            "num_participantes", "periodo_pretendido", "mensagem",
        ]
        widgets = {"mensagem": forms.Textarea(attrs={"rows": 5, "maxlength": 2000})}

    def e_robo(self):
        return bool(self.data.get("confirmacao"))
```

- [ ] **Step 5: Escrever a view**

Acrescente a `apps/catalogo/views.py`:

```python
import datetime

from django.shortcuts import redirect
from django.utils import timezone

from apps.catalogo.forms import SolicitacaoForm
from apps.catalogo.models import Solicitacao
from apps.notificacoes.services import enfileirar

LIMITE_POR_IP_POR_HORA = 5


def _ip_da_requisicao(request):
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def solicitar(request, pk):
    curso = get_object_or_404(cursos_publicados(), pk=pk)
    form = SolicitacaoForm(request.POST or None)

    if request.method != "POST":
        return render(request, "catalogo/solicitar.html", {"curso": curso, "form": form})

    if form.e_robo():
        # Descarte silencioso: responder com erro so ensina o robo a acertar.
        return render(request, "catalogo/solicitacao_recebida.html", {"curso": curso})

    ip = _ip_da_requisicao(request)
    uma_hora_atras = timezone.now() - datetime.timedelta(hours=1)
    if Solicitacao.objects.filter(ip_origem=ip, criado_em__gte=uma_hora_atras).count() >= LIMITE_POR_IP_POR_HORA:
        return render(
            request,
            "catalogo/solicitar.html",
            {"curso": curso, "form": form, "erro": "Muitas solicitacoes deste endereco. Tente novamente mais tarde."},
        )

    if not form.is_valid():
        return render(request, "catalogo/solicitar.html", {"curso": curso, "form": form})

    solicitacao = form.save(commit=False)
    solicitacao.curso = curso
    solicitacao.ip_origem = ip
    solicitacao.save()

    enfileirar(
        evento="SOLICITACAO_RECEBIDA",
        destinatarios=[curso.professor_responsavel.email] + _emails_dos_coordenadores(),
        assunto=f"Nova solicitacao: {curso.titulo}",
        corpo=(
            f"{solicitacao.nome} ({solicitacao.instituicao}) solicitou o curso {curso.titulo} "
            f"para {solicitacao.num_participantes} participantes.\n\n{solicitacao.mensagem}"
        ),
    )
    return render(request, "catalogo/solicitacao_recebida.html", {"curso": curso})


def _emails_dos_coordenadores():
    from apps.contas.models import Usuario

    return list(
        Usuario.objects.filter(papel=Usuario.COORDENADOR, is_active=True).values_list("email", flat=True)
    )
```

Em `apps/catalogo/urls.py`:

```python
    path("cursos/<int:pk>/solicitar/", views.solicitar, name="solicitar"),
```

- [ ] **Step 6: Escrever os templates**

`templates/catalogo/solicitar.html`:

```html
{% extends "base.html" %}
{% block titulo %}Solicitar {{ curso.titulo }}{% endblock %}
{% block conteudo %}
  <h1>Solicitar o curso {{ curso.titulo }}</h1>
  {% if erro %}<p class="mensagem">{{ erro }}</p>{% endif %}
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <p class="finalidade">
      Seus dados serao usados exclusivamente para dar andamento a esta solicitacao e
      organizar a realizacao do curso, e ficam acessiveis apenas ao professor responsavel
      e a coordenacao do curso de Sistemas de Informacao.
    </p>
    <button type="submit">Enviar solicitacao</button>
  </form>
{% endblock %}
```

`templates/catalogo/solicitacao_recebida.html`:

```html
{% extends "base.html" %}
{% block titulo %}Solicitacao recebida{% endblock %}
{% block conteudo %}
  <h1>Solicitacao recebida</h1>
  <p>Recebemos seu pedido para o curso <strong>{{ curso.titulo }}</strong>. O professor
     responsavel entrara em contato pelo e-mail informado.</p>
  <p><a href="{% url 'catalogo' %}">Voltar ao catalogo</a></p>
{% endblock %}
```

Em `templates/catalogo/curso.html`, antes do fim do bloco:

```html
  <p><a href="{% url 'solicitar' curso.pk %}">Solicitar este curso</a></p>
```

- [ ] **Step 7: Migrar, rodar e commitar**

```bash
python manage.py makemigrations catalogo
pytest apps/catalogo/tests -v
git add apps/catalogo templates
git commit -m "feat(catalogo): solicitacao publica com honeypot e limite por IP"
```

Expected: PASS (16 testes no app).

---

### Task 7: Turmas

**Files:**
- Create: `apps/turmas/` (app completo), `apps/turmas/models.py`, `apps/turmas/services.py`, `apps/turmas/admin.py`
- Modify: `config/settings.py`
- Test: `apps/turmas/tests/__init__.py`, `apps/turmas/tests/test_turma.py`

**Interfaces:**
- Consumes: `Curso` (Plano 2), `Solicitacao` (Task 6), `permissions` (Plano 2), `enfileirar` (Task 1).
- Produces: `apps.turmas.models.Turma` (`curso`, `solicitacao`, `professor`, `data_inicio`, `data_fim`, `local`, `vagas`, `status`, `observacoes`), `apps.turmas.models.Participante` (`turma`, `nome`, `email`, `telefone`); `apps.turmas.services.aceitar_solicitacao(solicitacao, professor, dados_turma, por) -> Turma` e `recusar_solicitacao(solicitacao, por, resposta)`.

- [ ] **Step 1: Criar o app**

```bash
mkdir -p apps/turmas/tests
python manage.py startapp turmas apps/turmas
touch apps/turmas/tests/__init__.py
```

Em `apps/turmas/apps.py`, troque `name = "turmas"` por `name = "apps.turmas"`, e acrescente `"apps.turmas"` a `INSTALLED_APPS`.

- [ ] **Step 2: Escrever o teste (vai falhar)**

`apps/turmas/tests/test_turma.py`:

```python
import datetime

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.catalogo.models import Solicitacao
from apps.cursos import services as servicos_curso
from apps.cursos.choices import StatusEntregavel
from apps.notificacoes.models import Notificacao
from apps.turmas import services
from apps.turmas.models import Participante, Turma


@pytest.fixture
def curso_publicado(dados_curso, professor, coordenador):
    curso = servicos_curso.criar_curso(**dados_curso)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    servicos_curso.submeter_ao_coordenador(curso, por=professor)
    servicos_curso.publicar_curso(curso, por=coordenador)
    return curso


@pytest.fixture
def solicitacao(curso_publicado):
    return Solicitacao.objects.create(
        curso=curso_publicado, nome="Escola Sao Jose", email="direcao@escola.exemplo.br",
        num_participantes=25, instituicao="EMEF Sao Jose",
    )


def dados_turma():
    return {
        "data_inicio": datetime.date(2027, 3, 1),
        "data_fim": datetime.date(2027, 3, 30),
        "local": "EMEF Sao Jose",
        "vagas": 25,
    }


@pytest.mark.django_db
def test_aceitar_cria_a_turma_com_professor(solicitacao, professor, coordenador):
    turma = services.aceitar_solicitacao(solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador)
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.ACEITA
    assert turma.professor == professor
    assert turma.curso == solicitacao.curso
    assert turma.status == Turma.AGENDADA


@pytest.mark.django_db
def test_aceitar_responde_ao_solicitante(solicitacao, professor, coordenador):
    services.aceitar_solicitacao(solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador)
    assert Notificacao.objects.filter(destinatario=solicitacao.email).exists()


@pytest.mark.django_db
def test_aceitar_sem_professor_e_impossivel(solicitacao, coordenador):
    with pytest.raises(TypeError):
        services.aceitar_solicitacao(solicitacao, dados_turma=dados_turma(), por=coordenador)


@pytest.mark.django_db
def test_quem_nao_e_professor_nao_conduz_turma(solicitacao, aluno, coordenador):
    with pytest.raises(ValidationError):
        services.aceitar_solicitacao(solicitacao, professor=aluno, dados_turma=dados_turma(), por=coordenador)


@pytest.mark.django_db
def test_aluno_nao_aceita_solicitacao(solicitacao, professor, aluno):
    with pytest.raises(PermissionDenied):
        services.aceitar_solicitacao(solicitacao, professor=professor, dados_turma=dados_turma(), por=aluno)


@pytest.mark.django_db
def test_aceitar_duas_vezes_e_recusado(solicitacao, professor, coordenador):
    services.aceitar_solicitacao(solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador)
    with pytest.raises(ValidationError):
        services.aceitar_solicitacao(solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador)


@pytest.mark.django_db
def test_aceitar_e_atomico(solicitacao, professor, coordenador):
    dados = dados_turma()
    dados["data_fim"] = datetime.date(2027, 1, 1)  # antes do inicio
    with pytest.raises(ValidationError):
        services.aceitar_solicitacao(solicitacao, professor=professor, dados_turma=dados, por=coordenador)
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA
    assert Turma.objects.count() == 0


@pytest.mark.django_db
def test_recusar_registra_a_resposta(solicitacao, coordenador):
    services.recusar_solicitacao(solicitacao, por=coordenador, resposta="Sem equipe disponivel em 2027.")
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECUSADA
    assert solicitacao.resposta == "Sem equipe disponivel em 2027."
    assert Notificacao.objects.filter(destinatario=solicitacao.email).exists()


@pytest.mark.django_db
def test_participante_e_vinculado_a_turma(solicitacao, professor, coordenador):
    turma = services.aceitar_solicitacao(solicitacao, professor=professor, dados_turma=dados_turma(), por=coordenador)
    Participante.objects.create(turma=turma, nome="Maria", email="maria@exemplo.br")
    assert turma.participantes.count() == 1


@pytest.mark.django_db
def test_turma_nao_tem_campo_de_frequencia_nem_certificado():
    """Fronteira do modulo de execucao (spec 1.1): se um destes campos aparecer,
    a fronteira foi atravessada sem querer."""
    campos = {c.name for c in Turma._meta.get_fields()} | {c.name for c in Participante._meta.get_fields()}
    proibidos = {"frequencia", "presenca", "nota", "certificado", "certificado_emitido", "avaliacao"}
    assert campos & proibidos == set()
```

- [ ] **Step 3: Rodar para ver falhar**

Run: `pytest apps/turmas/tests -v`
Expected: FAIL — `ImportError: cannot import name 'Turma'`.

- [ ] **Step 4: Implementar os modelos**

`apps/turmas/models.py`:

```python
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Turma(models.Model):
    """O agendamento de uma realizacao do curso.

    Forma minima de proposito (spec 1.1): este e o modulo de producao. Frequencia,
    avaliacao e certificado sao do modulo de execucao, que sera construido a partir
    daqui. Nenhum campo desses entra neste modelo.
    """

    AGENDADA = "AGENDADA"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"
    SITUACOES = [
        (AGENDADA, "Agendada"),
        (EM_ANDAMENTO, "Em andamento"),
        (CONCLUIDA, "Concluida"),
        (CANCELADA, "Cancelada"),
    ]

    # Aponta para a versao especifica do curso, nunca para a linhagem: e o que
    # permitira dizer, la na frente, qual material foi aplicado nesta turma (spec 1.1).
    curso = models.ForeignKey(
        "cursos.Curso", on_delete=models.PROTECT, related_name="turmas", verbose_name="curso"
    )
    solicitacao = models.OneToOneField(
        "catalogo.Solicitacao",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="turma",
        verbose_name="solicitacao de origem",
    )
    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turmas", verbose_name="professor"
    )
    data_inicio = models.DateField("inicio")
    data_fim = models.DateField("fim")
    local = models.CharField("local", max_length=200)
    vagas = models.PositiveSmallIntegerField("vagas")
    status = models.CharField("situacao", max_length=20, choices=SITUACOES, default=AGENDADA)
    observacoes = models.TextField("observacoes", blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "turma"
        verbose_name_plural = "turmas"
        ordering = ["-data_inicio"]

    def __str__(self):
        return f"{self.curso.titulo} em {self.local}"

    def clean(self):
        super().clean()
        erros = {}
        if self.data_inicio and self.data_fim and self.data_fim < self.data_inicio:
            erros["data_fim"] = "O fim nao pode ser anterior ao inicio."
        if self.professor_id and not self.professor.e_professor:
            erros["professor"] = "Somente professor conduz turma."
        if erros:
            raise ValidationError(erros)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Participante(models.Model):
    turma = models.ForeignKey(
        Turma, on_delete=models.CASCADE, related_name="participantes", verbose_name="turma"
    )
    nome = models.CharField("nome", max_length=150)
    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField("telefone", max_length=20, blank=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "participante"
        verbose_name_plural = "participantes"
        ordering = ["nome"]

    def __str__(self):
        return self.nome
```

- [ ] **Step 5: Implementar os serviços**

`apps/turmas/services.py`:

```python
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.catalogo.models import Solicitacao
from apps.cursos import permissions
from apps.notificacoes.services import enfileirar
from apps.turmas.models import Turma


@transaction.atomic
def aceitar_solicitacao(solicitacao, professor, dados_turma, por):
    """Aceita a solicitacao e cria a turma na mesma transacao.

    O professor e obrigatorio: e desta designacao que decorre o acesso dele aos
    participantes (spec 7.2). Solicitacao aceita sem turma e sem professor nao e
    um estado alcancavel.
    """
    permissions.garante(permissions.pode_publicar(por), "Somente a coordenacao aceita solicitacoes.")
    if solicitacao.status in (Solicitacao.ACEITA, Solicitacao.RECUSADA):
        raise ValidationError("Esta solicitacao ja foi respondida.")

    turma = Turma.objects.create(
        curso=solicitacao.curso, solicitacao=solicitacao, professor=professor, **dados_turma
    )
    solicitacao.status = Solicitacao.ACEITA
    solicitacao.resposta = (
        f"Curso agendado para {turma.data_inicio:%d/%m/%Y} em {turma.local}. "
        f"Professor responsavel: {professor.nome_completo}."
    )
    solicitacao.save(update_fields=["status", "resposta"])

    enfileirar(
        evento="SOLICITACAO_ACEITA",
        destinatarios=[solicitacao.email],
        assunto=f"Curso agendado: {solicitacao.curso.titulo}",
        corpo=solicitacao.resposta,
    )
    return turma


@transaction.atomic
def recusar_solicitacao(solicitacao, por, resposta):
    permissions.garante(permissions.pode_publicar(por), "Somente a coordenacao responde solicitacoes.")
    if solicitacao.status in (Solicitacao.ACEITA, Solicitacao.RECUSADA):
        raise ValidationError("Esta solicitacao ja foi respondida.")
    if not (resposta or "").strip():
        raise ValidationError("Escreva a resposta ao solicitante.")
    solicitacao.status = Solicitacao.RECUSADA
    solicitacao.resposta = resposta
    solicitacao.save(update_fields=["status", "resposta"])
    enfileirar(
        evento="SOLICITACAO_RECUSADA",
        destinatarios=[solicitacao.email],
        assunto=f"Sobre sua solicitacao: {solicitacao.curso.titulo}",
        corpo=resposta,
    )
    return solicitacao
```

- [ ] **Step 6: Escrever o Admin com acesso restrito**

`apps/turmas/admin.py`:

```python
from django.contrib import admin

from apps.turmas.models import Participante, Turma


class ParticipanteInline(admin.TabularInline):
    model = Participante
    extra = 0


@admin.register(Turma)
class TurmaAdmin(admin.ModelAdmin):
    list_display = ["curso", "local", "data_inicio", "professor", "status"]
    list_filter = ["status", "data_inicio"]
    inlines = [ParticipanteInline]

    def get_queryset(self, request):
        """Professor nao ve turma alheia, e por consequencia nao ve os
        participantes dela (spec 10)."""
        queryset = super().get_queryset(request)
        if request.user.e_coordenador or request.user.is_superuser:
            return queryset
        return queryset.filter(professor=request.user)
```

- [ ] **Step 7: Migrar, rodar e commitar**

```bash
python manage.py makemigrations turmas
pytest apps/turmas/tests -v
git add apps/turmas config/settings.py
git commit -m "feat(turmas): turma minima nascida de solicitacao aceita"
```

Expected: PASS (10 testes).

---

### Task 8: Telas de solicitações e turmas

**Files:**
- Create: `apps/turmas/views.py`, `apps/turmas/urls.py`, `apps/turmas/forms.py`, `templates/turmas/solicitacoes.html`, `templates/turmas/responder.html`, `templates/turmas/minhas_turmas.html`
- Modify: `config/urls.py`, `templates/painel.html`
- Test: `apps/turmas/tests/test_views.py`

**Interfaces:**
- Consumes: serviços da Task 7.
- Produces: rotas `solicitacoes`, `responder_solicitacao` (`<int:pk>`), `minhas_turmas`; `TurmaForm`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/turmas/tests/test_views.py`:

```python
import datetime

import pytest
from django.urls import reverse

from apps.catalogo.models import Solicitacao
from apps.cursos import services as servicos_curso
from apps.cursos.choices import StatusEntregavel
from apps.turmas.models import Turma


@pytest.fixture
def solicitacao(dados_curso, professor, coordenador):
    curso = servicos_curso.criar_curso(**dados_curso)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    servicos_curso.submeter_ao_coordenador(curso, por=professor)
    servicos_curso.publicar_curso(curso, por=coordenador)
    return Solicitacao.objects.create(
        curso=curso, nome="Escola Sao Jose", email="direcao@escola.exemplo.br", num_participantes=25
    )


@pytest.mark.django_db
def test_coordenador_ve_as_solicitacoes(client, coordenador, solicitacao):
    client.force_login(coordenador)
    resposta = client.get(reverse("solicitacoes"))
    assert solicitacao.nome in resposta.content.decode()


@pytest.mark.django_db
def test_aluno_nao_ve_as_solicitacoes(client, aluno, solicitacao):
    client.force_login(aluno)
    assert client.get(reverse("solicitacoes")).status_code == 403


@pytest.mark.django_db
def test_aceitar_pela_tela_cria_a_turma(client, coordenador, professor, solicitacao):
    client.force_login(coordenador)
    client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        {
            "decisao": "ACEITAR",
            "professor": professor.pk,
            "data_inicio": "2027-03-01",
            "data_fim": "2027-03-30",
            "local": "EMEF Sao Jose",
            "vagas": 25,
        },
        follow=True,
    )
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.ACEITA
    assert Turma.objects.get().professor == professor


@pytest.mark.django_db
def test_recusar_sem_resposta_e_barrado(client, coordenador, solicitacao):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("responder_solicitacao", args=[solicitacao.pk]),
        {"decisao": "RECUSAR", "resposta": " "},
        follow=True,
    )
    assert "Escreva a resposta" in resposta.content.decode()
    solicitacao.refresh_from_db()
    assert solicitacao.status == Solicitacao.RECEBIDA


@pytest.mark.django_db
def test_professor_ve_apenas_as_proprias_turmas(client, coordenador, professor, solicitacao, db):
    from apps.contas.models import Usuario
    from apps.turmas import services

    services.aceitar_solicitacao(
        solicitacao, professor=professor,
        dados_turma={
            "data_inicio": datetime.date(2027, 3, 1), "data_fim": datetime.date(2027, 3, 30),
            "local": "EMEF Sao Jose", "vagas": 25,
        },
        por=coordenador,
    )
    outro = Usuario.objects.create_user(
        email="outro.prof@ufsm.br", nome_completo="Elisa Esteves", cpf="111.444.777-35",
        papel=Usuario.PROFESSOR, siape="9999999", password="senha-de-teste-123",
    )
    client.force_login(outro)
    assert "EMEF Sao Jose" not in client.get(reverse("minhas_turmas")).content.decode()
    client.force_login(professor)
    assert "EMEF Sao Jose" in client.get(reverse("minhas_turmas")).content.decode()
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/turmas/tests/test_views.py -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'solicitacoes' not found`.

- [ ] **Step 3: Escrever o formulário**

`apps/turmas/forms.py`:

```python
from django import forms

from apps.contas.models import Usuario
from apps.turmas.models import Turma


class TurmaForm(forms.ModelForm):
    professor = forms.ModelChoiceField(
        queryset=Usuario.objects.filter(papel=Usuario.PROFESSOR, is_active=True),
        label="professor responsavel",
    )

    class Meta:
        model = Turma
        fields = ["professor", "data_inicio", "data_fim", "local", "vagas", "observacoes"]
        widgets = {
            "data_inicio": forms.DateInput(attrs={"type": "date"}),
            "data_fim": forms.DateInput(attrs={"type": "date"}),
        }
```

- [ ] **Step 4: Escrever as views**

`apps/turmas/views.py`:

```python
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.catalogo.models import Solicitacao
from apps.cursos import permissions
from apps.turmas import services
from apps.turmas.forms import TurmaForm
from apps.turmas.models import Turma


@login_required
def solicitacoes(request):
    permissions.garante(permissions.pode_publicar(request.user), "Area da coordenacao.")
    pendentes = Solicitacao.objects.filter(
        status__in=[Solicitacao.RECEBIDA, Solicitacao.EM_ANALISE]
    ).select_related("curso")
    respondidas = Solicitacao.objects.exclude(
        status__in=[Solicitacao.RECEBIDA, Solicitacao.EM_ANALISE]
    ).select_related("curso")[:20]
    return render(
        request, "turmas/solicitacoes.html", {"pendentes": pendentes, "respondidas": respondidas}
    )


@login_required
def responder_solicitacao(request, pk):
    permissions.garante(permissions.pode_publicar(request.user), "Area da coordenacao.")
    solicitacao = get_object_or_404(Solicitacao, pk=pk)
    form = TurmaForm(request.POST or None)

    if request.method == "POST":
        if request.POST.get("decisao") == "ACEITAR":
            if form.is_valid():
                dados = dict(form.cleaned_data)
                professor = dados.pop("professor")
                try:
                    services.aceitar_solicitacao(
                        solicitacao, professor=professor, dados_turma=dados, por=request.user
                    )
                except ValidationError as erro:
                    messages.error(request, erro.messages[0])
                else:
                    messages.success(request, "Turma agendada e solicitante avisado.")
                    return redirect("solicitacoes")
        else:
            try:
                services.recusar_solicitacao(
                    solicitacao, por=request.user, resposta=request.POST.get("resposta", "")
                )
            except ValidationError as erro:
                messages.error(request, erro.messages[0])
            else:
                messages.success(request, "Solicitante avisado.")
                return redirect("solicitacoes")

    return render(request, "turmas/responder.html", {"solicitacao": solicitacao, "form": form})


@login_required
def minhas_turmas(request):
    turmas = Turma.objects.select_related("curso")
    if not request.user.e_coordenador:
        turmas = turmas.filter(professor=request.user)
    return render(request, "turmas/minhas_turmas.html", {"turmas": turmas})
```

`apps/turmas/urls.py`:

```python
from django.urls import path

from apps.turmas import views

urlpatterns = [
    path("solicitacoes/", views.solicitacoes, name="solicitacoes"),
    path("solicitacoes/<int:pk>/", views.responder_solicitacao, name="responder_solicitacao"),
    path("turmas/", views.minhas_turmas, name="minhas_turmas"),
]
```

Em `config/urls.py`, acrescente `path("", include("apps.turmas.urls")),`.

- [ ] **Step 5: Escrever os templates**

`templates/turmas/solicitacoes.html`:

```html
{% extends "base.html" %}
{% block titulo %}Solicitacoes{% endblock %}
{% block conteudo %}
  <h1>Solicitacoes recebidas</h1>
  {% for solicitacao in pendentes %}
    <article>
      <h2><a href="{% url 'responder_solicitacao' solicitacao.pk %}">{{ solicitacao.curso.titulo }}</a></h2>
      <p>{{ solicitacao.nome }} &middot; {{ solicitacao.instituicao }} &middot;
         {{ solicitacao.num_participantes }} participantes &middot; {{ solicitacao.criado_em|date:"d/m/Y" }}</p>
    </article>
  {% empty %}
    <p>Nenhuma solicitacao pendente.</p>
  {% endfor %}

  <h2>Ja respondidas</h2>
  <ul>
    {% for solicitacao in respondidas %}
      <li>{{ solicitacao.curso.titulo }} &mdash; {{ solicitacao.get_status_display }}</li>
    {% endfor %}
  </ul>
{% endblock %}
```

`templates/turmas/responder.html`:

```html
{% extends "base.html" %}
{% block titulo %}Responder solicitacao{% endblock %}
{% block conteudo %}
  <h1>{{ solicitacao.curso.titulo }}</h1>
  {% for mensagem in messages %}<p class="mensagem">{{ mensagem }}</p>{% endfor %}
  <p>{{ solicitacao.nome }} &middot; {{ solicitacao.email }} &middot; {{ solicitacao.telefone }}</p>
  <p>{{ solicitacao.instituicao }} &middot; {{ solicitacao.num_participantes }} participantes
     &middot; {{ solicitacao.periodo_pretendido }}</p>
  <blockquote>{{ solicitacao.mensagem }}</blockquote>

  <h2>Aceitar e agendar a turma</h2>
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit" name="decisao" value="ACEITAR">Aceitar e agendar</button>
  </form>

  <h2>Recusar</h2>
  <form method="post">
    {% csrf_token %}
    <textarea name="resposta" rows="4" placeholder="Resposta ao solicitante"></textarea>
    <button type="submit" name="decisao" value="RECUSAR">Recusar</button>
  </form>
{% endblock %}
```

`templates/turmas/minhas_turmas.html`:

```html
{% extends "base.html" %}
{% block titulo %}Turmas{% endblock %}
{% block conteudo %}
  <h1>Turmas</h1>
  {% for turma in turmas %}
    <article>
      <h2>{{ turma.curso.titulo }}</h2>
      <p>{{ turma.local }} &middot; {{ turma.data_inicio|date:"d/m/Y" }} a {{ turma.data_fim|date:"d/m/Y" }}
         &middot; {{ turma.vagas }} vagas &middot; {{ turma.get_status_display }}</p>
      <p>{{ turma.participantes.count }} participantes inscritos</p>
    </article>
  {% empty %}
    <p>Nenhuma turma agendada.</p>
  {% endfor %}
{% endblock %}
```

Em `templates/painel.html`:

```html
  {% if user.e_professor or user.e_coordenador %}
    <p><a href="{% url 'minhas_turmas' %}">Turmas</a>
    {% if user.e_coordenador %} &middot; <a href="{% url 'solicitacoes' %}">Solicitacoes</a>{% endif %}</p>
  {% endif %}
```

- [ ] **Step 6: Rodar a suíte inteira**

Run: `pytest -v`
Expected: PASS — todos os testes dos Planos 1, 2 e 3.

- [ ] **Step 7: Conferir o ciclo completo na mão**

```bash
python manage.py runserver
```

Como professor, submeta um curso com os cinco entregáveis aprovados. Como coordenador, publique. Abra `http://localhost:8000/` numa janela anônima, encontre o curso pela busca, solicite. Volte como coordenador, veja a solicitação, aceite designando o professor e conferindo que a turma aparece em Turmas. Rode `python manage.py enviar_notificacoes` e confira os e-mails no console.

- [ ] **Step 8: Commitar**

```bash
git add apps/turmas config/urls.py templates
git commit -m "feat(turmas): telas de solicitacoes e agendamento de turmas"
```

---

## Entregue ao fim deste plano

O ciclo do §3 da spec funciona inteiro, do rascunho do professor à turma agendada, com catálogo público buscável. Falta o que o **Plano 4** cobre: upload de vídeo de 1 GB, entrega protegida de arquivos, versionamento de cursos e o deploy de verdade.
