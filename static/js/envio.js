// Um envio por clique.
//
// Trinta e cinco botoes de envio no sistema, e um unico com indicador de
// progresso (o de salvar secao). Nas acoes lentas - submeter a coordenacao, que
// enfileira notificacao; publicar; concluir o envio de um video de ate 1 GB,
// cujo SHA-256 leva 2,4 s para 500 MB no servidor - nada muda na tela entre o
// clique e a resposta, e o proximo movimento previsivel e clicar de novo. Em
// "submeter a coordenacao" isso e duas notificacoes para a mesma transicao.
//
// A marca fica no FORMULARIO, e nao no botao: o que nao pode acontecer duas
// vezes e o envio, e ha formularios com quatro botoes de acao diferentes
// (`pessoas.html`: rebaixar, promover, excluir, reativar).
(function () {
  'use strict';

  var MARCA = 'data-enviando';

  // `aria-disabled`, e nunca `disabled`. Duas razoes, e a primeira e um defeito
  // silencioso:
  //
  // 1. O corpo do POST e montado DEPOIS do evento `submit`, e o par nome/valor
  //    de um botao desabilitado nao entra nele. Desabilitar aqui apagaria o
  //    `decisao=APROVAR` de `revisar.html` e o `acao=EXCLUIR` de `pessoas.html`,
  //    e a view receberia um pedido sem dizer o que fazer.
  // 2. Um botao que fica `disabled` perde o foco para o `<body>`, e quem navega
  //    por teclado e jogado para o topo da pagina no meio da propria acao.
  //
  // Como `aria-disabled` nao impede o clique, quem barra o segundo envio e a
  // marca no formulario, logo abaixo.
  function marcar(botao) {
    if (!botao) return;
    botao.setAttribute('aria-disabled', 'true');
    botao.classList.add('enviando');
  }

  function desmarcar(botao) {
    botao.removeAttribute('aria-disabled');
    botao.classList.remove('enviando');
  }

  function liberar(form) {
    if (!form || !form.removeAttribute) return;
    form.removeAttribute(MARCA);
    var botoes = form.querySelectorAll('[type="submit"]');
    Array.prototype.forEach.call(botoes, desmarcar);
  }

  // Na fase de CAPTURA, e nao na de bolha.
  //
  // Escutando no `document` em bolha, todo manipulador preso ao proprio
  // formulario roda ANTES deste - inclusive o do HTMX, que ja teria disparado o
  // pedido quando a marca fosse conferida. O segundo clique chegaria ao
  // servidor exatamente no unico formulario que faz pedido sem recarregar a
  // pagina. Achado num navegador de verdade, com os nove cenarios verdes.
  //
  // E `stopPropagation` junto do `preventDefault` no caminho barrado, porque
  // `preventDefault` sozinho cancela so a acao padrao do navegador: os outros
  // ouvintes rodam do mesmo jeito, e o do HTMX nao pergunta se o evento foi
  // cancelado antes de mandar o pedido.
  document.addEventListener('submit', function (evento) {
    var form = evento.target;
    // `upload.js` intercepta este formulario, tem barra de progresso propria e
    // um caminho de erro que pede nova tentativa. Bloquear aqui impediria a
    // pessoa de tentar de novo depois de um upload que caiu.
    if (form.matches && form.matches('[data-upload-video]')) return;

    if (form.hasAttribute(MARCA)) {
      evento.preventDefault();
      evento.stopPropagation();
      return;
    }
    form.setAttribute(MARCA, '');
    marcar(evento.submitter || form.querySelector('[type="submit"]'));
  }, true);

  // A validacao do lado do cliente barra o envio SEM disparar outro `submit`.
  // Sem isto, um campo invalido travaria o formulario para sempre: a pessoa
  // corrigiria o erro e o botao nao responderia mais.
  document.addEventListener('invalid', function (evento) {
    liberar(evento.target && evento.target.form);
  }, true);

  // O unico formulario HTMX do sistema (`_secao.html`) e substituido pela
  // resposta no caminho feliz. Quando o pedido falha nao ha troca, e sem isto
  // salvar uma secao com o servidor fora do ar travaria a secao ate recarregar.
  document.addEventListener('htmx:afterRequest', function (evento) {
    liberar(evento.target);
  });

  // Pagina restaurada do cache do navegador (voltar/avancar) volta com o DOM
  // como estava, marca inclusive. Sem isto, voltar e reenviar seria impossivel.
  window.addEventListener('pageshow', function (evento) {
    if (!evento.persisted) return;
    var formularios = document.querySelectorAll('[' + MARCA + ']');
    Array.prototype.forEach.call(formularios, liberar);
  });
})();
