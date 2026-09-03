/* O menu da pessoa no cabecalho.
 *
 * O <details> ja abre, fecha e navega por teclado sozinho. Este arquivo so
 * acrescenta as duas coisas que ele nao faz: fechar ao clicar fora e fechar no
 * Esc. Sem elas o menu fica aberto atras da proxima coisa que a pessoa clicar.
 *
 * Se este script nao carregar, o menu continua inteiro - so fecha por um segundo
 * clique no proprio nome.
 */
(function () {
  "use strict";

  function fecha(exceto) {
    document.querySelectorAll("details.menu-pessoa[open]").forEach(function (menu) {
      if (menu !== exceto) {
        menu.open = false;
      }
    });
  }

  document.addEventListener("click", function (evento) {
    var dentro = evento.target.closest("details.menu-pessoa");
    fecha(dentro);
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key !== "Escape") {
      return;
    }
    var aberto = document.querySelector("details.menu-pessoa[open]");
    if (aberto) {
      aberto.open = false;
      /* O foco volta para o gatilho: sem isso ele fica no elemento que acabou de
         sumir, e a proxima tabulacao recomeca do topo da pagina. */
      var gatilho = aberto.querySelector("summary");
      if (gatilho) {
        gatilho.focus();
      }
    }
  });
})();
