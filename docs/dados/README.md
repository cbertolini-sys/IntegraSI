# Dados de referencia

## BNCC da Computacao

A fixture `apps/referenciais/fixtures/bncc_computacao.json` traz o referencial e os
tres eixos (Pensamento Computacional, Mundo Digital, Cultura Digital).

As habilidades (EF05CO01 e afins) NAO estao no repositorio: elas sao transcritas do
Complemento a BNCC (Resolucao CNE/CEB no 1/2022) para um CSV com as colunas
`codigo,descricao,etapa,categoria` e importadas com:

    python manage.py loaddata bncc_computacao
    python manage.py importar_competencias --referencial BNCC-COMP --csv habilidades.csv

Importar de novo atualiza as descricoes sem duplicar nada.
