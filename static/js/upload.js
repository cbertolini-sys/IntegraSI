// Upload de vídeo em blocos, retomável. HTMX não fatia arquivo: é o único ponto
// do sistema que precisa de JavaScript próprio (spec §8).
//
// Um GB no upstream doméstico de um aluno leva perto de meia hora. Nessa janela
// uma queda de conexão não é exótica - e a segunda queda é tão provável quanto a
// primeira. Por isso a retomada é um laço com um número limitado de tentativas e
// espera crescente, e não um try/catch que salva o upload uma vez só.
//
// Duas coisas este arquivo deliberadamente NÃO sabe: as URLs das rotas e o
// tamanho do bloco. As duas chegam pelo `data-*` do formulário, que as lê do
// `urls.py` e do `apps/cursos/arquivos.py`. Uma cópia aqui divergiria da outra em
// silêncio e só apareceria no navegador de um aluno, com a suíte inteira verde.
//
// O que o navegador exercita e nenhum teste alcança está listado no relatório da
// Task 3; o que dá para provar sem navegador está em `apps/cursos/tests/js/`.

const TENTATIVAS_MAXIMAS = 5;
const ESPERA_BASE_MS = 1000;

const dormir = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Resposta que o servidor recusou. Um 4xx é definitivo: o servidor entendeu o
 * pedido e disse não, então repetir só gasta a paciência de quem espera. Um 5xx
 * (ou um proxy no meio do caminho) pode ser passageiro e vale nova tentativa. */
class ErroDoServidor extends Error {
  constructor(mensagem, status) {
    super(mensagem);
    this.status = status;
    this.definitivo = status >= 400 && status < 500;
  }
}

async function mensagemDeErro(resposta) {
  const corpo = await resposta.json().catch(() => ({}));
  return corpo.erro || 'Falha na comunicação com o servidor.';
}

async function postar(url, corpo, tipo, csrf) {
  // O CSRF fica ligado nas quatro rotas (nenhuma é `csrf_exempt`), então todo
  // POST daqui precisa carregar o cabeçalho - sem ele o Django devolve 403.
  const resposta = await fetch(url, {
    method: 'POST',
    headers: { 'X-CSRFToken': csrf, 'Content-Type': tipo },
    body: corpo,
  });
  if (!resposta.ok) {
    throw new ErroDoServidor(await mensagemDeErro(resposta), resposta.status);
  }
  return resposta.json();
}

async function consultarEstado(url) {
  const resposta = await fetch(url);
  if (!resposta.ok) {
    throw new ErroDoServidor(await mensagemDeErro(resposta), resposta.status);
  }
  return resposta.json();
}

/** Onde guardamos qual upload já está aberto para este arquivo. Fica em
 * `sessionStorage` e é LIDO de volta: sem a leitura, recarregar a página órfã o
 * identificador junto com os bytes que já subiram, e a retomada só sobreviveria
 * enquanto a aba continuasse viva - que é justo o cenário em que ela menos
 * importa. Pode não existir (aba anônima, armazenamento bloqueado); nesse caso o
 * upload funciona igual, só não sobrevive a um recarregamento. */
function memoria() {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage;
  } catch (erro) {
    return null;
  }
}

function lembrar(chave, valor) {
  try {
    if (memoria()) memoria().setItem(chave, valor);
  } catch (erro) {
    /* cota cheia: seguir sem memória é melhor que abortar o envio */
  }
}

function lembrado(chave) {
  try {
    return memoria() ? memoria().getItem(chave) : null;
  } catch (erro) {
    return null;
  }
}

function esquecer(chave) {
  try {
    if (memoria()) memoria().removeItem(chave);
  } catch (erro) {
    /* idem */
  }
}

/** As três rotas que dependem do identificador, com a marca trocada pelo real. */
function rotas(form, identificador) {
  const real = (modelo) => modelo.split(form.dataset.uuidModelo).join(identificador);
  return {
    bloco: real(form.dataset.urlBloco),
    estado: real(form.dataset.urlEstado),
    concluir: real(form.dataset.urlConcluir),
  };
}

async function enviarBlocos(arquivo, url, deslocamentoInicial, tamanhoBloco, csrf, aoProgredir) {
  let deslocamento = deslocamentoInicial;
  while (deslocamento < arquivo.size) {
    const bloco = arquivo.slice(deslocamento, deslocamento + tamanhoBloco);
    const resultado = await postar(url, bloco, 'application/octet-stream', csrf);
    // Quem diz onde o arquivo está é o servidor, não um contador local: um bloco
    // pode ter chegado inteiro mesmo com a resposta perdida no caminho.
    if (!(resultado.recebido > deslocamento)) {
      // Servidor que não avança transformaria o `while` num laço infinito
      // martelando a rota para sempre.
      throw new ErroDoServidor('O servidor não registrou o avanço do envio.', 400);
    }
    deslocamento = resultado.recebido;
    aoProgredir(deslocamento / arquivo.size);
  }
  return deslocamento;
}

/** Envia o arquivo inteiro, atravessando quedas de conexão.
 *
 * Cada nova tentativa espera mais que a anterior e pergunta ao servidor onde o
 * arquivo parou, em vez de confiar no deslocamento que o cliente tinha quando
 * caiu. Perguntar faz parte de toda tentativa, e não de uma só: a segunda queda
 * de uma transferência de meia hora é tão provável quanto a primeira. */
async function enviarComRetomada(arquivo, urls, inicio, tamanhoBloco, csrf, aoProgredir, aoAvisar) {
  let deslocamento = inicio;
  let ultimoErro = null;
  for (let tentativa = 0; tentativa < TENTATIVAS_MAXIMAS; tentativa += 1) {
    try {
      if (tentativa > 0) {
        await dormir(ESPERA_BASE_MS * 2 ** (tentativa - 1));
        deslocamento = (await consultarEstado(urls.estado)).recebido;
        aoProgredir(deslocamento / arquivo.size);
        aoAvisar(
          `Conexão instável. Retomando de ${Math.round((100 * deslocamento) / arquivo.size)}%…`
          + ` (tentativa ${tentativa + 1} de ${TENTATIVAS_MAXIMAS})`
        );
      }
      return await enviarBlocos(arquivo, urls.bloco, deslocamento, tamanhoBloco, csrf, aoProgredir);
    } catch (erro) {
      if (erro.definitivo) throw erro;
      ultimoErro = erro;
    }
  }
  throw new Error(
    `Não foi possível enviar o vídeo após ${TENTATIVAS_MAXIMAS} tentativas.`
    + ' O que já subiu continua no servidor: escolha o mesmo arquivo de novo para'
    + ` retomar. (${ultimoErro ? ultimoErro.message : 'sem detalhes'})`
  );
}

/** Retoma o upload que já estava aberto para este arquivo, ou abre um novo. */
async function abrirOuRetomar(form, arquivo, chave, csrf) {
  const guardado = lembrado(chave);
  if (guardado) {
    try {
      const estado = await consultarEstado(rotas(form, guardado).estado);
      // O tamanho é a única prova barata de que o registro guardado é deste
      // arquivo: a chave leva nome e tamanho, mas a memória pode ter sobrado de
      // um arquivo trocado com o mesmo nome.
      if (estado.total === arquivo.size) {
        return { identificador: guardado, recebido: estado.recebido };
      }
    } catch (erro) {
      // Só descarta o que já subiu quando o servidor DIZ que não conhece mais o
      // upload (404). Uma falha de rede aqui não é resposta nenhuma: abrir outro
      // upload jogaria fora meia hora de bytes bons.
      if (!erro.definitivo) throw erro;
    }
    esquecer(chave);
  }
  const aberto = await postar(
    form.dataset.urlIniciar,
    JSON.stringify({
      entregavel: form.dataset.entregavel,
      nome: arquivo.name,
      tamanho: arquivo.size,
    }),
    'application/json',
    csrf
  );
  lembrar(chave, aberto.identificador);
  return { identificador: aberto.identificador, recebido: aberto.recebido || 0 };
}

function recarregar() {
  if (typeof window !== 'undefined' && window.location) window.location.reload();
}

async function iniciarUpload(form) {
  const arquivo = form.querySelector('input[type=file]').files[0];
  const barra = form.querySelector('progress');
  const aviso = form.querySelector('.aviso');
  const aoAvisar = (texto) => { aviso.textContent = texto; };
  const aoProgredir = (fracao) => { barra.value = Math.round(fracao * 100); };

  if (!arquivo) {
    aoAvisar('Escolha o arquivo de vídeo.');
    return;
  }

  // O token vem de dentro DESTE formulário. Pegar o primeiro do documento
  // funcionaria por acidente hoje e passaria a mandar o token de outro
  // formulário no dia em que a tela ganhasse mais um acima deste.
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  const tamanhoBloco = Number(form.dataset.tamanhoBloco);
  const chave = `upload:${form.dataset.entregavel}:${arquivo.name}:${arquivo.size}`;

  try {
    aoAvisar('Enviando…');
    const { identificador, recebido } = await abrirOuRetomar(form, arquivo, chave, csrf);
    const urls = rotas(form, identificador);
    aoProgredir(recebido / arquivo.size);
    await enviarComRetomada(
      arquivo, urls, recebido, tamanhoBloco, csrf, aoProgredir, aoAvisar
    );

    aoAvisar('Concluindo…');
    // A conclusão não entra no laço de retomada de propósito: se ela cair, os
    // bytes continuam no servidor e a chave continua na memória - escolher o
    // mesmo arquivo de novo retoma, não acha bloco nenhum faltando e conclui.
    await postar(
      urls.concluir,
      JSON.stringify({
        titulo: form.querySelector('input[name=titulo]').value,
        duracao_minutos: form.querySelector('input[name=duracao_minutos]').value,
      }),
      'application/json',
      csrf
    );
    esquecer(chave);
    aoAvisar('Vídeo enviado.');
    recarregar();
  } catch (erro) {
    aoAvisar(erro.message);
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('submit', (evento) => {
    if (evento.target.matches('[data-upload-video]')) {
      evento.preventDefault();
      iniciarUpload(evento.target);
    }
  });
}

// Só para os testes sob node (`apps/cursos/tests/js/`). No navegador `module` não
// existe e esta linha não faz nada.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { iniciarUpload, TENTATIVAS_MAXIMAS, ESPERA_BASE_MS };
}
