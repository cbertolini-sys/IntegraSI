# Bibliotecas de terceiros vendorizadas

Estas seis cópias vivem no repositório de propósito: nada é carregado de CDN, e
`tests/test_ajuda.py::test_nenhum_template_carrega_biblioteca_de_fora` reprova
quem tentar. A razão está na spec 13: o sistema precisa funcionar sem depender de
um domínio de terceiro no ar, e uma biblioteca que chega pela rede é uma
biblioteca que alguém pode trocar sem o nosso consentimento.

**O problema que este arquivo resolve** é outro: até 05/09/2026 nenhuma das
versões estava escrita em lugar nenhum. Só o Popper anunciava a sua no cabeçalho.
Para descobrir as outras foi preciso escavar o conteúdo minificado, e a do Tippy
não estava nem lá: ela foi identificada comparando o SHA-256 com o que a origem
publica. **Dependência cuja versão ninguém sabe é dependência que ninguém
atualiza**, e a checagem contra um aviso de segurança fica impossível.

Os hashes abaixo foram conferidos **contra a origem** em 05/09/2026, byte por
byte. Os seis batem.

| Arquivo local | Pacote | Versão | Caminho na origem | Bytes |
| --- | --- | --- | --- | ---: |
| `static/js/htmx.min.js` | `htmx.org` | 2.0.4 | `dist/htmx.min.js` | 50917 |
| `static/js/quill.min.js` | `quill` | 2.0.3 | `dist/quill.js` | 209274 |
| `static/css/quill.snow.css` | `quill` | 2.0.3 | `dist/quill.snow.css` | 24606 |
| `static/js/popper.min.js` | `@popperjs/core` | 2.11.8 | `dist/umd/popper.min.js` | 20122 |
| `static/js/tippy.min.js` | `tippy.js` | 6.3.7 | `dist/tippy-bundle.umd.min.js` | 25717 |
| `static/css/tippy.css` | `tippy.js` | 6.3.7 | `dist/tippy.css` | 1409 |

A origem é o unpkg, no formato `https://unpkg.com/<pacote>@<versão>/<caminho>`.

## SHA-256

`tests/test_vendor.py` lê esta tabela e confere os arquivos em disco. Divergência
silenciosa entre o que se documentou e o que se serve é o defeito que este projeto
persegue em toda parte; aqui ela seria pior, porque um arquivo trocado no disco é
código executando no navegador de quem visita.

| Arquivo | SHA-256 |
| --- | --- |
| `static/js/htmx.min.js` | `e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447` |
| `static/js/quill.min.js` | `f6157c72ac9b3f51cdead426335688a027b12405d9d6a4daadd38a676b2d7ff2` |
| `static/css/quill.snow.css` | `1c7948cd13aa92fac6390319bc1e5e461823da171519d3a768db56164f871636` |
| `static/js/popper.min.js` | `c212f4b505a86352aed62b24a8f16f999f821ecbe6456c7f3c8a04bc87968782` |
| `static/js/tippy.min.js` | `3f0fe70eb26ccf28f6887a192e29d38dd7ef7c2f079a73304ad42ddc7bed37de` |
| `static/css/tippy.css` | `5969f497d9158d7682f8219c6f13fa67269cdf5bf50a3931d95327151dee5678` |

## Dois detalhes que custaram investigação

**`quill.min.js` é o `quill.js` da origem.** O Quill 2.0.3 não publica um
`quill.min.js`: aquele caminho devolve "Not found". O `dist/quill.js` já é o build
distribuído. O nome local está errado e ficou, porque renomeá-lo mexeria em
`base.html`, no `collectstatic` e no cache de quem já visitou, sem ganho nenhum.

**O Popper NÃO é redundante, apesar das aparências.** O `tippy.min.js` é o
`tippy-bundle.umd.min.js`, e "bundle" ali quer dizer que ele embute o CSS padrão,
e não o Popper. O cabeçalho UMD do arquivo entrega o jogo:
`(t=t||self).tippy=e(t.Popper)` - ele recebe o `Popper` global como dependência.

Isso foi testado, e não deduzido: removendo o `popper.min.js` do `base.html`,
`window.tippy` fica `undefined` e nenhuma ajuda de campo funciona. A ordem das
duas tags em `base.html` também importa, e é por isso que o Popper vem primeiro.

## Como atualizar uma delas

1. Baixar da origem: `curl -O https://unpkg.com/<pacote>@<versão>/<caminho>`.
2. Conferir o SHA-256 do que chegou antes de sobrescrever o que está no disco.
3. Trocar o arquivo, e atualizar versão e hash nas duas tabelas acima.
4. Rodar a suíte: `tests/test_vendor.py` reprova se as tabelas e o disco
   divergirem.
5. Abrir uma tela com ajuda de campo e uma com editor, e conferir na tela. A
   suíte não carrega JavaScript nenhum: ela prova que os arquivos são os
   documentados, e não que a biblioteca continua funcionando.
