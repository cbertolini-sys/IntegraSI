// Editor de texto das secoes do Plano de Ensino, com Quill.
//
// A barra oferece EXATAMENTE o que `Secao.save()` preserva. Ela sanitiza com nh3
// contra `TAGS_PERMITIDAS` (apps/cursos/models/producao.py), incondicionalmente:
// oferecer um botao de cor, de imagem ou de tabela aqui faria a pessoa formatar,
// salvar, e ver a formatacao sumir sem explicacao nenhuma. Se aquela lista mudar,
// esta barra muda junto.
(function () {
  'use strict';

  if (typeof window.Quill !== 'function') return;

  var BARRA = [
    [{ header: [2, 3, false] }],
    ['bold', 'italic', 'underline'],
    [{ list: 'ordered' }, { list: 'bullet' }],
    ['blockquote', 'link'],
    ['clean']
  ];

  function ligar(campo) {
    if (campo.dataset.editorLigado) return;
    campo.dataset.editorLigado = '1';

    var caixa = document.createElement('div');
    caixa.className = 'editor-secao';
    campo.parentNode.insertBefore(caixa, campo);
    // O textarea continua no formulario, escondido: e ele que o Django recebe, e
    // e ele que guarda o valor quando o JS nao roda.
    campo.classList.add('visualmente-oculto');

    var editor = new window.Quill(caixa, {
      theme: 'snow',
      modules: { toolbar: BARRA },
      placeholder: campo.getAttribute('placeholder') || 'Escreva aqui.'
    });
    editor.clipboard.dangerouslyPasteHTML(campo.value || '');

    // Sincroniza a cada tecla, e nao no submit: o formulario e enviado por HTMX,
    // que le o valor do campo direto, sem disparar o evento de submit onde um
    // "copiar agora" caberia.
    editor.on('text-change', function () {
      var html = editor.getSemanticHTML();
      campo.value = html === '<p><br></p>' ? '' : html;
    });
  }

  function ligarTudo(raiz) {
    if (!raiz || !raiz.querySelectorAll) return;
    raiz.querySelectorAll('textarea[data-editor]').forEach(ligar);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { ligarTudo(document); });
  } else {
    ligarTudo(document);
  }

  // A secao salva volta trocada por HTMX, com um textarea novo.
  document.addEventListener('htmx:afterSwap', function (evento) {
    ligarTudo(evento.target);
  });
})();
