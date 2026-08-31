// Carrossel dos últimos cursos publicados, no herói da página inicial.
//
// Sem dependência: o projeto vendoriza o que usa e não carrega biblioteca de
// carrossel para ~90 linhas. Progressivo por desenho - sem JS, o primeiro slide
// fica visível e os outros ficam no DOM para quem navega por leitor de tela; o
// que se perde é a troca automática, não o conteúdo.
(function () {
  'use strict';

  var INTERVALO = 6000;

  function iniciar(raiz) {
    var slides = Array.prototype.slice.call(raiz.querySelectorAll('.vitrine-slide'));
    if (slides.length < 2) return;

    var pontos = Array.prototype.slice.call(raiz.querySelectorAll('.ponto'));
    var anterior = raiz.querySelector('[data-anterior]');
    var proxima = raiz.querySelector('[data-proxima]');
    var atual = 0;
    var relogio = null;

    // A preferência é lida uma vez e observada: quem liga "reduzir movimento" no
    // sistema com a página aberta para o autoplay na hora, sem recarregar.
    var semMovimento = window.matchMedia('(prefers-reduced-motion: reduce)');

    function mostrar(indice) {
      atual = (indice + slides.length) % slides.length;
      slides.forEach(function (slide, i) {
        var ativo = i === atual;
        slide.classList.toggle('ativo', ativo);
        // aria-hidden acompanha a visibilidade: sem isto o leitor de tela leria
        // os dez cursos em sequência como se estivessem todos na tela.
        slide.setAttribute('aria-hidden', ativo ? 'false' : 'true');
      });
      pontos.forEach(function (ponto, i) {
        ponto.classList.toggle('ativo', i === atual);
        ponto.setAttribute('aria-selected', i === atual ? 'true' : 'false');
      });
    }

    function andar(passo) {
      mostrar(atual + passo);
    }

    function tocar() {
      parar();
      if (semMovimento.matches) return;
      relogio = window.setInterval(function () {
        andar(1);
      }, INTERVALO);
    }

    function parar() {
      if (relogio !== null) {
        window.clearInterval(relogio);
        relogio = null;
      }
    }

    if (anterior) {
      anterior.addEventListener('click', function () {
        andar(-1);
        tocar();
      });
    }
    if (proxima) {
      proxima.addEventListener('click', function () {
        andar(1);
        tocar();
      });
    }
    pontos.forEach(function (ponto) {
      ponto.addEventListener('click', function () {
        mostrar(parseInt(ponto.dataset.irPara, 10));
        tocar();
      });
    });

    // Pausa no hover e também no foco do teclado: quem navega por Tab está lendo
    // o cartão tanto quanto quem parou o mouse nele, e trocar embaixo do foco
    // levaria a pessoa para um link que ela não escolheu.
    raiz.addEventListener('mouseenter', parar);
    raiz.addEventListener('mouseleave', tocar);
    raiz.addEventListener('focusin', parar);
    raiz.addEventListener('focusout', function (evento) {
      if (!raiz.contains(evento.relatedTarget)) tocar();
    });

    raiz.addEventListener('keydown', function (evento) {
      if (evento.key === 'ArrowLeft') {
        andar(-1);
        tocar();
      } else if (evento.key === 'ArrowRight') {
        andar(1);
        tocar();
      }
    });

    // Aba escondida não anima: sem isto o carrossel avança dez vezes enquanto
    // ninguém olha e a pessoa volta num slide aleatório.
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) parar();
      else tocar();
    });

    if (semMovimento.addEventListener) {
      semMovimento.addEventListener('change', tocar);
    }

    mostrar(0);
    tocar();
  }

  function ligar() {
    document.querySelectorAll('[data-carrossel]').forEach(iniciar);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ligar);
  } else {
    ligar();
  }
})();
