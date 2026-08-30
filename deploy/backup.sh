#!/usr/bin/env bash
# Backup do IntegraSI. Sao dois problemas diferentes (spec 13):
#   - o banco e pequeno e o que salva de erro humano -> pg_dump diario, 30 dias
#   - a midia e grande e cresce -> copia incremental deduplicada para fora do servidor
set -euo pipefail

DESTINO_SQL=/srv/backups/sql
MEDIA=/srv/integrasi/media
export RESTIC_REPOSITORY="${RESTIC_REPOSITORY:?defina o repositorio restic}"
export RESTIC_PASSWORD_FILE=/srv/integrasi/.restic-senha

mkdir -p "$DESTINO_SQL"
ARQUIVO="$DESTINO_SQL/integrasi-$(date +%Y%m%d).sql.gz"

pg_dump --no-owner integrasi | gzip > "$ARQUIVO"
find "$DESTINO_SQL" -name 'integrasi-*.sql.gz' -mtime +30 -delete

restic backup "$MEDIA" "$DESTINO_SQL" --tag integrasi
# `--tag integrasi`, a mesma da linha acima: sem ela esta politica de retencao
# apaga TODO snapshot do repositorio, inclusive os de outra maquina que o
# compartilhe. `docs/operacao.md` pressupoe repositorio dedicado, mas a tag ja
# esta escrita uma linha acima e sai de graca.
restic forget --tag integrasi --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --prune

echo "Backup concluido em $(date --iso-8601=seconds)"
