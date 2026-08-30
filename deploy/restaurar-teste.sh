#!/usr/bin/env bash
# Backup que nunca foi restaurado nao e backup (spec 13). Rode este script depois
# do primeiro backup, e uma vez por semestre. Ele derruba o banco de teste no
# final; nao toca no banco de producao em momento nenhum.
set -euo pipefail

BANCO_TESTE=integrasi_restauracao
ULTIMO=$(ls -t /srv/backups/sql/integrasi-*.sql.gz | head -1)

echo "Restaurando $ULTIMO em $BANCO_TESTE"
dropdb --if-exists "$BANCO_TESTE"
createdb "$BANCO_TESTE"
# A extensao unaccent e a configuracao de busca vem no dump como comandos SQL
# (a migracao 0008 as criou no banco de origem), entao a restauracao precisa de
# um papel com direito de criar extensao -- o mesmo requisito da instalacao.
gunzip -c "$ULTIMO" | psql -q "$BANCO_TESTE"

CURSOS=$(psql -tAc "select count(*) from cursos_curso" "$BANCO_TESTE")
USUARIOS=$(psql -tAc "select count(*) from contas_usuario" "$BANCO_TESTE")
echo "Restaurado: $CURSOS cursos, $USUARIOS usuarios"

echo "Conferindo um arquivo de midia do backup:"
restic restore latest --target /tmp/restauracao-teste --include /srv/integrasi/media
find /tmp/restauracao-teste -type f | head -3

dropdb "$BANCO_TESTE"
rm -rf /tmp/restauracao-teste
echo "Restauracao de teste concluida com sucesso."
