// Editor de texto das secoes do Plano de Ensino, com Quill.
//
// A barra oferece EXATAMENTE o que `Secao.save()` preserva. Ela sanitiza com nh3
// contra `TAGS_PERMITIDAS` (apps/cursos/models/producao.py), incondicionalmente:
// oferecer um botao de cor, de imagem ou de tabela aqui faria a pessoa formatar,
// salvar, e ver a formatacao sumir sem explicacao nenhuma. Se aquela lista mudar,
// esta barra muda junto.
(function () {
  'use strict';

  // O bundle vendorizado do Quill faz `.replaceAll(" ", "&nbsp;")` ao serializar
  // (`getSemanticHTML`), SEM CONDICAO nenhuma - nao so em sequencias de espaco
  // repetido, qualquer espaco. Um paragrafo inteiro de prosa vira, para o
  // navegador, uma unica "palavra" sem ponto de quebra: numa caixa mais estreita
  // que a linha toda (a ficha do curso, o comentario de revisao), o texto
  // atravessa a caixa e some atras do card vizinho, em vez de dobrar a linha.
  // Achado numa revisao de verdade, com a suite inteira verde.
  //
  // Nao ha como o usuario pedir um espaco que nao quebra de proposito - a barra
  // nao oferece isso - entao todo `&nbsp;` que sai daqui e espaco comum digitado
  // e nada mais. Duas trocas seguidas (de um espaco duplo, por exemplo) viram
  // dois espacos comuns, que o navegador colapsa visualmente num so ao
  // renderizar: perda aceitavel, e a mesma que aconteceria digitando direto
  // num campo de texto qualquer.
  //
  // Fora da guarda do Quill, de proposito: assim um teste sob node prova esta
  // funcao sem precisar simular o editor inteiro (tests/js/testa_editor.js).
  function normalizarEspacos(html) {
    return html.replace(/&nbsp;/g, ' ');
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { normalizarEspacos: normalizarEspacos };
  }

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
    // A altura curta acompanha as `rows` do textarea, e nao o formulario em que
    // ele esta: era uma regra presa a `[data-upload-video]`, e o campo seguinte a
    // pedir um editor baixo nasceria com as 13rem das secoes do Plano de Ensino.
    var linhas = parseInt(campo.getAttribute('rows'), 10) || 10;
    caixa.className = linhas <= 4 ? 'editor-secao editor-curto' : 'editor-secao';
    campo.parentNode.insertBefore(caixa, campo);
    // O textarea continua no formulario, escondido: e ele que o Django recebe, e
    // e ele que guarda o valor quando o JS nao roda.
    campo.classList.add('visualmente-oculto');

    var editor = new window.Quill(caixa, {
      theme: 'snow',
      modules: { toolbar: BARRA },
      placeholder: campo.getAttribute('placeholder') || 'Escreva aqui.'
    });
    // `setContents`, e nao `dangerouslyPasteHTML`: aquele chama `setSelection(0)`
    // logo depois de gravar o conteudo (esta assim no bundle vendorizado), e
    // `setSelection` foca o editor. A pagina abria com o cursor dentro da
    // descricao; no Plano de Ensino, dentro da ultima das sete secoes, depois de
    // rolar ate ela. `setContents` sozinho nao mexe na selecao.
    //
    // Fonte 'silent' porque carregar o valor nao e edicao: com a fonte padrao o
    // `text-change` abaixo disparava na abertura e reescrevia o campo com o que
    // ele ja tinha.
    editor.setContents(
      editor.clipboard.convert({ html: campo.value || '', text: '' }),
      'silent'
    );

    // Sincroniza a cada tecla, e nao no submit: o formulario e enviado por HTMX,
    // que le o valor do campo direto, sem disparar o evento de submit onde um
    // "copiar agora" caberia.
    editor.on('text-change', function () {
      var html = normalizarEspacos(editor.getSemanticHTML());
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
