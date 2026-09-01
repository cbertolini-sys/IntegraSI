// Tooltips de ajuda dos campos, com Tippy.js.
//
// A explicacao de cada campo mora no `help_text` do formulario, em Python: e la
// que ela fica junto da definicao do campo, versionada, e onde um teste consegue
// exigir que todo campo tenha uma. O JS so decide COMO mostrar.
//
// Formulario novo ganha tooltip sozinho, por dois caminhos:
//   1. `templates/cursos/_campo.html` desenha o gatilho a partir do help_text;
//   2. para quem renderiza com `form.as_p`, o Django escreve o help_text num
//      `.helptext`, e este arquivo o converte em gatilho.
// Nenhum dos dois pede que alguem lembre de acrescentar nada.
(function () {
  'use strict';

  if (typeof window.tippy !== 'function') return;

  var OPCOES = {
    theme: 'integrasi',
    placement: 'right',
    maxWidth: 300,
    // Atraso na entrada e nao na saida: passar o mouse por cima a caminho de
    // outro campo nao pode disparar uma nuvem de balões.
    delay: [250, 0],
    // Toque longo no celular: toque curto ali e a pessoa tentando usar o campo.
    touch: ['hold', 400],
    appendTo: function () { return document.body; }
  };

  function gatilho(texto, rotulo) {
    var botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'ajuda-campo';
    botao.setAttribute('data-ajuda', texto);
    botao.setAttribute('aria-label', 'O que é ' + (rotulo || 'este campo'));
    // O balão é redundante para leitor de tela, que já recebe o texto pelo
    // `aria-describedby` do campo. Escondê-lo da árvore de acessibilidade
    // evita a explicação ser anunciada duas vezes.
    botao.setAttribute('tabindex', '-1');
    botao.textContent = '?';
    return botao;
  }

  // O Django escreve o help_text visivel; vira gatilho para o formulario nao
  // ficar comprido.
  //
  // O span e ESCONDIDO, e nao removido. O Django aponta o campo para ele com
  // `aria-describedby="id_x_helptext"`, e apagar o elemento deixaria a referencia
  // pendurada: quem usa leitor de tela perderia a explicacao exatamente por causa
  // da melhoria visual. Escondido, ele continua sendo lido.
  function converterHelptextDoDjango(raiz) {
    raiz.querySelectorAll('.helptext:not(.visualmente-oculto)').forEach(function (ajuda) {
      var campo = ajuda.closest('p, div, li, fieldset');
      var rotulo = campo && campo.querySelector('label');
      if (!rotulo) return;
      var texto = ajuda.textContent.trim();
      if (!texto) return;
      rotulo.appendChild(gatilho(texto, rotulo.textContent.trim()));
      ajuda.classList.add('visualmente-oculto');
    });
  }

  function ligar(raiz) {
    if (!raiz || !raiz.querySelectorAll) return;
    converterHelptextDoDjango(raiz);
    var alvos = raiz.querySelectorAll('[data-ajuda]:not([data-ajuda-ligada])');
    alvos.forEach(function (alvo) {
      alvo.setAttribute('data-ajuda-ligada', '');
      window.tippy(alvo, Object.assign({ content: alvo.getAttribute('data-ajuda') }, OPCOES));
    });
  }

  function ligarTudo() {
    ligar(document);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ligarTudo);
  } else {
    ligarTudo();
  }

  // Bloco trocado por HTMX chega sem tooltip: a ficha do curso troca o
  // referencial, a etapa e as habilidades sem recarregar a pagina, e sem isto os
  // campos que voltam da troca ficariam mudos.
  document.addEventListener('htmx:afterSwap', function (evento) {
    ligar(evento.target);
  });
})();
