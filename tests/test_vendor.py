"""As bibliotecas de terceiros sao as que `static/VENDOR.md` diz que sao.

O projeto vendoriza tudo de proposito (spec 13), e ja havia teste reprovando quem
carregasse de CDN. O que faltava era saber O QUE esta vendorizado: ate 05/09/2026
nenhuma versao estava escrita em lugar nenhum, e a do Tippy nao aparecia nem
dentro do proprio arquivo minificado - foi identificada comparando SHA-256 com a
origem.

Estes testes fecham a outra ponta. Documentacao que ninguem confere envelhece
calada, e aqui envelhecer calada e pior que em outros lugares: um arquivo trocado
no disco e codigo executando no navegador de quem visita o catalogo.

O que estes testes NAO fazem: carregar JavaScript. Eles provam que os arquivos
sao os documentados, e nao que a biblioteca funciona. Essa parte e olhar a tela,
e esta escrita no proprio VENDOR.md.
"""

import hashlib
import re
from pathlib import Path

import pytest
from django.conf import settings

RAIZ = Path(settings.BASE_DIR)
VENDOR = RAIZ / "static" / "VENDOR.md"


def documentados():
    """Os pares (arquivo, sha256) lidos da segunda tabela do VENDOR.md."""
    texto = VENDOR.read_text(encoding="utf-8")
    return dict(re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$", texto, re.M))


def test_o_vendor_md_existe_e_lista_alguma_coisa():
    """Guarda do proprio arquivo de testes: um regex que deixasse de casar faria
    os dois testes abaixo passarem sobre uma lista VAZIA, verdes para sempre."""
    assert VENDOR.exists(), "static/VENDOR.md sumiu"
    assert len(documentados()) >= 6, documentados()


@pytest.mark.parametrize("caminho", sorted(documentados()))
def test_o_arquivo_em_disco_e_o_documentado(caminho):
    """SHA-256 do disco contra o do VENDOR.md.

    Falha aqui significa uma de duas coisas, e as duas pedem atencao: ou alguem
    trocou a biblioteca sem atualizar a documentacao, ou o arquivo foi alterado
    sem ninguem saber.
    """
    arquivo = RAIZ / caminho
    assert arquivo.exists(), f"{caminho} está no VENDOR.md e não está no disco"

    digest = hashlib.sha256(arquivo.read_bytes()).hexdigest()

    assert digest == documentados()[caminho], (
        f"{caminho} mudou: o VENDOR.md diz {documentados()[caminho][:16]}… "
        f"e o disco tem {digest[:16]}…"
    )


def test_toda_biblioteca_vendorizada_esta_documentada():
    """O caminho inverso: arquivo novo em `static/` que ninguem documentou.

    Sem isto, acrescentar uma biblioteca e esquecer o VENDOR.md passa verde, e o
    arquivo volta a ser o que era antes deste trabalho: codigo de terceiro no
    repositorio sem versao, sem origem e sem hash.

    O criterio e o NOME: `.min.` e a marca de arquivo que veio pronto de fora. O
    codigo proprio do projeto (`ajuda.js`, `editor.js`, `upload.js`, `menu.js`,
    `vitrine.js`, `integrasi.css`) nao usa esse sufixo.
    """
    de_fora = {
        str(caminho.relative_to(RAIZ))
        for caminho in (RAIZ / "static").rglob("*")
        if caminho.is_file() and ".min." in caminho.name
    }
    faltando = de_fora - set(documentados())

    assert not faltando, f"biblioteca de fora sem entrada no VENDOR.md: {sorted(faltando)}"
