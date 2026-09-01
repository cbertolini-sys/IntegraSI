'use strict';

// Cenarios que exercitam `static/js/upload.js` sob node, com `fetch`,
// `sessionStorage`, `setTimeout` e formulario de mentira. Quem chama e
// `apps/cursos/tests/test_upload_js.py`, que le o JSON impresso aqui e transforma
// cada cenario num teste do pytest.
//
// Sem isto o unico ponto do sistema com JavaScript proprio ficaria sem prova
// nenhuma: e justo a parte cujo defeito (retomar uma vez so, guardar na sessao um
// identificador que ninguem le) nao aparece em teste de view.

const path = require('path');

const CAMINHO = path.resolve(__dirname, '../../../../static/js/upload.js');

const MARCA = 'MARCA-DO-UUID';
const ROTAS = {
  // De proposito nada parecido com as rotas de verdade: se o JS montasse
  // "/uploads/<id>/bloco/" na mao em vez de ler o `data-url-bloco`, os pedidos
  // deste arquivo nao cairiam em nenhuma destas URLs.
  iniciar: '/rota-de-teste/abrir/',
  bloco: `/rota-de-teste/${MARCA}/bloco/`,
  estado: `/rota-de-teste/${MARCA}/estado/`,
  concluir: `/rota-de-teste/${MARCA}/concluir/`,
};

// `document` existe so para que um JS que buscasse o token CSRF no documento
// inteiro (em vez de dentro do formulario) encontrasse ALGO - e o token errado.
let ouvinteDeSubmit = null;
globalThis.document = {
  querySelector: () => ({ value: 'token-de-outro-formulario' }),
  addEventListener: (tipo, fn) => { if (tipo === 'submit') ouvinteDeSubmit = fn; },
};

const upload = require(CAMINHO);

// --- ambiente de mentira ---------------------------------------------------

const TOKEN = 'token-deste-formulario';

function arquivoFalso(tamanho, nome) {
  return {
    name: nome || 'aula.mp4',
    size: tamanho,
    slice: (inicio, fim) => ({ inicio, fim: Math.min(fim, tamanho) }),
  };
}

function formulario(arquivo, dataset) {
  const nos = {
    'input[type=file]': { files: arquivo ? [arquivo] : [] },
    'input[name=titulo]': { value: 'Aula 1' },
    'input[name=duracao_minutos]': { value: '7' },
    'textarea[name=descricao]': { value: 'Abertura do curso.' },
    '[name=csrfmiddlewaretoken]': { value: TOKEN },
    // A barra e permanente e nasce zerada; so o aviso nasce escondido.
    progress: { value: 0 },
    '.envio-numero': { textContent: '0%' },
    '.aviso': { textContent: '', hidden: true },
  };
  return {
    dataset: Object.assign(
      {
        entregavel: '3',
        tamanhoBloco: '4',
        uuidModelo: MARCA,
        urlIniciar: ROTAS.iniciar,
        urlBloco: ROTAS.bloco,
        urlEstado: ROTAS.estado,
        urlConcluir: ROTAS.concluir,
      },
      dataset || {}
    ),
    querySelector: (seletor) => nos[seletor],
    matches: (seletor) => seletor === '[data-upload-video]',
    nos,
  };
}

const ok = (corpo) => ({ ok: true, status: 200, json: async () => corpo });
const recusa = (status, erro) => ({ ok: false, status, json: async () => ({ erro }) });

function identificadorDe(url) {
  return url.split('/')[2];
}

/** Servidor que se comporta: as quatro rotas da Task 2, contra um estado em
 * memoria. Os cenarios embrulham este responder para injetar queda ou recusa. */
function servidor(est) {
  return async (url, init) => {
    est.chamadas.push(url);
    if (url === est.rotaIniciar) {
      est.uploads[est.proximoId] = 0;
      return ok({ identificador: est.proximoId, recebido: 0 });
    }
    const ident = identificadorDe(url);
    if (!(ident in est.uploads)) return recusa(404, 'Upload não encontrado.');
    if (url.endsWith('/estado/')) {
      return ok({ recebido: est.uploads[ident], total: est.total });
    }
    if (url.endsWith('/bloco/')) {
      const { inicio, fim } = init.body;
      est.blocos.push([inicio, fim]);
      est.uploads[ident] = est.recebidoApos ? est.recebidoApos(fim) : fim;
      return ok({ recebido: est.uploads[ident], total: est.total });
    }
    if (url.endsWith('/concluir/')) {
      est.concluido = JSON.parse(init.body);
      return ok({ anexo: 1, titulo: est.concluido.titulo });
    }
    throw new Error(`rota inesperada: ${url}`);
  };
}

function novoEstado(opcoes) {
  return Object.assign(
    {
      total: 10,
      proximoId: 'ident-novo',
      uploads: {},
      blocos: [],
      chamadas: [],
      concluido: null,
      rotaIniciar: ROTAS.iniciar,
    },
    opcoes || {}
  );
}

function conta(chamadas, sufixo) {
  return chamadas.filter((url) => url.endsWith(sufixo)).length;
}

/** Roda `iniciarUpload` com globais de mentira e devolve o que foi observado. */
async function rodar({ responder, arquivo, memoria, dataset, viaSubmit, alvo }) {
  const registro = { esperas: [], recargas: 0, progresso: [], pedidos: [], barrou: false };
  const guardado = new Map(Object.entries(memoria || {}));

  const originais = {
    fetch: globalThis.fetch,
    setTimeout: globalThis.setTimeout,
    window: globalThis.window,
    sessionStorage: globalThis.sessionStorage,
  };

  globalThis.sessionStorage = {
    getItem: (chave) => (guardado.has(chave) ? guardado.get(chave) : null),
    setItem: (chave, valor) => guardado.set(chave, valor),
    removeItem: (chave) => guardado.delete(chave),
  };
  globalThis.window = { location: { reload: () => { registro.recargas += 1; } } };
  // Espera de mentira: anota quanto o JS PEDIU para esperar e segue na hora.
  globalThis.setTimeout = (fn, ms) => { registro.esperas.push(ms); fn(); return 0; };
  globalThis.fetch = async (url, init) => {
    registro.pedidos.push({ url, init: init || {} });
    return responder(url, init || {});
  };

  const form = formulario(arquivo === undefined ? arquivoFalso(10) : arquivo, dataset);
  const barra = form.nos.progress;
  const original = Object.getOwnPropertyDescriptor(barra, 'value');
  Object.defineProperty(barra, 'value', {
    get: () => original.value,
    set: (v) => { original.value = v; registro.progresso.push(v); },
  });

  try {
    if (viaSubmit) {
      // Caminho de verdade do navegador: o ouvinte de `submit` do documento.
      // Sem ele o formulario faria um POST comum para a propria pagina e NADA
      // do resto do arquivo rodaria - com a suite inteira verde.
      const evento = {
        target: alvo || form,
        preventDefault: () => { registro.barrou = true; },
      };
      ouvinteDeSubmit(evento);
      // O ouvinte nao espera a promessa; drena as microtarefas ate o fim.
      for (let i = 0; i < 500; i += 1) await Promise.resolve();
    } else {
      await upload.iniciarUpload(form);
    }
  } finally {
    Object.assign(globalThis, originais);
  }

  return Object.assign(registro, {
    aviso: form.nos['.aviso'].textContent,
    guardado,
    form,
  });
}

// --- cenarios --------------------------------------------------------------

const cenarios = {};
const cenario = (nome, corpo) => { cenarios[nome] = corpo; };

function afirma(condicao, mensagem) {
  if (!condicao) throw new Error(mensagem);
}

function afirmaIgual(obtido, esperado, mensagem) {
  const a = JSON.stringify(obtido);
  const b = JSON.stringify(esperado);
  if (a !== b) throw new Error(`${mensagem}: esperado ${b}, obtido ${a}`);
}

const CAIU = () => { throw new TypeError('Failed to fetch'); };

/** Embrulha o responder para derrubar a conexao em pedidos escolhidos. */
function comQueda(responder, { antesDe = () => false, depoisDe = () => false } = {}) {
  const contagem = {};
  return async (url, init) => {
    const rota = url.split('/').filter(Boolean).pop();
    contagem[rota] = (contagem[rota] || 0) + 1;
    if (antesDe(rota, contagem[rota])) CAIU();
    const resposta = await responder(url, init);
    if (depoisDe(rota, contagem[rota])) CAIU();
    return resposta;
  };
}

// Regra: o arquivo e fatiado no tamanho que o formulario informa, e nao num
// numero escrito de novo dentro do JS.
cenario('fatia_no_tamanho_que_o_formulario_manda', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est) });
  afirmaIgual(est.blocos, [[0, 4], [4, 8], [8, 10]], 'blocos enviados');
  afirma(est.concluido !== null, 'o upload precisava terminar em conclusão');
});

// Regra: o mesmo, com outro tamanho - o valor vem do dado, nao de uma constante.
cenario('outro_tamanho_de_bloco_muda_o_fatiamento', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est), dataset: { tamanhoBloco: '3' } });
  afirmaIgual(est.blocos, [[0, 3], [3, 6], [6, 9], [9, 10]], 'blocos enviados');
});

// Regra: todo POST leva o X-CSRFToken deste formulario. As quatro rotas tem CSRF
// ligado; sem o cabecalho o Django devolve 403 e o upload nao sai do lugar.
cenario('manda_o_csrf_deste_formulario_em_todo_post', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est) });
  const posts = r.pedidos.filter((p) => p.init.method === 'POST');
  afirma(posts.length === 5, `esperava 5 POSTs (abrir, 3 blocos, concluir), houve ${posts.length}`);
  for (const p of posts) {
    afirmaIgual(p.init.headers['X-CSRFToken'], TOKEN, `token em ${p.url}`);
  }
});

// Regra: as URLs saem do formulario, com a marca trocada pelo identificador.
cenario('usa_as_urls_que_o_formulario_entrega', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est) });
  for (const p of r.pedidos) {
    afirma(p.url.startsWith('/rota-de-teste/'), `URL fora do formulário: ${p.url}`);
    afirma(!p.url.includes(MARCA), `marca do UUID não substituída: ${p.url}`);
  }
});

// Regra: uma queda de conexao no meio nao perde o upload.
cenario('uma_queda_no_meio_nao_perde_o_upload', async () => {
  const est = novoEstado();
  const responder = comQueda(servidor(est), {
    antesDe: (rota, n) => rota === 'bloco' && n === 2,
  });
  const r = await rodar({ responder });
  afirma(est.concluido !== null, `o upload não terminou; aviso: ${r.aviso}`);
  afirmaIgual(est.uploads['ident-novo'], 10, 'bytes no servidor');
});

// Regra: DUAS quedas tambem nao. E o ponto inteiro da tarefa - meia hora de
// transferencia domestica cabe mais de uma queda, e um try/catch unico salva a
// primeira e entrega a segunda de bandeja.
cenario('duas_quedas_no_meio_nao_perdem_o_upload', async () => {
  const est = novoEstado();
  const responder = comQueda(servidor(est), {
    antesDe: (rota, n) => rota === 'bloco' && (n === 2 || n === 4),
  });
  const r = await rodar({ responder });
  afirma(est.concluido !== null, `o upload não terminou; aviso: ${r.aviso}`);
  afirmaIgual(est.uploads['ident-novo'], 10, 'bytes no servidor');
});

// Regra: cada tentativa pergunta ao servidor onde parou. O bloco cuja RESPOSTA se
// perdeu chegou inteiro: retomar pelo deslocamento local reenviaria bytes que ja
// estao la, e a conta de quem manda no arquivo e do servidor.
cenario('pergunta_ao_servidor_onde_parou_a_cada_tentativa', async () => {
  const est = novoEstado();
  // A queda acontece DEPOIS de o servidor gravar o bloco: ele esta em 8, o
  // cliente acha que esta em 4.
  const responder = comQueda(servidor(est), {
    depoisDe: (rota, n) => rota === 'bloco' && (n === 2 || n === 3),
  });
  const r = await rodar({ responder });
  afirmaIgual(conta(est.chamadas, '/estado/'), 2, 'consultas de estado');
  afirmaIgual(est.blocos, [[0, 4], [4, 8], [8, 10]], 'nenhum bloco reenviado');
  afirma(est.concluido !== null, `o upload não terminou; aviso: ${r.aviso}`);
});

// Regra: a espera entre tentativas cresce, e cresce no ponto onde e usada.
cenario('espera_mais_a_cada_tentativa', async () => {
  const est = novoEstado();
  const responder = comQueda(servidor(est), {
    antesDe: (rota, n) => rota === 'bloco' && n <= 3,
  });
  const r = await rodar({ responder });
  afirma(r.esperas.length >= 3, `esperava ao menos 3 esperas, houve ${r.esperas.length}`);
  afirmaIgual(r.esperas[0], upload.ESPERA_BASE_MS, 'primeira espera');
  for (let i = 1; i < r.esperas.length; i += 1) {
    afirma(
      r.esperas[i] > r.esperas[i - 1],
      `espera ${i} (${r.esperas[i]}ms) não cresceu sobre ${r.esperas[i - 1]}ms`
    );
  }
});

// Regra: o numero de tentativas e limitado. Sem limite, uma queda definitiva vira
// um laco martelando o servidor para sempre.
cenario('desiste_depois_do_limite_de_tentativas', async () => {
  const est = novoEstado();
  const responder = comQueda(servidor(est), { antesDe: (rota) => rota === 'bloco' });
  const r = await rodar({ responder });
  afirmaIgual(r.esperas.length, upload.TENTATIVAS_MAXIMAS - 1, 'esperas antes de desistir');
  afirmaIgual(conta(est.chamadas, '/estado/'), upload.TENTATIVAS_MAXIMAS - 1, 'consultas de estado');
  afirma(est.concluido === null, 'não podia concluir');
  afirma(r.aviso.includes('tentativas'), `aviso pouco explicativo: ${r.aviso}`);
});

// Regra: recusa do servidor (4xx) e definitiva - repetir so gasta a paciencia de
// quem espera, porque o servidor entendeu o pedido e disse nao.
cenario('recusa_do_servidor_nao_e_retentada', async () => {
  const est = novoEstado();
  const base = servidor(est);
  const responder = async (url, init) => {
    if (url.endsWith('/bloco/')) return recusa(400, 'Bloco ultrapassa o tamanho declarado.');
    return base(url, init);
  };
  const r = await rodar({ responder });
  afirmaIgual(r.esperas, [], 'não podia esperar para tentar de novo');
  afirmaIgual(conta(est.chamadas, '/estado/'), 0, 'não podia perguntar o estado');
  afirmaIgual(r.aviso, 'Bloco ultrapassa o tamanho declarado.', 'aviso');
});

// Regra: o identificador guardado na sessao e LIDO de volta. Recarregar a pagina
// no meio do envio nao pode orfanar os bytes que ja subiram.
cenario('retoma_o_upload_guardado_depois_de_recarregar_a_pagina', async () => {
  const est = novoEstado({ uploads: { 'ident-antigo': 8 } });
  const r = await rodar({
    responder: servidor(est),
    memoria: { 'upload:3:aula.mp4:10': 'ident-antigo' },
  });
  afirmaIgual(conta(est.chamadas, '/abrir/'), 0, 'não podia abrir um upload novo');
  afirmaIgual(est.blocos, [[8, 10]], 'só faltavam os últimos 2 bytes');
  afirma(est.concluido !== null, `o upload não terminou; aviso: ${r.aviso}`);
});

// Regra: identificador guardado que o servidor nao conhece mais (404) e
// descartado, e um upload novo e aberto no lugar.
cenario('identificador_guardado_que_o_servidor_esqueceu_e_descartado', async () => {
  const est = novoEstado();
  const r = await rodar({
    responder: servidor(est),
    memoria: { 'upload:3:aula.mp4:10': 'ident-que-sumiu' },
  });
  afirmaIgual(conta(est.chamadas, '/abrir/'), 1, 'precisava abrir um upload novo');
  afirmaIgual(est.blocos, [[0, 4], [4, 8], [8, 10]], 'blocos enviados do zero');
  afirma(est.concluido !== null, `o upload não terminou; aviso: ${r.aviso}`);
});

// Regra: guardado que e de OUTRO arquivo (mesmo nome, tamanho diferente no
// servidor) tambem e descartado - a chave leva o tamanho, mas a memoria pode ter
// sobrado de um arquivo trocado.
cenario('guardado_de_arquivo_de_outro_tamanho_e_descartado', async () => {
  const est = novoEstado({ uploads: { 'ident-de-outro': 4 }, total: 99 });
  const r = await rodar({
    responder: servidor(est),
    memoria: { 'upload:3:aula.mp4:10': 'ident-de-outro' },
  });
  afirmaIgual(conta(est.chamadas, '/abrir/'), 1, 'precisava abrir um upload novo');
  const paraOAlheio = est.chamadas.filter((url) => url.includes('ident-de-outro'));
  afirmaIgual(paraOAlheio, [ROTAS.estado.replace(MARCA, 'ident-de-outro')],
    'só podia perguntar o estado do guardado, e nada mais');
  afirmaIgual(est.uploads['ident-de-outro'], 4, 'o upload alheio não podia receber bytes');
});

// Regra: queda de REDE ao conferir o guardado nao descarta nada. Nao ha resposta
// do servidor; abrir outro upload jogaria fora meia hora de bytes bons.
cenario('queda_de_rede_ao_conferir_o_guardado_nao_descarta_o_que_ja_subiu', async () => {
  const est = novoEstado({ uploads: { 'ident-antigo': 8 } });
  const responder = comQueda(servidor(est), { antesDe: (rota) => rota === 'estado' });
  const r = await rodar({
    responder,
    memoria: { 'upload:3:aula.mp4:10': 'ident-antigo' },
  });
  afirmaIgual(conta(est.chamadas, '/abrir/'), 0, 'não podia abrir um upload novo');
  afirmaIgual(r.guardado.get('upload:3:aula.mp4:10'), 'ident-antigo', 'chave preservada');
  afirma(r.aviso !== '', 'precisava avisar quem espera');
});

// Regra: a chave sai da memoria quando o video entra de verdade.
cenario('chave_some_da_memoria_quando_o_video_entra', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est) });
  afirmaIgual(r.guardado.size, 0, 'memória depois do sucesso');
});

// Regra: a tela recarrega no fim - e o que faz o anexo novo aparecer na lista de
// materiais. Cenario separado do anterior de proposito: dois assertos numa mesma
// funcao seriam duas guardas presas por um teste so, e nenhuma das duas estaria
// presa sozinha.
cenario('recarrega_a_tela_quando_o_video_entra', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est) });
  afirmaIgual(r.recargas, 1, 'a tela precisa recarregar para mostrar o anexo novo');
});

// Regra: sem arquivo escolhido, nada e enviado.
cenario('sem_arquivo_nao_fala_com_o_servidor', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est), arquivo: null });
  afirmaIgual(r.pedidos.length, 0, 'pedidos ao servidor');
  afirmaIgual(r.aviso, 'Escolha o arquivo de vídeo.', 'aviso');
});

// Regra: o deslocamento do proximo bloco vem do `recebido` do servidor, e nao de
// uma soma local - o servidor pode ter gravado mais do que o cliente contou.
cenario('o_deslocamento_do_proximo_bloco_vem_do_servidor', async () => {
  const est = novoEstado({ recebidoApos: (fim) => (fim === 4 ? 6 : fim) });
  const r = await rodar({ responder: servidor(est) });
  afirmaIgual(est.blocos, [[0, 4], [6, 10]], 'blocos enviados');
  afirma(est.concluido !== null, `o upload não terminou; aviso: ${r.aviso}`);
});

// Regra: a barra de progresso acompanha o envio.
cenario('a_barra_de_progresso_acompanha_o_envio', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est) });
  afirmaIgual(r.progresso[r.progresso.length - 1], 100, 'progresso final');
  afirma(r.progresso.filter((v) => v > 0 && v < 100).length > 0, 'nenhum progresso intermediário');
});

// Regra: servidor que aceita o bloco sem avancar nao pode virar laco infinito.
cenario('servidor_que_nao_avanca_nao_vira_laco_infinito', async () => {
  const est = novoEstado({ recebidoApos: () => 0 });
  const r = await rodar({ responder: servidor(est) });
  afirma(est.blocos.length <= 2, `mandou ${est.blocos.length} blocos sem sair do lugar`);
  afirma(est.concluido === null, 'não podia concluir');
});

// Regra: a conclusao leva titulo e duracao do formulario.
cenario('conclui_com_titulo_e_duracao_do_formulario', async () => {
  const est = novoEstado();
  await rodar({ responder: servidor(est) });
  afirmaIgual(
    est.concluido,
    { titulo: 'Aula 1', duracao_minutos: '7', descricao: 'Abertura do curso.' },
    'corpo da conclusão'
  );
});

// Regra: o numero ao lado da barra acompanha o envio e fecha em 100%. Barra sem
// porcentagem nao diz quanto falta de um arquivo de um giga.
cenario('o_numero_acompanha_a_barra_e_fecha_em_cem', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est) });
  afirmaIgual(r.form.nos['.envio-numero'].textContent, '100%', 'número final');
  afirmaIgual(r.form.nos.progress.value, 100, 'barra final');
});

// Regra: o aviso nasce escondido e aparece quando ha o que dizer - inclusive sem
// arquivo escolhido, que e o unico caso em que ele fala sem haver envio nenhum.
cenario('o_aviso_aparece_quando_ha_o_que_dizer', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est), arquivo: null });
  afirmaIgual(r.form.nos['.aviso'].hidden, false, 'o pedido do arquivo precisa aparecer');
  afirmaIgual(r.aviso, 'Escolha o arquivo de vídeo.', 'aviso');
  // E a barra nao se mexe: nao houve envio nenhum.
  afirmaIgual(r.form.nos.progress.value, 0, 'a barra andou sem haver envio');
});

// Regra: o `submit` do formulario de video e interceptado pelo ouvinte do
// documento, que impede o POST comum e chama o envio em blocos.
cenario('o_submit_do_formulario_de_video_e_interceptado', async () => {
  const est = novoEstado();
  const r = await rodar({ responder: servidor(est), viaSubmit: true });
  afirma(r.barrou, 'o POST comum do formulário precisava ser impedido');
  afirma(est.concluido !== null, 'o envio em blocos precisava rodar pelo submit');
});

// Regra: o ouvinte e do documento inteiro, entao precisa deixar passar o submit
// dos OUTROS formularios da tela (anexar, enviar para revisao).
cenario('submit_de_outro_formulario_nao_e_interceptado', async () => {
  const est = novoEstado();
  const r = await rodar({
    responder: servidor(est),
    viaSubmit: true,
    alvo: { matches: () => false },
  });
  afirma(!r.barrou, 'não podia impedir o submit de outro formulário');
  afirmaIgual(r.pedidos.length, 0, 'não podia falar com o servidor');
});

// --- execucao --------------------------------------------------------------

async function principal() {
  const resultado = {};
  for (const [nome, corpo] of Object.entries(cenarios)) {
    try {
      await corpo();
      resultado[nome] = { ok: true, erro: null };
    } catch (erro) {
      resultado[nome] = { ok: false, erro: `${erro && erro.message ? erro.message : erro}` };
    }
  }
  process.stdout.write(JSON.stringify(resultado));
}

principal().catch((erro) => {
  process.stdout.write(JSON.stringify({ __harness__: { ok: false, erro: String(erro) } }));
  process.exitCode = 1;
});
