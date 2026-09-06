'use strict';

// Cenarios que exercitam `static/js/envio.js` sob node, com documento, janela e
// formularios de mentira. Quem chama e `tests/test_envio_js.py`, que le o JSON
// impresso aqui e transforma cada cenario num teste do pytest - o mesmo arranjo
// de `apps/cursos/tests/js/testa_upload.js`.
//
// O que se prova aqui nao tem como ser provado por teste de view: o segundo
// clique e barrado no navegador, e o servidor nunca chega a ver os dois pedidos.

const path = require('path');
const CAMINHO = path.resolve(__dirname, '../../static/js/envio.js');

// --- documento e janela de mentira ------------------------------------------

const ouvintes = { documento: {}, janela: {} };

// O `pageshow` do envio.js varre o documento atras dos formularios marcados, em
// vez de receber um. Sem este registro, o cenario do historico passaria por um
// caminho que o navegador nao usa.
const criados = [];

globalThis.document = {
  addEventListener: (tipo, fn, captura) => {
    (ouvintes.documento[tipo] = ouvintes.documento[tipo] || [])
      .push({ fn: fn, captura: captura === true });
  },
  querySelectorAll: (seletor) => {
    const marca = seletor.replace(/[[\]]/g, '');
    return criados.filter((f) => f.hasAttribute(marca));
  },
};
globalThis.window = {
  addEventListener: (tipo, fn, captura) => {
    (ouvintes.janela[tipo] = ouvintes.janela[tipo] || [])
      .push({ fn: fn, captura: captura === true });
  },
};

require(CAMINHO);

function disparar(onde, tipo, evento) {
  (ouvintes[onde][tipo] || []).forEach((o) => o.fn(evento));
}

function fase(onde, tipo) {
  const o = (ouvintes[onde][tipo] || [])[0];
  return o ? (o.captura ? 'captura' : 'bolha') : null;
}

// --- formulario de mentira --------------------------------------------------

function botao(valor) {
  const atributos = {};
  const classes = new Set();
  return {
    valor,
    classes,
    // `disabled` e propriedade, e nao atributo: e assim que o navegador decide
    // se o par nome/valor do botao entra no corpo do POST, e e o que o cenario
    // do `disabled` mede.
    disabled: false,
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c) },
    setAttribute(k, v) { atributos[k] = v; },
    removeAttribute(k) { delete atributos[k]; },
    getAttribute(k) { return k in atributos ? atributos[k] : null; },
  };
}

function comBotoes(valores, marcas) {
  const botoes = valores.map(botao);
  const atributos = Object.assign({}, marcas);
  const form = {
    botoes,
    hasAttribute: (k) => k in atributos,
    setAttribute(k, v) { atributos[k] = v; },
    removeAttribute(k) { delete atributos[k]; },
    // `matches('[data-upload-video]')` -> procura a marca entre os atributos.
    matches: (seletor) => seletor.replace(/[[\]]/g, '') in atributos,
    querySelector: () => botoes[0] || null,
    querySelectorAll: () => botoes,
  };
  botoes.forEach((b) => { b.form = form; });
  criados.push(form);
  return form;
}

function envio(form, submitter) {
  const visto = { barrado: false, cortado: false };
  disparar('documento', 'submit', {
    target: form,
    submitter: submitter || null,
    preventDefault: () => { visto.barrado = true; },
    stopPropagation: () => { visto.cortado = true; },
  });
  ultimoEnvio = visto;
  return visto.barrado;
}

let ultimoEnvio = null;

// --- cenarios ---------------------------------------------------------------

const cenarios = {};

cenarios.o_primeiro_envio_passa = () => {
  const f = comBotoes(['APROVAR']);
  if (envio(f, f.botoes[0])) throw new Error('o primeiro envio foi barrado');
};

cenarios.o_segundo_envio_e_barrado = () => {
  const f = comBotoes(['APROVAR']);
  envio(f, f.botoes[0]);
  if (!envio(f, f.botoes[0])) {
    throw new Error('o segundo envio passou: o clique duplo chega ao servidor');
  }
};

cenarios.o_botao_apertado_nunca_recebe_disabled = () => {
  // A REGRA QUE MAIS IMPORTA. O corpo do POST e montado DEPOIS do evento
  // `submit`, e botao desabilitado nao entra nele. Com `disabled`, o
  // `acao=EXCLUIR` de `pessoas.html` (quatro botoes no mesmo formulario)
  // sumiria e a view nao saberia o que foi pedido.
  const f = comBotoes(['EXCLUIR']);
  envio(f, f.botoes[0]);
  if (f.botoes[0].disabled) {
    throw new Error('o botão foi desabilitado e o `name=value` dele sai do POST');
  }
};

cenarios.o_botao_apertado_e_marcado_para_a_tecnologia_assistiva = () => {
  const f = comBotoes(['APROVAR']);
  envio(f, f.botoes[0]);
  if (f.botoes[0].getAttribute('aria-disabled') !== 'true') {
    throw new Error('o botão não avisa que está ocupado');
  }
};

cenarios.de_quatro_botoes_o_marcado_e_o_que_foi_apertado = () => {
  const f = comBotoes(['REBAIXAR', 'PROMOVER', 'EXCLUIR', 'REATIVAR']);
  envio(f, f.botoes[2]);
  const marcados = f.botoes.filter((b) => b.getAttribute('aria-disabled'));
  if (marcados.length !== 1 || marcados[0].valor !== 'EXCLUIR') {
    throw new Error(
      'marcou ' + marcados.map((b) => b.valor).join(',') + ' em vez de EXCLUIR'
    );
  }
};

cenarios.validacao_do_navegador_libera_o_formulario = () => {
  // Sem isto o formulario trava para sempre: a validacao do lado do cliente
  // barra o envio SEM disparar outro `submit`, entao nada desfaria a marca e a
  // pessoa nao conseguiria enviar depois de corrigir o campo.
  const f = comBotoes(['SALVAR']);
  envio(f, f.botoes[0]);
  disparar('documento', 'invalid', { target: { form: f } });
  if (envio(f, f.botoes[0])) {
    throw new Error('depois de corrigir o campo, o formulário continua travado');
  }
};

cenarios.voltar_pelo_historico_libera_o_formulario = () => {
  // A pagina restaurada do cache do navegador volta com o DOM como estava,
  // marca inclusive. Sem isto, voltar e reenviar seria impossivel.
  const f = comBotoes(['SALVAR']);
  envio(f, f.botoes[0]);
  disparar('janela', 'pageshow', { persisted: true });
  if (envio(f, f.botoes[0])) {
    throw new Error('voltando pelo histórico, o formulário continua travado');
  }
};

cenarios.resposta_do_htmx_libera_o_formulario = () => {
  // O unico formulario HTMX do sistema (`_secao.html`) e substituido pela
  // resposta no caminho feliz, mas nao quando o pedido falha. Sem isto, salvar
  // uma secao com o servidor fora do ar travaria a secao ate recarregar.
  const f = comBotoes(['Salvar seção']);
  envio(f, f.botoes[0]);
  disparar('documento', 'htmx:afterRequest', { target: f });
  if (envio(f, f.botoes[0])) {
    throw new Error('depois da resposta do HTMX, o formulário continua travado');
  }
};

cenarios.o_upload_de_video_nao_e_bloqueado = () => {
  // `upload.js` intercepta este formulario, tem barra de progresso propria e um
  // caminho de erro que pede nova tentativa. Bloquear aqui impediria a pessoa
  // de tentar de novo depois de um upload que falhou.
  const f = comBotoes(['Enviar'], { 'data-upload-video': '' });
  envio(f, f.botoes[0]);
  if (envio(f, f.botoes[0])) {
    throw new Error('o formulário de upload foi bloqueado; upload.js cuida dele');
  }
};

cenarios.o_ouvinte_de_submit_e_preso_na_fase_de_captura = () => {
  // Em bolha, todo manipulador preso ao proprio formulario roda ANTES deste -
  // inclusive o do HTMX, que ja teria disparado o pedido quando a marca fosse
  // conferida. O segundo clique chegaria ao servidor exatamente no unico
  // formulario que faz pedido sem recarregar a pagina.
  const onde = fase('documento', 'submit');
  if (onde !== 'captura') {
    throw new Error('o `submit` é ouvido em ' + onde + ', e o HTMX corre na frente');
  }
};

cenarios.o_envio_barrado_tambem_corta_a_propagacao = () => {
  // `preventDefault` sozinho cancela so a acao padrao do navegador: os outros
  // ouvintes rodam do mesmo jeito, e o do HTMX nao pergunta se o evento foi
  // cancelado antes de mandar o pedido.
  const f = comBotoes(['Salvar seção']);
  envio(f, f.botoes[0]);
  envio(f, f.botoes[0]);
  if (!ultimoEnvio.cortado) {
    throw new Error('a propagação segue e o HTMX manda o pedido assim mesmo');
  }
};

// --- execucao ---------------------------------------------------------------

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
