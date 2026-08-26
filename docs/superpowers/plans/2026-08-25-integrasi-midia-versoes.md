# IntegraSI — Plano 4: Mídia, Versões e Operação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar o sistema utilizável de verdade em produção: upload de vídeo de até 1 GB que sobrevive a queda de conexão, entrega de arquivo que não derruba o servidor, cursos que ganham novas versões sem sair do catálogo, e um deploy com backup que já foi restaurado uma vez.

**Architecture:** O upload é fatiado no navegador e remontado no servidor contra um registro de progresso; a entrega delega ao nginx via `X-Accel-Redirect`; o versionamento clona o curso reaproveitando os mesmos `Arquivo`, e a invariante "no máximo uma versão publicada por linhagem" mantém a consulta do catálogo trivial.

**Tech Stack:** Django 5.x, PostgreSQL 16, JavaScript sem dependências (`Blob.slice`), nginx, gunicorn, systemd, restic.

**Spec:** `docs/superpowers/specs/2026-08-25-integrasi-design.md`

**Depende de:** Planos 1, 2 e 3 completos.

## Global Constraints

- Vídeo até 1 GB, upload em blocos retomável (spec §8).
- Entrega de arquivo **nunca** passa pelo Django: `X-Accel-Redirect`, com o `location` do nginx marcado `internal;` (spec §8, §10).
- `Content-Disposition: inline` apenas para PDF e vídeo; todo o resto vai como `attachment` (spec §8).
- Clonar um curso não pode clonar bytes: versões compartilham o mesmo `Arquivo` (spec §4.6).
- Remoção física de arquivo só quando nenhum anexo de nenhuma versão o referencia, por idade e sob `select_for_update()`, sem contador de referências (spec §13).
- `SUBSTITUIDO` é terminal: consultável como histórico, fora do catálogo, não republicável (spec §5).
- Nenhum campo de frequência, nota ou certificado (spec §1.1).
- **Enumere as regras da tarefa antes de conferir os testes contra elas**, e prove cada teste de invariante quebrando a guarda que ele prende. Partir dos testes só acha teste fraco; partir das regras também acha regra sem teste. Ver `CLAUDE.md`, seção Testes — o padrão apareceu sete vezes no Plano 2.

---

### Task 1: Registro de upload em andamento

**Files:**
- Create: `apps/cursos/models/upload.py`
- Modify: `apps/cursos/models/__init__.py`, `apps/cursos/arquivos.py`, `config/settings.py`
- Test: `apps/cursos/tests/test_upload_modelo.py`

**Interfaces:**
- Consumes: `Entregavel`, `Usuario` (Planos 1-2).
- Produces: `apps.cursos.models.UploadEmAndamento` (`identificador`, `usuario`, `entregavel`, `nome_original`, `tamanho_total`, `tamanho_recebido`, `criado_em`, `atualizado_em`) com métodos `caminho()`, `acrescentar(bloco: bytes)`, `completo`; `apps.cursos.arquivos.LIMITE_VIDEO`, `detecta_mime` reconhecendo MP4.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_upload_modelo.py`:

```python
import pytest

from apps.cursos.arquivos import LIMITE_VIDEO, detecta_mime, valida_upload
from apps.cursos.choices import TipoEntregavel
from apps.cursos.models import UploadEmAndamento

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16


def test_detecta_mp4_pela_caixa_ftyp():
    assert detecta_mime(MP4) == "video/mp4"


def test_video_ate_um_giga_e_aceito():
    assert LIMITE_VIDEO == 1024 * 1024 * 1024
    assert valida_upload("aula.mp4", tamanho=LIMITE_VIDEO, cabecalho=MP4) == "video/mp4"


def test_video_acima_de_um_giga_e_recusado():
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        valida_upload("aula.mp4", tamanho=LIMITE_VIDEO + 1, cabecalho=MP4)


@pytest.fixture
def entregavel_videos(dados_curso, aluno):
    from apps.cursos import services

    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso.entregaveis.get(tipo=TipoEntregavel.VIDEOS)


@pytest.mark.django_db
def test_acrescentar_blocos_soma_o_recebido(entregavel_videos, aluno):
    upload = UploadEmAndamento.objects.create(
        usuario=aluno, entregavel=entregavel_videos, nome_original="aula.mp4", tamanho_total=8
    )
    upload.acrescentar(b"1234")
    assert upload.tamanho_recebido == 4
    assert upload.completo is False
    upload.acrescentar(b"5678")
    assert upload.tamanho_recebido == 8
    assert upload.completo is True
    assert upload.caminho().read_bytes() == b"12345678"


@pytest.mark.django_db
def test_bloco_que_ultrapassa_o_tamanho_declarado_e_recusado(entregavel_videos, aluno):
    from django.core.exceptions import ValidationError

    upload = UploadEmAndamento.objects.create(
        usuario=aluno, entregavel=entregavel_videos, nome_original="aula.mp4", tamanho_total=4
    )
    with pytest.raises(ValidationError):
        upload.acrescentar(b"123456")


@pytest.mark.django_db
def test_upload_declarado_acima_do_limite_e_recusado_na_criacao(entregavel_videos, aluno):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        UploadEmAndamento.objects.create(
            usuario=aluno, entregavel=entregavel_videos,
            nome_original="aula.mp4", tamanho_total=LIMITE_VIDEO + 1,
        )
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_upload_modelo.py -v`
Expected: FAIL — `ImportError: cannot import name 'LIMITE_VIDEO'`.

- [ ] **Step 3: Reconhecer MP4 em `arquivos.py`**

Em `apps/cursos/arquivos.py`, substitua a função `detecta_mime` e acrescente o limite:

```python
GIGA = 1024 * 1024 * 1024
LIMITE_VIDEO = 1 * GIGA


def detecta_mime(cabecalho):
    """Devolve o mime pela assinatura do arquivo, ou None se nao reconhecer."""
    for assinatura, mime in ASSINATURAS:
        if cabecalho.startswith(assinatura):
            return mime
    # MP4 nao comeca com assinatura fixa: a caixa 'ftyp' vem depois do tamanho,
    # nos bytes 4 a 8.
    if len(cabecalho) >= 8 and cabecalho[4:8] == b"ftyp":
        return "video/mp4"
    return None
```

E acrescente às tabelas:

```python
LIMITES["video/mp4"] = LIMITE_VIDEO
EXTENSOES[".mp4"] = "video/mp4"
```

- [ ] **Step 4: Implementar o modelo**

`apps/cursos/models/upload.py`:

```python
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.cursos.arquivos import LIMITE_VIDEO


class UploadEmAndamento(models.Model):
    """Progresso de um upload fatiado. Um GB no upstream domestico de um aluno leva
    perto de meia hora: um POST unico que falha aos 90% significa entrega perdida
    (spec 8)."""

    identificador = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="uploads"
    )
    entregavel = models.ForeignKey(
        "cursos.Entregavel", on_delete=models.CASCADE, related_name="uploads"
    )
    nome_original = models.CharField("nome original", max_length=255)
    tamanho_total = models.PositiveBigIntegerField("tamanho total declarado")
    tamanho_recebido = models.PositiveBigIntegerField("recebido", default=0)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        verbose_name = "upload em andamento"
        verbose_name_plural = "uploads em andamento"
        ordering = ["-atualizado_em"]

    def __str__(self):
        return f"{self.nome_original} ({self.tamanho_recebido}/{self.tamanho_total})"

    def clean(self):
        super().clean()
        if self.tamanho_total > LIMITE_VIDEO:
            raise ValidationError({"tamanho_total": "Arquivo acima do limite de 1 GB."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def caminho(self):
        pasta = Path(settings.MEDIA_ROOT) / "uploads"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta / f"{self.identificador.hex}.parcial"

    @property
    def completo(self):
        return self.tamanho_recebido >= self.tamanho_total

    def acrescentar(self, bloco):
        """Grava o bloco no fim do arquivo parcial e atualiza o progresso."""
        if self.tamanho_recebido + len(bloco) > self.tamanho_total:
            raise ValidationError("Bloco ultrapassa o tamanho declarado do arquivo.")
        with open(self.caminho(), "ab") as parcial:
            parcial.write(bloco)
        self.tamanho_recebido += len(bloco)
        self.save(update_fields=["tamanho_recebido", "atualizado_em"])
```

Acrescente `UploadEmAndamento` a `apps/cursos/models/__init__.py` e ao `__all__`.

- [ ] **Step 5: Migrar, rodar e commitar**

```bash
python manage.py makemigrations cursos
pytest apps/cursos/tests/test_upload_modelo.py -v
git add apps/cursos
git commit -m "feat(cursos): registro de upload em blocos com limite de 1 GB"
```

Expected: PASS (6 testes).

---

### Task 2: Endpoints do upload em blocos

**Files:**
- Create: `apps/cursos/views/upload.py`
- Modify: `apps/cursos/views/__init__.py`, `apps/cursos/urls.py`, `apps/cursos/services.py`
- Test: `apps/cursos/tests/test_upload_views.py`

**Interfaces:**
- Consumes: `UploadEmAndamento` (Task 1), `permissions` (Plano 2).
- Produces: rotas `upload_iniciar` (POST, JSON `{identificador, recebido}`), `upload_bloco` (`<uuid:identificador>`, POST binário), `upload_estado` (`<uuid:identificador>`, GET JSON `{recebido, total}`), `upload_concluir` (`<uuid:identificador>`, POST JSON); `services.concluir_upload(upload, titulo, duracao_minutos) -> Anexo`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_upload_views.py`:

```python
import json

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo, Arquivo, UploadEmAndamento

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 56


@pytest.fixture
def entregavel_videos(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso.entregaveis.get(tipo=TipoEntregavel.VIDEOS)


def inicia(client, entregavel, tamanho=len(MP4)):
    resposta = client.post(
        reverse("upload_iniciar"),
        data=json.dumps({"entregavel": entregavel.pk, "nome": "aula.mp4", "tamanho": tamanho}),
        content_type="application/json",
    )
    return resposta


@pytest.mark.django_db
def test_iniciar_devolve_identificador(client, aluno, entregavel_videos):
    client.force_login(aluno)
    resposta = inicia(client, entregavel_videos)
    assert resposta.status_code == 200
    assert UploadEmAndamento.objects.get().tamanho_total == len(MP4)


@pytest.mark.django_db
def test_aluno_de_fora_nao_inicia_upload(client, outro_aluno, entregavel_videos):
    client.force_login(outro_aluno)
    assert inicia(client, entregavel_videos).status_code == 403


@pytest.mark.django_db
def test_blocos_em_sequencia_montam_o_arquivo(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]
    meio = len(MP4) // 2
    client.post(reverse("upload_bloco", args=[identificador]), data=MP4[:meio], content_type="application/octet-stream")
    resposta = client.post(
        reverse("upload_bloco", args=[identificador]), data=MP4[meio:], content_type="application/octet-stream"
    )
    assert resposta.json()["recebido"] == len(MP4)


@pytest.mark.django_db
def test_estado_permite_retomar_de_onde_parou(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]
    client.post(reverse("upload_bloco", args=[identificador]), data=MP4[:10], content_type="application/octet-stream")
    estado = client.get(reverse("upload_estado", args=[identificador])).json()
    assert estado["recebido"] == 10
    assert estado["total"] == len(MP4)


@pytest.mark.django_db
def test_upload_de_outro_usuario_nao_e_acessivel(client, aluno, outro_aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]
    client.force_login(outro_aluno)
    resposta = client.post(
        reverse("upload_bloco", args=[identificador]), data=MP4, content_type="application/octet-stream"
    )
    assert resposta.status_code == 404


@pytest.mark.django_db
def test_concluir_cria_arquivo_e_anexo_de_video(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]
    client.post(reverse("upload_bloco", args=[identificador]), data=MP4, content_type="application/octet-stream")
    resposta = client.post(
        reverse("upload_concluir", args=[identificador]),
        data=json.dumps({"titulo": "Aula 1", "duracao_minutos": 7}),
        content_type="application/json",
    )
    assert resposta.status_code == 200
    anexo = Anexo.objects.get()
    assert anexo.tipo_midia == TipoMidia.VIDEO
    assert anexo.duracao_minutos == 7
    assert anexo.arquivo.mime == "video/mp4"
    assert Arquivo.objects.count() == 1
    assert UploadEmAndamento.objects.count() == 0


@pytest.mark.django_db
def test_concluir_upload_incompleto_e_recusado(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = inicia(client, entregavel_videos).json()["identificador"]
    client.post(reverse("upload_bloco", args=[identificador]), data=MP4[:10], content_type="application/octet-stream")
    resposta = client.post(
        reverse("upload_concluir", args=[identificador]),
        data=json.dumps({"titulo": "Aula 1", "duracao_minutos": 7}),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert Anexo.objects.count() == 0


@pytest.mark.django_db
def test_arquivo_que_nao_e_video_e_recusado_na_conclusao(client, aluno, entregavel_videos):
    client.force_login(aluno)
    conteudo = b"%PDF-1.7 nao sou video" + b"\x00" * 40
    identificador = inicia(client, entregavel_videos, tamanho=len(conteudo)).json()["identificador"]
    client.post(reverse("upload_bloco", args=[identificador]), data=conteudo, content_type="application/octet-stream")
    resposta = client.post(
        reverse("upload_concluir", args=[identificador]),
        data=json.dumps({"titulo": "Aula 1", "duracao_minutos": 7}),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert Anexo.objects.count() == 0
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_upload_views.py -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'upload_iniciar' not found`.

- [ ] **Step 3: Escrever o serviço de conclusão**

Ao fim de `apps/cursos/services.py`:

```python
import hashlib

from django.core.files import File

from apps.cursos.arquivos import valida_upload
from apps.cursos.choices import TipoMidia
from apps.cursos.models import Anexo, Arquivo


@transaction.atomic
def concluir_upload(upload, titulo, duracao_minutos):
    """Transforma o arquivo parcial em Arquivo + Anexo de video."""
    if not upload.completo:
        raise ValidationError("O upload ainda nao terminou.")
    caminho = upload.caminho()
    with open(caminho, "rb") as parcial:
        cabecalho = parcial.read(16)
    mime = valida_upload(upload.nome_original, caminho.stat().st_size, cabecalho)
    if mime != "video/mp4":
        raise ValidationError("Este entregavel aceita apenas video MP4.")

    digest = hashlib.sha256()
    with open(caminho, "rb") as parcial:
        for pedaco in iter(lambda: parcial.read(1024 * 1024), b""):
            digest.update(pedaco)

    arquivo = Arquivo(
        nome_original=upload.nome_original,
        tamanho=caminho.stat().st_size,
        mime=mime,
        hash_conteudo=digest.hexdigest(),
        enviado_por=upload.usuario,
    )
    with open(caminho, "rb") as parcial:
        arquivo.arquivo.save(upload.nome_original, File(parcial), save=False)
    arquivo.save()

    anexo = Anexo.objects.create(
        entregavel=upload.entregavel,
        tipo_midia=TipoMidia.VIDEO,
        titulo=titulo,
        arquivo=arquivo,
        duracao_minutos=duracao_minutos,
        enviado_por=upload.usuario,
    )
    caminho.unlink(missing_ok=True)
    upload.delete()
    return anexo
```

- [ ] **Step 4: Escrever as views**

`apps/cursos/views/upload.py`:

```python
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.cursos import permissions, services
from apps.cursos.models import Entregavel, UploadEmAndamento


def _meu_upload(request, identificador):
    """Upload e sempre do proprio usuario: 404 para qualquer outro, e nao 403,
    para nao confirmar a existencia do identificador a quem nao e dono."""
    return get_object_or_404(
        UploadEmAndamento, identificador=identificador, usuario=request.user
    )


@login_required
@require_POST
def upload_iniciar(request):
    dados = json.loads(request.body)
    entregavel = get_object_or_404(Entregavel, pk=dados["entregavel"])
    permissions.garante(
        permissions.pode_editar_producao(request.user, entregavel),
        "Este entregavel nao esta aberto para edicao.",
    )
    try:
        upload = UploadEmAndamento.objects.create(
            usuario=request.user,
            entregavel=entregavel,
            nome_original=dados["nome"],
            tamanho_total=int(dados["tamanho"]),
        )
    except ValidationError as erro:
        return JsonResponse({"erro": erro.messages[0]}, status=400)
    return JsonResponse({"identificador": str(upload.identificador), "recebido": 0})


@login_required
@require_POST
def upload_bloco(request, identificador):
    upload = _meu_upload(request, identificador)
    try:
        upload.acrescentar(request.body)
    except ValidationError as erro:
        return JsonResponse({"erro": erro.messages[0]}, status=400)
    return JsonResponse({"recebido": upload.tamanho_recebido, "total": upload.tamanho_total})


@login_required
@require_GET
def upload_estado(request, identificador):
    upload = _meu_upload(request, identificador)
    return JsonResponse({"recebido": upload.tamanho_recebido, "total": upload.tamanho_total})


@login_required
@require_POST
def upload_concluir(request, identificador):
    upload = _meu_upload(request, identificador)
    dados = json.loads(request.body)
    try:
        anexo = services.concluir_upload(
            upload, titulo=dados["titulo"], duracao_minutos=int(dados["duracao_minutos"])
        )
    except ValidationError as erro:
        return JsonResponse({"erro": erro.messages[0]}, status=400)
    return JsonResponse({"anexo": anexo.pk, "titulo": anexo.titulo})
```

Acrescente as quatro views a `apps/cursos/views/__init__.py` e as rotas a `apps/cursos/urls.py`:

```python
    path("uploads/iniciar/", views.upload_iniciar, name="upload_iniciar"),
    path("uploads/<uuid:identificador>/bloco/", views.upload_bloco, name="upload_bloco"),
    path("uploads/<uuid:identificador>/estado/", views.upload_estado, name="upload_estado"),
    path("uploads/<uuid:identificador>/concluir/", views.upload_concluir, name="upload_concluir"),
```

- [ ] **Step 5: Rodar e commitar**

```bash
pytest apps/cursos/tests/test_upload_views.py -v
git add apps/cursos
git commit -m "feat(cursos): endpoints de upload em blocos com retomada"
```

Expected: PASS (8 testes).

---

### Task 3: Upload retomável no navegador

**Files:**
- Create: `static/js/upload.js`
- Modify: `templates/cursos/entregavel.html`
- Test: `apps/cursos/tests/test_upload_integracao.py`

**Interfaces:**
- Consumes: as rotas da Task 2.
- Produces: `static/js/upload.js` expondo `iniciarUpload(form)`; bloco de upload de vídeo no template do entregável quando `entregavel.tipo == "VIDEOS"`.

Este é o único ponto do sistema com JavaScript próprio: **HTMX não fatia arquivo** (spec §8). São cerca de 90 linhas com `Blob.slice()`, sem dependência nova.

- [ ] **Step 1: Escrever o teste de integração (vai falhar)**

Testar JavaScript de navegador exigiria Playwright e um servidor de verdade — desproporcional para 90 linhas. O que este teste verifica é o contrato do lado do servidor que o JS usa: a sequência iniciar → bloco → bloco → concluir funciona com blocos do tamanho que o JS envia.

`apps/cursos/tests/test_upload_integracao.py`:

```python
import json

import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import TipoEntregavel
from apps.cursos.models import Anexo

TAMANHO_BLOCO = 5 * 1024 * 1024  # precisa ser o mesmo valor de static/js/upload.js
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * (TAMANHO_BLOCO * 2)


@pytest.fixture
def entregavel_videos(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso.entregaveis.get(tipo=TipoEntregavel.VIDEOS)


@pytest.mark.django_db
def test_upload_em_tres_blocos_do_tamanho_do_js(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = client.post(
        reverse("upload_iniciar"),
        data=json.dumps({"entregavel": entregavel_videos.pk, "nome": "aula.mp4", "tamanho": len(MP4)}),
        content_type="application/json",
    ).json()["identificador"]

    for inicio in range(0, len(MP4), TAMANHO_BLOCO):
        resposta = client.post(
            reverse("upload_bloco", args=[identificador]),
            data=MP4[inicio : inicio + TAMANHO_BLOCO],
            content_type="application/octet-stream",
        )
        assert resposta.status_code == 200

    resposta = client.post(
        reverse("upload_concluir", args=[identificador]),
        data=json.dumps({"titulo": "Aula 1", "duracao_minutos": 8}),
        content_type="application/json",
    )
    assert resposta.status_code == 200
    assert Anexo.objects.get().arquivo.tamanho == len(MP4)


@pytest.mark.django_db
def test_retomada_apos_queda_no_meio(client, aluno, entregavel_videos):
    client.force_login(aluno)
    identificador = client.post(
        reverse("upload_iniciar"),
        data=json.dumps({"entregavel": entregavel_videos.pk, "nome": "aula.mp4", "tamanho": len(MP4)}),
        content_type="application/json",
    ).json()["identificador"]

    client.post(
        reverse("upload_bloco", args=[identificador]),
        data=MP4[:TAMANHO_BLOCO],
        content_type="application/octet-stream",
    )
    # A conexao cai. O navegador volta, pergunta onde parou e continua dali.
    recebido = client.get(reverse("upload_estado", args=[identificador])).json()["recebido"]
    assert recebido == TAMANHO_BLOCO

    for inicio in range(recebido, len(MP4), TAMANHO_BLOCO):
        client.post(
            reverse("upload_bloco", args=[identificador]),
            data=MP4[inicio : inicio + TAMANHO_BLOCO],
            content_type="application/octet-stream",
        )

    resposta = client.post(
        reverse("upload_concluir", args=[identificador]),
        data=json.dumps({"titulo": "Aula 1", "duracao_minutos": 8}),
        content_type="application/json",
    )
    assert resposta.status_code == 200
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_upload_integracao.py -v`
Expected: FAIL — o segundo teste falha em `DATA_UPLOAD_MAX_MEMORY_SIZE` ou o primeiro na soma dos tamanhos, dependendo da configuração. Anote a mensagem: ela mostra qual limite precisa subir.

- [ ] **Step 3: Liberar o tamanho do bloco no Django**

Em `config/settings.py`, substitua a linha de `DATA_UPLOAD_MAX_MEMORY_SIZE`:

```python
# Um bloco de upload de video tem 5 MB; a folga cobre o maior anexo comum (slides).
DATA_UPLOAD_MAX_MEMORY_SIZE = 55 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
```

Se o teste acusar limite, é `DATA_UPLOAD_MAX_MEMORY_SIZE` que precisa ser maior que `TAMANHO_BLOCO`.

- [ ] **Step 4: Escrever o JavaScript**

`static/js/upload.js`:

```javascript
// Upload de video em blocos, retomavel. HTMX nao fatia arquivo: e o unico ponto
// do sistema que precisa de JS de verdade (spec 8).
const TAMANHO_BLOCO = 5 * 1024 * 1024;

function csrf() {
  return document.querySelector('[name=csrfmiddlewaretoken]').value;
}

async function postar(url, corpo, tipo) {
  const resposta = await fetch(url, {
    method: 'POST',
    headers: { 'X-CSRFToken': csrf(), 'Content-Type': tipo },
    body: corpo,
  });
  if (!resposta.ok) {
    const erro = await resposta.json().catch(() => ({ erro: 'Falha na comunicacao.' }));
    throw new Error(erro.erro);
  }
  return resposta.json();
}

async function enviarBlocos(arquivo, identificador, deslocamentoInicial, aoProgredir) {
  let deslocamento = deslocamentoInicial;
  while (deslocamento < arquivo.size) {
    const bloco = arquivo.slice(deslocamento, deslocamento + TAMANHO_BLOCO);
    const resultado = await postar(
      `/uploads/${identificador}/bloco/`, bloco, 'application/octet-stream'
    );
    deslocamento = resultado.recebido;
    aoProgredir(deslocamento / arquivo.size);
  }
}

async function iniciarUpload(form) {
  const arquivo = form.querySelector('input[type=file]').files[0];
  const titulo = form.querySelector('input[name=titulo]').value;
  const duracao = form.querySelector('input[name=duracao_minutos]').value;
  const entregavel = form.dataset.entregavel;
  const barra = form.querySelector('progress');
  const aviso = form.querySelector('.aviso');

  if (!arquivo) { aviso.textContent = 'Escolha o arquivo de video.'; return; }

  const aoProgredir = (fracao) => { barra.value = Math.round(fracao * 100); };

  try {
    aviso.textContent = 'Enviando...';
    const inicio = await postar(
      '/uploads/iniciar/',
      JSON.stringify({ entregavel, nome: arquivo.name, tamanho: arquivo.size }),
      'application/json'
    );
    const id = inicio.identificador;
    sessionStorage.setItem(`upload:${arquivo.name}:${arquivo.size}`, id);

    try {
      await enviarBlocos(arquivo, id, 0, aoProgredir);
    } catch (erro) {
      // Queda de rede: pergunta ao servidor onde parou e continua dali, em vez
      // de recomecar do zero.
      aviso.textContent = 'Conexao caiu. Retomando...';
      const estado = await (await fetch(`/uploads/${id}/estado/`)).json();
      await enviarBlocos(arquivo, id, estado.recebido, aoProgredir);
    }

    await postar(
      `/uploads/${id}/concluir/`,
      JSON.stringify({ titulo, duracao_minutos: duracao }),
      'application/json'
    );
    sessionStorage.removeItem(`upload:${arquivo.name}:${arquivo.size}`);
    aviso.textContent = 'Video enviado.';
    window.location.reload();
  } catch (erro) {
    aviso.textContent = erro.message;
  }
}

document.addEventListener('submit', (evento) => {
  if (evento.target.matches('[data-upload-video]')) {
    evento.preventDefault();
    iniciarUpload(evento.target);
  }
});
```

- [ ] **Step 5: Acrescentar o formulário ao template**

Em `templates/cursos/entregavel.html`, dentro do `{% if pode_editar %}`:

```html
    {% if entregavel.tipo == "VIDEOS" %}
      <form data-upload-video data-entregavel="{{ entregavel.pk }}">
        {% csrf_token %}
        <label>Video (MP4, ate 1 GB) <input type="file" accept="video/mp4"></label>
        <label>Titulo <input type="text" name="titulo" required></label>
        <label>Duracao em minutos <input type="number" name="duracao_minutos" min="1" max="60" required></label>
        <progress value="0" max="100"></progress>
        <p class="aviso"></p>
        <button type="submit">Enviar video</button>
      </form>
      <script src="{% static 'js/upload.js' %}" defer></script>
    {% endif %}
```

Garanta que `{% load static %}` esteja no topo do template.

- [ ] **Step 6: Rodar e conferir no navegador**

```bash
pytest apps/cursos/tests/test_upload_integracao.py -v
python manage.py runserver
```

Entre como aluno de uma equipe, abra o entregável de vídeo-aulas e envie um MP4 grande de verdade (pelo menos 50 MB). Acompanhe a barra. Para conferir a retomada: comece o envio, desligue a rede no meio, religue e veja o aviso "Retomando".

- [ ] **Step 7: Commitar**

```bash
git add static apps/cursos templates config/settings.py
git commit -m "feat(cursos): upload de video retomavel no navegador"
```

---

### Task 4: Entrega protegida de arquivos

**Files:**
- Create: `apps/cursos/views/midia.py`
- Modify: `apps/cursos/views/__init__.py`, `apps/cursos/urls.py`, `config/settings.py`, `templates/cursos/entregavel.html`, `templates/cursos/revisar.html`
- Test: `apps/cursos/tests/test_midia.py`

**Interfaces:**
- Consumes: `Arquivo`, `Anexo`, `permissions` (Planos 2).
- Produces: rota `baixar` (`<uuid:identificador>`); setting `USAR_X_ACCEL` (padrão `not DEBUG`); constante `INLINE = {"application/pdf", "video/mp4"}`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_midia.py`:

```python
import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo


@pytest.fixture
def anexo(dados_curso, aluno, arquivo_qualquer):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    return Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )


@pytest.mark.django_db
def test_anonimo_nao_baixa(client, anexo):
    resposta = client.get(reverse("baixar", args=[anexo.arquivo.identificador]))
    assert resposta.status_code in (302, 403)


@pytest.mark.django_db
def test_aluno_de_outra_equipe_nao_baixa(client, anexo, outro_aluno):
    client.force_login(outro_aluno)
    assert client.get(reverse("baixar", args=[anexo.arquivo.identificador])).status_code == 403


@pytest.mark.django_db
def test_membro_baixa(client, anexo, aluno, settings):
    settings.USAR_X_ACCEL = True
    client.force_login(aluno)
    resposta = client.get(reverse("baixar", args=[anexo.arquivo.identificador]))
    assert resposta.status_code == 200
    assert resposta["X-Accel-Redirect"].startswith("/protegido/")
    assert resposta.content == b""


@pytest.mark.django_db
def test_curso_publicado_nao_libera_material_para_estranho(client, anexo, outro_aluno, professor, coordenador):
    curso = anexo.entregavel.curso
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    client.force_login(outro_aluno)
    assert client.get(reverse("baixar", args=[anexo.arquivo.identificador])).status_code == 403


@pytest.mark.django_db
def test_pdf_abre_no_navegador(client, anexo, aluno, settings):
    settings.USAR_X_ACCEL = True
    client.force_login(aluno)
    resposta = client.get(reverse("baixar", args=[anexo.arquivo.identificador]))
    assert resposta["Content-Disposition"].startswith("inline")


@pytest.mark.django_db
def test_tipo_nao_confiavel_vai_como_anexo(client, anexo, aluno, settings):
    settings.USAR_X_ACCEL = True
    anexo.arquivo.mime = "image/svg+xml"
    anexo.arquivo.save(update_fields=["mime"])
    client.force_login(aluno)
    resposta = client.get(reverse("baixar", args=[anexo.arquivo.identificador]))
    assert resposta["Content-Disposition"].startswith("attachment")


@pytest.mark.django_db
def test_em_desenvolvimento_o_django_entrega_o_arquivo(client, anexo, aluno, settings):
    settings.USAR_X_ACCEL = False
    client.force_login(aluno)
    resposta = client.get(reverse("baixar", args=[anexo.arquivo.identificador]))
    assert resposta.status_code == 200
    assert b"PDF" in b"".join(resposta.streaming_content)
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_midia.py -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'baixar' not found`.

- [ ] **Step 3: Escrever a view**

`apps/cursos/views/midia.py`:

```python
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404

from apps.cursos import permissions
from apps.cursos.models import Arquivo

# Abrir no navegador so o que e seguro renderizar. HTML ou SVG servido inline a
# partir do nosso dominio e vetor de XSS (spec 8).
INLINE = {"application/pdf", "video/mp4"}


@login_required
def baixar(request, identificador):
    arquivo = get_object_or_404(Arquivo, identificador=identificador)
    anexo = arquivo.anexos.select_related("entregavel__curso").first()
    permissions.garante(
        anexo is not None and permissions.pode_ver_curso(request.user, anexo.entregavel.curso),
        "Material de curso de outra equipe.",
    )

    disposicao = "inline" if arquivo.mime in INLINE else "attachment"
    cabecalho = f'{disposicao}; filename*=UTF-8\'\'{quote(arquivo.nome_original)}'

    if not settings.USAR_X_ACCEL:
        # Desenvolvimento: sem nginx na frente, o Django entrega mesmo.
        resposta = FileResponse(arquivo.arquivo.open("rb"), content_type=arquivo.mime)
        resposta["Content-Disposition"] = cabecalho
        return resposta

    # Producao: quem transmite e o nginx. Um GB pelo processo Python prende um
    # worker por dez minutos e tres downloads simultaneos derrubam o servidor.
    resposta = HttpResponse(content_type=arquivo.mime)
    resposta["X-Accel-Redirect"] = f"/protegido/{arquivo.arquivo.name}"
    resposta["Content-Disposition"] = cabecalho
    return resposta
```

Em `config/settings.py`, depois de `MEDIA_ROOT`:

```python
# Em producao quem transmite e o nginx (X-Accel-Redirect); em desenvolvimento,
# o proprio Django.
USAR_X_ACCEL = os.environ.get("USAR_X_ACCEL", "True" if not DEBUG else "False") == "True"
```

Acrescente `baixar` a `apps/cursos/views/__init__.py` e a rota:

```python
    path("materiais/<uuid:identificador>/", views.baixar, name="baixar"),
```

- [ ] **Step 4: Usar o link nos templates**

Em `templates/cursos/entregavel.html` e `templates/cursos/revisar.html`, troque a listagem de anexos por:

```html
    {% for anexo in entregavel.anexos.all %}
      <li>
        {% if anexo.arquivo %}
          <a href="{% url 'baixar' anexo.arquivo.identificador %}">{{ anexo.titulo }}</a>
        {% else %}
          <a href="{{ anexo.url }}" rel="noopener noreferrer" target="_blank">{{ anexo.titulo }}</a>
        {% endif %}
        {% if anexo.duracao_minutos %} ({{ anexo.duracao_minutos }} min){% endif %}
        {% if anexo.referencia_bibliografica %} &mdash; {{ anexo.referencia_bibliografica }}{% endif %}
      </li>
    {% endfor %}
```

- [ ] **Step 5: Rodar e commitar**

```bash
pytest apps/cursos/tests/test_midia.py -v
git add apps/cursos config/settings.py templates
git commit -m "feat(cursos): entrega de arquivo protegida via X-Accel-Redirect"
```

Expected: PASS (7 testes).

---

### Task 5: Versões de um curso

**Files:**
- Modify: `apps/cursos/models/curso.py`, `apps/cursos/services.py`, `apps/cursos/permissions.py`
- Test: `apps/cursos/tests/test_versoes.py`

**Interfaces:**
- Consumes: `Curso`, `Entregavel`, `Secao`, `Anexo`, `services.publicar_curso` (Planos 2-3).
- Produces: campos `raiz`, `versao`, `motivo_versao` no `Curso`; propriedade `Curso.linhagem_id`; `services.abrir_nova_versao(curso, por, motivo) -> Curso`; `permissions.pode_abrir_versao(usuario, curso) -> bool`.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_versoes.py`:

```python
import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel, TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo, Arquivo, Curso


@pytest.fixture
def curso_publicado(dados_curso, aluno, professor, coordenador, arquivo_qualquer):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    slides = curso.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Anexo.objects.create(
        entregavel=slides, tipo_midia=TipoMidia.ARQUIVO, titulo="Slides",
        arquivo=arquivo_qualquer, enviado_por=aluno,
    )
    plano = curso.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    secao = plano.secoes.first()
    secao.conteudo = "<p>Ementa da primeira versao</p>"
    secao.save()
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    return curso


@pytest.mark.django_db
def test_primeira_versao_e_a_raiz(curso_publicado):
    assert curso_publicado.versao == 1
    assert curso_publicado.raiz is None
    assert curso_publicado.linhagem_id == curso_publicado.pk


@pytest.mark.django_db
def test_nova_versao_clona_conteudo_e_zera_os_estados(curso_publicado, coordenador):
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Faltam atividades praticas.")
    assert nova.versao == 2
    assert nova.linhagem_id == curso_publicado.pk
    assert nova.status == StatusCurso.RASCUNHO
    assert nova.entregaveis.count() == 5
    assert set(nova.entregaveis.values_list("status", flat=True)) == {StatusEntregavel.RASCUNHO}
    plano = nova.entregaveis.get(tipo=TipoEntregavel.PLANO_ENSINO)
    assert "primeira versao" in plano.secoes.first().conteudo


@pytest.mark.django_db
def test_nova_versao_compartilha_o_arquivo_em_disco(curso_publicado, coordenador):
    antes = Arquivo.objects.count()
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Melhorar os slides.")
    assert Arquivo.objects.count() == antes
    original = curso_publicado.entregaveis.get(tipo=TipoEntregavel.SLIDES).anexos.first()
    copia = nova.entregaveis.get(tipo=TipoEntregavel.SLIDES).anexos.first()
    assert copia.pk != original.pk
    assert copia.arquivo_id == original.arquivo_id


@pytest.mark.django_db
def test_historico_de_revisao_nao_e_copiado(curso_publicado, coordenador, professor):
    from apps.cursos.models import Revisao

    slides = curso_publicado.entregaveis.get(tipo=TipoEntregavel.SLIDES)
    Revisao.objects.create(entregavel=slides, revisor=professor, decisao=Revisao.APROVADO)
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    assert Revisao.objects.filter(entregavel__curso=nova).count() == 0


@pytest.mark.django_db
def test_versao_anterior_continua_publicada_durante_o_trabalho(curso_publicado, coordenador):
    services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    curso_publicado.refresh_from_db()
    assert curso_publicado.status == StatusCurso.PUBLICADO


@pytest.mark.django_db
def test_publicar_a_nova_substitui_a_anterior(curso_publicado, coordenador, professor, aluno):
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    services.adicionar_membro(nova, aluno, por=professor)
    nova.entregaveis.update(status=StatusEntregavel.APROVADO)
    nova.refresh_from_db()
    services.submeter_ao_coordenador(nova, por=professor)
    services.publicar_curso(nova, por=coordenador)
    curso_publicado.refresh_from_db()
    nova.refresh_from_db()
    assert nova.status == StatusCurso.PUBLICADO
    assert curso_publicado.status == StatusCurso.SUBSTITUIDO


@pytest.mark.django_db
def test_duas_versoes_em_producao_ao_mesmo_tempo_sao_recusadas(curso_publicado, coordenador):
    services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Primeira tentativa.")
    with pytest.raises(ValidationError):
        services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Segunda tentativa.")


@pytest.mark.django_db
def test_motivo_e_obrigatorio(curso_publicado, coordenador):
    with pytest.raises(ValidationError):
        services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="  ")


@pytest.mark.django_db
def test_so_se_abre_versao_de_curso_publicado(dados_curso, coordenador):
    curso = services.criar_curso(**dados_curso)
    with pytest.raises(ValidationError):
        services.abrir_nova_versao(curso, por=coordenador, motivo="Ainda nao publicado.")


@pytest.mark.django_db
def test_aluno_nao_abre_versao(curso_publicado, aluno):
    with pytest.raises(PermissionDenied):
        services.abrir_nova_versao(curso_publicado, por=aluno, motivo="Quero mexer.")


@pytest.mark.django_db
def test_professor_responsavel_abre_versao(curso_publicado, professor):
    nova = services.abrir_nova_versao(curso_publicado, por=professor, motivo="Atualizar bibliografia.")
    assert nova.versao == 2


@pytest.mark.django_db
def test_substituido_nao_volta_ao_ar(curso_publicado, coordenador, professor, aluno):
    nova = services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Atualizar.")
    services.adicionar_membro(nova, aluno, por=professor)
    nova.entregaveis.update(status=StatusEntregavel.APROVADO)
    nova.refresh_from_db()
    services.submeter_ao_coordenador(nova, por=professor)
    services.publicar_curso(nova, por=coordenador)
    curso_publicado.refresh_from_db()
    with pytest.raises(ValidationError):
        services.publicar_curso(curso_publicado, por=coordenador)
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_versoes.py -v`
Expected: FAIL — `AttributeError: 'Curso' object has no attribute 'linhagem_id'`.

- [ ] **Step 3: Acrescentar os campos de versão**

Em `apps/cursos/models/curso.py`, dentro da classe `Curso`:

```python
    raiz = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="versoes",
        verbose_name="primeira versao desta linhagem",
    )
    versao = models.PositiveSmallIntegerField("versao", default=1)
    motivo_versao = models.TextField("motivo desta versao", blank=True)
```

E o método:

```python
    @property
    def linhagem_id(self):
        """Identifica a linhagem: a v1 e a propria raiz das demais."""
        return self.raiz_id or self.pk
```

- [ ] **Step 4: Implementar o serviço de clonagem**

Ao fim de `apps/cursos/services.py`:

```python
from apps.cursos.models import Secao


@transaction.atomic
def abrir_nova_versao(curso, por, motivo):
    """Clona o curso publicado numa nova versao na edicao corrente.

    A versao anterior continua publicada e solicitavel durante todo o trabalho;
    ela so vira SUBSTITUIDO quando a nova for publicada (spec 4.5).
    """
    permissions.garante(permissions.pode_abrir_versao(por, curso), "Somente o professor responsavel ou a coordenacao.")
    if curso.status != StatusCurso.PUBLICADO:
        raise ValidationError("So se abre nova versao de curso publicado.")
    if not (motivo or "").strip():
        raise ValidationError("Informe o motivo da nova versao.")

    linhagem = curso.linhagem_id
    em_andamento = Curso.objects.filter(
        models.Q(pk=linhagem) | models.Q(raiz_id=linhagem)
    ).exclude(status__in=[StatusCurso.PUBLICADO, StatusCurso.SUBSTITUIDO, StatusCurso.DESPUBLICADO])
    if em_andamento.exists():
        raise ValidationError("Ja existe uma versao deste curso em producao.")

    from apps.edicoes.models import Edicao

    ultima = Curso.objects.filter(
        models.Q(pk=linhagem) | models.Q(raiz_id=linhagem)
    ).order_by("-versao").first()

    nova = Curso.objects.create(
        titulo=curso.titulo,
        resumo=curso.resumo,
        edicao=Edicao.objects.corrente() or curso.edicao,
        professor_responsavel=curso.professor_responsavel,
        tipo_publico=curso.tipo_publico,
        etapa_ano=curso.etapa_ano,
        publico_descricao=curso.publico_descricao,
        referencial=curso.referencial,
        carga_horaria=curso.carga_horaria,
        formato=curso.formato,
        pre_requisitos=curso.pre_requisitos,
        palavras_chave=curso.palavras_chave,
        raiz_id=linhagem,
        versao=ultima.versao + 1,
        motivo_versao=motivo,
    )
    nova.temas.set(curso.temas.all())
    nova.competencias.set(curso.competencias.all())
    atualizar_vetor_temas(nova)

    for entregavel in curso.entregaveis.prefetch_related("secoes", "anexos"):
        copia = Entregavel.objects.create(curso=nova, tipo=entregavel.tipo)
        for secao in entregavel.secoes.all():
            Secao.objects.create(
                entregavel=copia, titulo=secao.titulo, ordem=secao.ordem, conteudo=secao.conteudo
            )
        for anexo in entregavel.anexos.all():
            # Aponta para o MESMO Arquivo: clonar um curso nao pode clonar
            # gigabytes de video (spec 4.6).
            Anexo.objects.create(
                entregavel=copia,
                tipo_midia=anexo.tipo_midia,
                arquivo=anexo.arquivo,
                url=anexo.url,
                titulo=anexo.titulo,
                descricao=anexo.descricao,
                referencia_bibliografica=anexo.referencia_bibliografica,
                rotulo=anexo.rotulo,
                tipo_pratica=anexo.tipo_pratica,
                duracao_minutos=anexo.duracao_minutos,
                enviado_por=anexo.enviado_por,
            )

    LogTransicaoCurso.objects.create(
        curso=nova, de_status=StatusCurso.RASCUNHO, para_status=StatusCurso.RASCUNHO,
        usuario=por, observacao=f"Versao {nova.versao} aberta a partir da versao {curso.versao}: {motivo}",
    )
    return nova
```

O histórico de `Revisao` **não** é copiado: ele pertence à versão que o produziu (spec §4.5).

- [ ] **Step 5: Substituir a versão anterior ao publicar**

Em `apps/cursos/services.py`, dentro de `publicar_curso`, logo após `_transicionar(curso, StatusCurso.PUBLICADO, por)`:

```python
    anteriores = Curso.objects.filter(
        models.Q(pk=curso.linhagem_id) | models.Q(raiz_id=curso.linhagem_id),
        status=StatusCurso.PUBLICADO,
    ).exclude(pk=curso.pk)
    for anterior in anteriores:
        _transicionar(
            anterior, StatusCurso.SUBSTITUIDO, por,
            observacao=f"Substituido pela versao {curso.versao}.",
        )
```

Isso mantém a invariante que faz o catálogo funcionar sem esforço: **no máximo uma versão publicada por linhagem**. Por causa dela, `filter(status=PUBLICADO)` já devolve uma linha por curso, sem `DISTINCT ON`.

Em `apps/cursos/permissions.py`:

```python
def pode_abrir_versao(usuario, curso):
    return usuario.e_coordenador or (usuario.e_professor and e_responsavel(usuario, curso))
```

- [ ] **Step 6: Migrar, rodar e commitar**

```bash
python manage.py makemigrations cursos --name versoes
pytest apps/cursos/tests/test_versoes.py -v
git add apps/cursos
git commit -m "feat(cursos): novas versoes de curso publicado compartilhando arquivos"
```

Expected: PASS (12 testes).

---

### Task 6: Versões no catálogo e nas telas

**Files:**
- Create: `templates/cursos/nova_versao.html`
- Modify: `apps/cursos/views/coordenador.py`, `apps/cursos/views/__init__.py`, `apps/cursos/urls.py`, `apps/catalogo/views.py`, `templates/catalogo/curso.html`, `templates/cursos/curso.html`
- Test: `apps/catalogo/tests/test_versoes_no_catalogo.py`

**Interfaces:**
- Consumes: `abrir_nova_versao` (Task 5).
- Produces: rota `nova_versao` (`<int:pk>`); página pública mostrando a versão e a edição.

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/catalogo/tests/test_versoes_no_catalogo.py`:

```python
import pytest
from django.urls import reverse

from apps.cursos import services
from apps.cursos.choices import StatusCurso, StatusEntregavel


@pytest.fixture
def curso_publicado(dados_curso, aluno, professor, coordenador):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=professor)
    curso.entregaveis.update(status=StatusEntregavel.APROVADO)
    curso.refresh_from_db()
    services.submeter_ao_coordenador(curso, por=professor)
    services.publicar_curso(curso, por=coordenador)
    return curso


def publica_nova_versao(curso, professor, coordenador, aluno):
    nova = services.abrir_nova_versao(curso, por=coordenador, motivo="Melhorias.")
    services.adicionar_membro(nova, aluno, por=professor)
    nova.entregaveis.update(status=StatusEntregavel.APROVADO)
    nova.refresh_from_db()
    services.submeter_ao_coordenador(nova, por=professor)
    services.publicar_curso(nova, por=coordenador)
    return nova


@pytest.mark.django_db
def test_catalogo_mostra_a_linhagem_uma_vez_so(client, curso_publicado, professor, coordenador, aluno):
    publica_nova_versao(curso_publicado, professor, coordenador, aluno)
    conteudo = client.get(reverse("catalogo")).content.decode()
    assert conteudo.count(curso_publicado.titulo) == 1


@pytest.mark.django_db
def test_durante_a_producao_da_nova_a_antiga_continua_no_catalogo(client, curso_publicado, coordenador):
    services.abrir_nova_versao(curso_publicado, por=coordenador, motivo="Melhorias.")
    assert curso_publicado.titulo in client.get(reverse("catalogo")).content.decode()


@pytest.mark.django_db
def test_versao_substituida_sai_do_catalogo_mas_a_pagina_dela_some(client, curso_publicado, professor, coordenador, aluno):
    publica_nova_versao(curso_publicado, professor, coordenador, aluno)
    curso_publicado.refresh_from_db()
    assert curso_publicado.status == StatusCurso.SUBSTITUIDO
    assert client.get(reverse("catalogo_curso", args=[curso_publicado.pk])).status_code == 404


@pytest.mark.django_db
def test_pagina_publica_mostra_a_versao(client, curso_publicado, professor, coordenador, aluno):
    nova = publica_nova_versao(curso_publicado, professor, coordenador, aluno)
    conteudo = client.get(reverse("catalogo_curso", args=[nova.pk])).content.decode()
    assert "versao 2" in conteudo.lower()


@pytest.mark.django_db
def test_coordenador_abre_nova_versao_pela_tela(client, curso_publicado, coordenador):
    client.force_login(coordenador)
    resposta = client.post(
        reverse("nova_versao", args=[curso_publicado.pk]),
        {"motivo": "Curso incompleto: faltam atividades desplugadas."},
        follow=True,
    )
    assert resposta.status_code == 200
    from apps.cursos.models import Curso

    assert Curso.objects.filter(raiz=curso_publicado, versao=2).exists()


@pytest.mark.django_db
def test_aluno_nao_abre_nova_versao_pela_tela(client, curso_publicado, aluno):
    client.force_login(aluno)
    resposta = client.post(reverse("nova_versao", args=[curso_publicado.pk]), {"motivo": "Quero mexer."})
    assert resposta.status_code == 403
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/catalogo/tests/test_versoes_no_catalogo.py -v`
Expected: FAIL — `NoReverseMatch: Reverse for 'nova_versao' not found`.

- [ ] **Step 3: Escrever a view**

Em `apps/cursos/views/coordenador.py`:

```python
@login_required
def nova_versao(request, pk):
    curso = get_object_or_404(Curso, pk=pk)
    if request.method == "POST":
        try:
            nova = services.abrir_nova_versao(curso, por=request.user, motivo=request.POST.get("motivo", ""))
        except ValidationError as erro:
            messages.error(request, erro.messages[0])
            return redirect("curso", pk=curso.pk)
        messages.success(request, f"Versao {nova.versao} aberta. Monte a equipe para comecar.")
        return redirect("equipe", pk=nova.pk)
    return render(request, "cursos/nova_versao.html", {"curso": curso})
```

Acrescente `nova_versao` a `apps/cursos/views/__init__.py` e a rota:

```python
    path("cursos/<int:pk>/nova-versao/", views.nova_versao, name="nova_versao"),
```

- [ ] **Step 4: Escrever o template e os links**

`templates/cursos/nova_versao.html`:

```html
{% extends "base.html" %}
{% block titulo %}Nova versao de {{ curso.titulo }}{% endblock %}
{% block conteudo %}
  <h1>Nova versao de {{ curso.titulo }}</h1>
  <p>A versao {{ curso.versao }} continua publicada e disponivel para solicitacao
     enquanto a nova estiver sendo produzida. Ela sera substituida quando a nova for aprovada.</p>
  <form method="post">
    {% csrf_token %}
    <label for="motivo">Por que esta versao esta sendo aberta?</label>
    <textarea id="motivo" name="motivo" rows="4" required></textarea>
    <button type="submit">Abrir nova versao</button>
  </form>
{% endblock %}
```

Em `templates/cursos/curso.html`, antes do fim do bloco:

```html
  {% if curso.status == "PUBLICADO" and user.e_coordenador or curso.status == "PUBLICADO" and user == curso.professor_responsavel %}
    <p><a href="{% url 'nova_versao' curso.pk %}">Abrir nova versao</a></p>
  {% endif %}
  {% if curso.versao > 1 %}<p>Versao {{ curso.versao }} &mdash; {{ curso.motivo_versao }}</p>{% endif %}
```

Em `templates/catalogo/curso.html`, logo abaixo do título:

```html
  <p class="versao">Versao {{ curso.versao }} &middot; {{ curso.edicao }}</p>
```

- [ ] **Step 5: Rodar a suíte inteira e commitar**

```bash
pytest -v
git add apps/cursos apps/catalogo templates
git commit -m "feat(catalogo): catalogo por linhagem e abertura de nova versao pela tela"
```

Expected: PASS — a consulta do catálogo não mudou: a invariante da Task 5 garante uma versão publicada por linhagem.

---

### Task 7: Rotinas de manutenção

**Files:**
- Create: `apps/cursos/management/__init__.py`, `apps/cursos/management/commands/__init__.py`, `apps/cursos/management/commands/limpar_uploads.py`, `apps/cursos/management/commands/limpar_arquivos_orfaos.py`
- Test: `apps/cursos/tests/test_manutencao.py`

**Interfaces:**
- Consumes: `UploadEmAndamento`, `Arquivo` (Tasks 1 e Plano 2).
- Produces: comandos `limpar_uploads` e `limpar_arquivos_orfaos`, ambos com `--horas` (padrão 24).

- [ ] **Step 1: Escrever o teste (vai falhar)**

`apps/cursos/tests/test_manutencao.py`:

```python
import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.cursos import services
from apps.cursos.choices import TipoEntregavel, TipoMidia
from apps.cursos.models import Anexo, Arquivo, UploadEmAndamento


@pytest.fixture
def entregavel_videos(dados_curso, aluno):
    curso = services.criar_curso(**dados_curso)
    services.adicionar_membro(curso, aluno, por=curso.professor_responsavel)
    return curso.entregaveis.get(tipo=TipoEntregavel.VIDEOS)


@pytest.mark.django_db
def test_upload_antigo_e_removido_com_o_arquivo_parcial(entregavel_videos, aluno):
    upload = UploadEmAndamento.objects.create(
        usuario=aluno, entregavel=entregavel_videos, nome_original="aula.mp4", tamanho_total=10
    )
    upload.acrescentar(b"123")
    caminho = upload.caminho()
    UploadEmAndamento.objects.filter(pk=upload.pk).update(
        atualizado_em=timezone.now() - datetime.timedelta(hours=25)
    )
    call_command("limpar_uploads")
    assert UploadEmAndamento.objects.count() == 0
    assert not caminho.exists()


@pytest.mark.django_db
def test_upload_recente_e_preservado(entregavel_videos, aluno):
    UploadEmAndamento.objects.create(
        usuario=aluno, entregavel=entregavel_videos, nome_original="aula.mp4", tamanho_total=10
    )
    call_command("limpar_uploads")
    assert UploadEmAndamento.objects.count() == 1


@pytest.mark.django_db
def test_arquivo_orfao_e_antigo_e_removido(arquivo_qualquer):
    caminho = arquivo_qualquer.arquivo.path
    Arquivo.objects.filter(pk=arquivo_qualquer.pk).update(
        enviado_em=timezone.now() - datetime.timedelta(hours=25)
    )
    call_command("limpar_arquivos_orfaos")
    assert Arquivo.objects.count() == 0
    import os

    assert not os.path.exists(caminho)


@pytest.mark.django_db
def test_arquivo_orfao_recente_e_preservado(arquivo_qualquer):
    """Entre o fim do upload e o salvamento do Anexo existe uma janela em que o
    arquivo nao tem referencia nenhuma e nao e lixo (spec 13)."""
    call_command("limpar_arquivos_orfaos")
    assert Arquivo.objects.count() == 1


@pytest.mark.django_db
def test_arquivo_referenciado_por_qualquer_versao_e_preservado(arquivo_qualquer, entregavel_videos, aluno):
    Anexo.objects.create(
        entregavel=entregavel_videos, tipo_midia=TipoMidia.VIDEO, titulo="Aula",
        arquivo=arquivo_qualquer, duracao_minutos=7, enviado_por=aluno,
    )
    Arquivo.objects.filter(pk=arquivo_qualquer.pk).update(
        enviado_em=timezone.now() - datetime.timedelta(days=400)
    )
    call_command("limpar_arquivos_orfaos")
    assert Arquivo.objects.count() == 1
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/cursos/tests/test_manutencao.py -v`
Expected: FAIL — `CommandError: Unknown command: 'limpar_uploads'`.

- [ ] **Step 3: Escrever os comandos**

```bash
mkdir -p apps/cursos/management/commands
touch apps/cursos/management/__init__.py apps/cursos/management/commands/__init__.py
```

`apps/cursos/management/commands/limpar_uploads.py`:

```python
import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cursos.models import UploadEmAndamento


class Command(BaseCommand):
    help = "Remove uploads em blocos abandonados. Rode por cron."

    def add_arguments(self, parser):
        parser.add_argument("--horas", type=int, default=24)

    def handle(self, *args, **opcoes):
        corte = timezone.now() - datetime.timedelta(hours=opcoes["horas"])
        abandonados = UploadEmAndamento.objects.filter(atualizado_em__lt=corte)
        total = 0
        for upload in abandonados:
            upload.caminho().unlink(missing_ok=True)
            upload.delete()
            total += 1
        # Sem esta rotina, o disco enche de fragmentos de video que ninguem reclamou.
        self.stdout.write(self.style.SUCCESS(f"{total} uploads abandonados removidos."))
```

`apps/cursos/management/commands/limpar_arquivos_orfaos.py`:

```python
import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.cursos.models import Arquivo


class Command(BaseCommand):
    help = "Remove arquivos que nenhum anexo de nenhuma versao referencia. Rode por cron."

    def add_arguments(self, parser):
        parser.add_argument("--horas", type=int, default=24)

    def handle(self, *args, **opcoes):
        corte = timezone.now() - datetime.timedelta(hours=opcoes["horas"])
        total = 0
        with transaction.atomic():
            # Idade + select_for_update, e nao contador de referencias: contador
            # denormalizado desanda em exclusao em lote, rollback ou clone de versao,
            # e o modo de falha e apagar arquivo em uso (spec 13).
            orfaos = (
                Arquivo.objects.filter(anexos__isnull=True, enviado_em__lt=corte)
                .select_for_update()
            )
            for arquivo in orfaos:
                arquivo.arquivo.delete(save=False)
                arquivo.delete()
                total += 1
        self.stdout.write(self.style.SUCCESS(f"{total} arquivos orfaos removidos."))
```

- [ ] **Step 4: Rodar e commitar**

```bash
pytest apps/cursos/tests/test_manutencao.py -v
git add apps/cursos
git commit -m "feat(cursos): rotinas de limpeza de uploads e arquivos orfaos"
```

Expected: PASS (5 testes).

---

### Task 8: Deploy, backup e restauração

**Files:**
- Create: `deploy/nginx.conf`, `deploy/integrasi.service`, `deploy/crontab`, `deploy/backup.sh`, `deploy/restaurar-teste.sh`, `docs/operacao.md`, `templates/403.html`, `templates/404.html`, `templates/500.html`
- Modify: `pyproject.toml` (gunicorn), `.env.example`
- Test: `tests/test_producao.py`

**Interfaces:**
- Consumes: todo o sistema.
- Produces: arquivos de configuração prontos para copiar ao servidor e o roteiro de operação em `docs/operacao.md`.

- [ ] **Step 1: Escrever o teste da configuração de produção (vai falhar)**

`tests/test_producao.py`:

```python
from pathlib import Path

import pytest
from django.conf import settings

DEPLOY = Path(settings.BASE_DIR) / "deploy"


def test_nginx_marca_a_midia_como_internal():
    """Sem internal, a URL direta burla toda a checagem de permissao (spec 10)."""
    conf = (DEPLOY / "nginx.conf").read_text()
    assert "location /protegido/" in conf
    assert "internal;" in conf


def test_nginx_aceita_o_bloco_de_upload():
    conf = (DEPLOY / "nginx.conf").read_text()
    assert "client_max_body_size" in conf


def test_cron_tem_as_tres_rotinas():
    crontab = (DEPLOY / "crontab").read_text()
    assert "enviar_notificacoes" in crontab
    assert "limpar_uploads" in crontab
    assert "limpar_arquivos_orfaos" in crontab


def test_backup_cobre_banco_e_midia():
    script = (DEPLOY / "backup.sh").read_text()
    assert "pg_dump" in script
    assert "restic" in script


@pytest.mark.parametrize("chave", ["SECRET_KEY", "DATABASE_URL", "ALLOWED_HOSTS", "USAR_X_ACCEL"])
def test_env_example_documenta_as_chaves(chave):
    assert chave in (Path(settings.BASE_DIR) / ".env.example").read_text()
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest tests/test_producao.py -v`
Expected: FAIL — `FileNotFoundError: deploy/nginx.conf`.

- [ ] **Step 3: Escrever a configuração do nginx**

```bash
mkdir -p deploy
```

`deploy/nginx.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name integrasi.ufsm.br;

    ssl_certificate     /etc/ssl/certs/integrasi.crt;
    ssl_certificate_key /etc/ssl/private/integrasi.key;

    # Um bloco de upload de video tem 5 MB; a folga cobre os demais anexos.
    client_max_body_size 60M;
    client_body_timeout 300s;
    proxy_read_timeout 300s;

    location /static/ {
        alias /srv/integrasi/staticfiles/;
        expires 30d;
    }

    # Entrega dos materiais. INTERNAL: so o Django, depois de checar a permissao,
    # consegue apontar para ca com X-Accel-Redirect. Sem esta diretiva, qualquer
    # pessoa com a URL baixa material nao aprovado (spec 8, 10).
    location /protegido/ {
        internal;
        alias /srv/integrasi/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name integrasi.ufsm.br;
    return 301 https://$host$request_uri;
}
```

- [ ] **Step 4: Escrever o serviço e o cron**

```bash
pip install gunicorn
```

Acrescente `gunicorn` às dependências do `pyproject.toml`.

`deploy/integrasi.service`:

```ini
[Unit]
Description=IntegraSI
After=network.target postgresql.service

[Service]
User=integrasi
Group=www-data
WorkingDirectory=/srv/integrasi
EnvironmentFile=/srv/integrasi/.env
ExecStart=/srv/integrasi/.venv/bin/gunicorn config.wsgi:application \
    --bind 127.0.0.1:8000 --workers 3 --timeout 300
Restart=always

[Install]
WantedBy=multi-user.target
```

O `--timeout 300` acompanha o `proxy_read_timeout` do nginx: um bloco de 5 MB numa conexão ruim leva minutos.

`deploy/crontab`:

```cron
# IntegraSI - instalar com: crontab -u integrasi deploy/crontab
*/5 * * * * cd /srv/integrasi && .venv/bin/python manage.py enviar_notificacoes >> /var/log/integrasi/cron.log 2>&1
17 3 * * * cd /srv/integrasi && .venv/bin/python manage.py limpar_uploads >> /var/log/integrasi/cron.log 2>&1
32 3 * * * cd /srv/integrasi && .venv/bin/python manage.py limpar_arquivos_orfaos >> /var/log/integrasi/cron.log 2>&1
5 2 * * * /srv/integrasi/deploy/backup.sh >> /var/log/integrasi/backup.log 2>&1
```

- [ ] **Step 5: Escrever o backup e o teste de restauração**

`deploy/backup.sh`:

```bash
#!/usr/bin/env bash
# Backup do IntegraSI. Sao dois problemas diferentes (spec 13):
#   - o banco e pequeno e o que salva de erro humano -> pg_dump diario, 30 dias
#   - a midia e grande e cresce -> copia incremental deduplicada para fora do servidor
set -euo pipefail

DESTINO_SQL=/srv/backups/sql
MEDIA=/srv/integrasi/media
export RESTIC_REPOSITORY="${RESTIC_REPOSITORY:?defina o repositorio restic}"
export RESTIC_PASSWORD_FILE=/srv/integrasi/.restic-senha

mkdir -p "$DESTINO_SQL"
ARQUIVO="$DESTINO_SQL/integrasi-$(date +%Y%m%d).sql.gz"

pg_dump --no-owner integrasi | gzip > "$ARQUIVO"
find "$DESTINO_SQL" -name 'integrasi-*.sql.gz' -mtime +30 -delete

restic backup "$MEDIA" "$DESTINO_SQL" --tag integrasi
restic forget --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --prune

echo "Backup concluido em $(date --iso-8601=seconds)"
```

`deploy/restaurar-teste.sh`:

```bash
#!/usr/bin/env bash
# Backup que nunca foi restaurado nao e backup (spec 13). Rode este script depois
# do primeiro backup, e uma vez por semestre.
set -euo pipefail

BANCO_TESTE=integrasi_restauracao
ULTIMO=$(ls -t /srv/backups/sql/integrasi-*.sql.gz | head -1)

echo "Restaurando $ULTIMO em $BANCO_TESTE"
dropdb --if-exists "$BANCO_TESTE"
createdb "$BANCO_TESTE"
gunzip -c "$ULTIMO" | psql -q "$BANCO_TESTE"

CURSOS=$(psql -tAc "select count(*) from cursos_curso" "$BANCO_TESTE")
USUARIOS=$(psql -tAc "select count(*) from contas_usuario" "$BANCO_TESTE")
echo "Restaurado: $CURSOS cursos, $USUARIOS usuarios"

echo "Conferindo um arquivo de midia do backup:"
restic restore latest --target /tmp/restauracao-teste --include /srv/integrasi/media
find /tmp/restauracao-teste -type f | head -3

dropdb "$BANCO_TESTE"
rm -rf /tmp/restauracao-teste
echo "Restauracao de teste concluida com sucesso."
```

```bash
chmod +x deploy/backup.sh deploy/restaurar-teste.sh
```

- [ ] **Step 6: Escrever as páginas de erro**

A spec §11 pede 403 e 404 com página própria, sem stack trace. Com `DEBUG=False`, o Django usa `templates/<codigo>.html` automaticamente. Acrescente o teste a `tests/test_producao.py`:

```python
@pytest.mark.django_db
def test_paginas_de_erro_existem_e_nao_vazam_detalhe(client, settings):
    settings.DEBUG = False
    for codigo in ("403", "404", "500"):
        conteudo = (Path(settings.BASE_DIR) / "templates" / f"{codigo}.html").read_text()
        assert "{% extends" in conteudo
        assert "Traceback" not in conteudo
```

Rode e veja falhar: `pytest tests/test_producao.py -v`
Expected: FAIL — `FileNotFoundError: templates/403.html`.

`templates/403.html`:

```html
{% extends "base.html" %}
{% block titulo %}Acesso negado{% endblock %}
{% block conteudo %}
  <h1>Acesso negado</h1>
  <p>Voce nao tem permissao para ver esta pagina. Se acredita que deveria ter,
     fale com o professor responsavel pelo curso ou com a coordenacao.</p>
  <p><a href="{% url 'catalogo' %}">Voltar ao inicio</a></p>
{% endblock %}
```

`templates/404.html`:

```html
{% extends "base.html" %}
{% block titulo %}Pagina nao encontrada{% endblock %}
{% block conteudo %}
  <h1>Pagina nao encontrada</h1>
  <p>O endereco nao existe, ou o curso que voce procura saiu do catalogo.</p>
  <p><a href="{% url 'catalogo' %}">Ver os cursos disponiveis</a></p>
{% endblock %}
```

`templates/500.html` — este **não** estende `base.html`: se o erro estiver no banco ou no contexto, renderizar o template completo falharia de novo e o visitante veria a página branca do servidor.

```html
<!doctype html>
<html lang="pt-br">
<head><meta charset="utf-8"><title>Erro no sistema &mdash; IntegraSI</title></head>
<body>
  <h1>Algo deu errado</h1>
  <p>O sistema encontrou um erro inesperado. A equipe foi registrada nos logs do servidor.</p>
  <p><a href="/">Voltar ao inicio</a></p>
</body>
</html>
```

O teste acima confere `{% extends`, então ajuste-o para exigir isso apenas de 403 e 404:

```python
@pytest.mark.django_db
def test_paginas_de_erro_existem_e_nao_vazam_detalhe(client, settings):
    settings.DEBUG = False
    for codigo in ("403", "404"):
        conteudo = (Path(settings.BASE_DIR) / "templates" / f"{codigo}.html").read_text()
        assert "{% extends" in conteudo
        assert "Traceback" not in conteudo
    quinhentos = (Path(settings.BASE_DIR) / "templates" / "500.html").read_text()
    assert "{% extends" not in quinhentos
    assert "<!doctype html>" in quinhentos.lower()
```

Run: `pytest tests/test_producao.py -v`
Expected: PASS.

- [ ] **Step 7: Escrever o roteiro de operação**

`docs/operacao.md`:

```markdown
# Operacao do IntegraSI

## Instalacao no servidor

1. Crie o usuario `integrasi` e o diretorio `/srv/integrasi`.
2. Clone o repositorio, crie o virtualenv e instale as dependencias.
3. Copie `.env.example` para `.env` e preencha: `SECRET_KEY` (gere uma nova),
   `DEBUG=False`, `ALLOWED_HOSTS`, `DATABASE_URL`, `USAR_X_ACCEL=True` e as
   variaveis de e-mail.
4. `python manage.py migrate && python manage.py collectstatic --noinput`
5. `python manage.py loaddata bncc_computacao temas_iniciais`
6. `python manage.py criar_coordenador --email ... --nome ... --cpf ... --siape ... --senha ...`
7. Copie `deploy/integrasi.service` para `/etc/systemd/system/`, habilite e inicie.
8. Copie `deploy/nginx.conf` para os sites do nginx, ajuste o dominio e os
   certificados, e recarregue.
9. `crontab -u integrasi deploy/crontab`
10. Rode `deploy/backup.sh` uma vez e depois `deploy/restaurar-teste.sh`.

## O volume de midia

Ate 3 GB de video por curso; com ~8 equipes por edicao, ~24 GB por semestre e
~240 GB em cinco anos. `media/` deve ficar em volume proprio, separado do sistema.

## Rotinas

| Quando | O que |
|---|---|
| A cada 5 min | `enviar_notificacoes` (lotes de 50, sob flock) |
| Diario 03:17 | `limpar_uploads` (blocos abandonados ha mais de 24 h) |
| Diario 03:32 | `limpar_arquivos_orfaos` (sem anexo e com mais de 24 h) |
| Diario 02:05 | `backup.sh` |
| A cada semestre | `restaurar-teste.sh` |

## Quando algo da errado

- **E-mails nao saem:** veja `ultimo_erro` na tabela de notificacoes pelo Admin. A
  operacao do sistema nao para por isso — por desenho.
- **Upload de video falha sempre no mesmo ponto:** confira `client_max_body_size`
  no nginx e `DATA_UPLOAD_MAX_MEMORY_SIZE` no Django; ambos precisam ser maiores
  que o bloco de 5 MB.
- **Download devolve 404 do nginx:** o `alias` de `/protegido/` precisa terminar
  com barra e apontar para o mesmo caminho de `MEDIA_ROOT`.
- **Disco enchendo:** rode `limpar_uploads` e `limpar_arquivos_orfaos` na mao e
  confira se o cron esta instalado para o usuario `integrasi`.
- **Visitante viu pagina de erro do servidor:** confirme `DEBUG=False` e que
  `templates/403.html`, `404.html` e `500.html` foram para o servidor.
```

- [ ] **Step 8: Rodar a suíte inteira e commitar**

```bash
pytest -v
git add deploy docs templates pyproject.toml .env.example tests
git commit -m "chore(deploy): nginx, systemd, cron, backup, paginas de erro e operacao"
```

Expected: PASS — todos os testes dos quatro planos.

---

## Entregue ao fim deste plano

O sistema completo do módulo de produção, em condições de rodar em produção: upload de vídeo de 1 GB que sobrevive a queda de conexão, entrega de arquivo que não prende o servidor, cursos que evoluem em versões sem sumir do catálogo, rotinas de manutenção instaladas e um backup que já foi restaurado ao menos uma vez.

O próximo passo é o **módulo de execução** (§1.1 da spec): frequência, avaliação e certificação, construídos a partir de `turmas`, sem tocar no núcleo de produção.
