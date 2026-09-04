#!/usr/bin/env bash
# Backup do IntegraSI (spec 13). Sao dois problemas distintos, e este script
# resolve UM deles:
#
#   - erro humano (um curso apagado, um migrate errado) -> `pg_dump` diario,
#     30 dias de retencao. E o que este script faz.
#   - perder a maquina -> backup diario da VM, mantido pelo CPD da UFSM. Ele
#     leva o disco inteiro, e portanto tambem a midia em /srv/integrasi/media e
#     os dumps que este script deixa em /srv/backups/sql.
#
# Por isso o dump fica no disco da propria VM DE PROPOSITO, e nao num destino
# externo: quem o tira daqui e o backup do CPD. A consequencia esta escrita em
# docs/operacao.md seccao 3, e vale repetir onde o operador vai ler primeiro:
# se um dia esta VM deixar de ser copiada pelo CPD, este script passa a nao
# proteger de perda de disco nenhuma, e o backup precisa de destino proprio.
set -euo pipefail

DESTINO_SQL=/srv/backups/sql
mkdir -p "$DESTINO_SQL"
ARQUIVO="$DESTINO_SQL/integrasi-$(date +%Y%m%d).sql.gz"

pg_dump --no-owner integrasi | gzip > "$ARQUIVO"
find "$DESTINO_SQL" -name 'integrasi-*.sql.gz' -mtime +30 -delete

echo "Backup concluido em $(date --iso-8601=seconds)"
