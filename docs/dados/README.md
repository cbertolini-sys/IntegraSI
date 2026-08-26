# Dados de referência

## BNCC da Computação

A fixture `apps/referenciais/fixtures/bncc_computacao.json` traz o referencial e os
três eixos (Pensamento Computacional, Mundo Digital, Cultura Digital).

As habilidades (EF05CO01 e afins) NÃO estão no repositório: elas são transcritas do
Complemento à BNCC (Resolução CNE/CEB nº 1/2022) para um CSV com as colunas
`codigo,descricao,etapa,categoria` e importadas com:

    python manage.py loaddata bncc_computacao
    python manage.py importar_competencias --referencial BNCC-COMP --csv habilidades.csv

Importar de novo atualiza as descrições sem duplicar nada.
