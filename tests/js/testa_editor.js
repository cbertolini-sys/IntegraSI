'use strict';

// Cenarios que exercitam `normalizarEspacos`, de `static/js/editor.js`, sob node.
// Quem chama e `tests/test_editor_js.py`, que le o JSON impresso aqui e transforma
// cada cenario num teste do pytest - o mesmo arranjo de
// `apps/cursos/tests/js/testa_upload.js` e `tests/js/testa_envio.js`.
//
// Por que uma funcao pura, e nao o editor inteiro sob node: o resto de
// `editor.js` manipula um Quill de verdade, que por sua vez depende de DOM
// completo (Selection, Range, MutationObserver, contentEditable) - simular isso
// sob node custaria muito mais do que vale. A funcao que importa aqui e uma
// string -> string sem nenhuma dependencia de navegador, e fica FORA da guarda
// `if (typeof window.Quill !== 'function') return;`, exatamente para que um
// teste sob node a alcance sem precisar de Quill nenhum.
//
// `globalThis.window = {}` (sem `.Quill`) e o que faz editor.js sair pela guarda
// logo depois de exportar a funcao - sem isto, `typeof window.Quill` estoura
// ReferenceError, porque `window` nao existe em node.
globalThis.window = {};

const path = require('path');
const CAMINHO = path.resolve(__dirname, '../../static/js/editor.js');
const { normalizarEspacos } = require(CAMINHO);

const cenarios = {};

cenarios.troca_todo_nbsp_por_espaco_normal = () => {
  // O bundle vendorizado do Quill faz `.replaceAll(" ", "&nbsp;")` sem condicao
  // nenhuma ao serializar (getSemanticHTML) - nao so em sequencias de espaco.
  // Um paragrafo inteiro de prosa vira uma unica "palavra" ligada por espacos
  // que nao quebram linha.
  const html = '<p>O&nbsp;curso&nbsp;e&nbsp;uma&nbsp;oficina.</p>';
  const resultado = normalizarEspacos(html);
  if (resultado !== '<p>O curso e uma oficina.</p>') {
    throw new Error('nbsp não virou espaço normal: ' + resultado);
  }
};

cenarios.duas_sequencias_de_nbsp_nao_se_confundem = () => {
  // Duas passagens de texto, cada uma com o proprio bloco de nbsp - a troca
  // precisa alcancar as duas, e nao só a primeira.
  const html = '<p>Primeiro&nbsp;paragrafo.</p><p>Segundo&nbsp;paragrafo.</p>';
  const resultado = normalizarEspacos(html);
  if (resultado.includes('&nbsp;')) {
    throw new Error('sobrou nbsp: ' + resultado);
  }
  if ((resultado.match(/paragrafo/g) || []).length !== 2) {
    throw new Error('perdeu texto: ' + resultado);
  }
};

cenarios.html_sem_nbsp_nenhum_sai_igual = () => {
  // A funcao nao pode inventar espaco onde nao havia: um paragrafo curto, sem
  // espaco nenhum entre tags, precisa sair identico.
  const html = '<p><strong>Aviso</strong></p>';
  const resultado = normalizarEspacos(html);
  if (resultado !== html) {
    throw new Error('mudou o que não tinha nbsp: ' + resultado);
  }
};

cenarios.nao_mexe_em_outras_entidades = () => {
  // So o nbsp e trocado. Um `&amp;` (de um "E" comercial que sobreviveu ao
  // sanitizador dentro, por exemplo, de um link) precisa continuar intacto.
  const html = '<p>Antes&nbsp;e&nbsp;depois &amp; outra coisa</p>';
  const resultado = normalizarEspacos(html);
  if (!resultado.includes('&amp;')) {
    throw new Error('mexeu numa entidade que não era nbsp: ' + resultado);
  }
  if (resultado.includes('&nbsp;')) {
    throw new Error('sobrou nbsp: ' + resultado);
  }
};

const resultado = {};
for (const nome of Object.keys(cenarios)) {
  try {
    cenarios[nome]();
    resultado[nome] = { ok: true, erro: null };
  } catch (e) {
    resultado[nome] = { ok: false, erro: e.message };
  }
}
process.stdout.write(JSON.stringify(resultado));
