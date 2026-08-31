#!/usr/bin/env bash
# Backup que nunca foi restaurado nao e backup (spec 13). Rode este script depois
# do primeiro backup, e uma vez por semestre. Ele derruba o banco de teste no
# final; nao toca no banco de producao em momento nenhum.
#
# O drill so vale se ele souber FALHAR. Um script que imprime contagens sem
# confer-las, ou que sai 0 com o dump quebrado no meio, so devolve a mesma falsa
# confianca que a spec 13 manda destruir.
set -euo pipefail

# Os caminhos sao os da instalacao; existem como variavel para que os testes
# possam apontar o drill para um diretorio de mentira e EXECUTAR o script, em vez
# de fazer grep nele. Em producao ninguem define nenhuma delas.
BANCO_TESTE="${INTEGRASI_BANCO_TESTE:-integrasi_restauracao}"
DESTINO_SQL="${INTEGRASI_BACKUP_SQL:-/srv/backups/sql}"
MIDIA="${INTEGRASI_MEDIA:-/srv/integrasi/media}"
MIDIA_TESTE="${INTEGRASI_RESTAURACAO:-/tmp/restauracao-teste}"

# Falhar no meio e o desfecho NORMAL de um drill que esta fazendo seu trabalho, e
# era exatamente aí que o script antigo largava para tras um banco
# `integrasi_restauracao` e uma copia da midia no /tmp do servidor, a cada
# semestre. O trap limpa nos dois desfechos.
limpar() {
  dropdb --if-exists "$BANCO_TESTE" >/dev/null 2>&1 || true
  rm -rf "$MIDIA_TESTE"
}
trap limpar EXIT

# `ls | head -1` sob `pipefail` e uma armadilha de SIGPIPE: o `head` fecha o cano
# depois da primeira linha, o `ls` morre com 141, o pipeline devolve 141 e `set -e`
# derruba o script aqui. Com poucos dumps nao acontece; com trinta dias de
# retencao, acontece. O `|| true` protege o pipeline e o `-z` abaixo e quem de
# fato recusa a ausencia de dump - a protecao nao pode virar silencio.
ULTIMO=$(ls -t "$DESTINO_SQL"/integrasi-*.sql.gz 2>/dev/null | head -1 || true)
if [ -z "$ULTIMO" ]; then
  echo "Nenhum dump em $DESTINO_SQL: nao ha o que restaurar." >&2
  exit 1
fi

echo "Restaurando $ULTIMO em $BANCO_TESTE"
dropdb --if-exists "$BANCO_TESTE"
createdb "$BANCO_TESTE"
# A extensao unaccent e a configuracao de busca vem no dump como comandos SQL
# (a migracao 0008 as criou no banco de origem), entao a restauracao precisa de
# um papel com direito de criar extensao -- o mesmo requisito da instalacao.
#
# `-v ON_ERROR_STOP=1` e o que faz um dump quebrado virar falha: sem ele o psql
# sai 0 mesmo com erro de SQL no meio, e nem `set -e` nem `pipefail` veem nada.
gunzip -c "$ULTIMO" | psql -q -v ON_ERROR_STOP=1 "$BANCO_TESTE"

CURSOS=$(psql -tAc "select count(*) from cursos_curso" "$BANCO_TESTE")
USUARIOS=$(psql -tAc "select count(*) from contas_usuario" "$BANCO_TESTE")
echo "Restaurado: $CURSOS cursos, $USUARIOS usuarios"
# Imprimir a contagem nao e conferir a contagem: um banco criado e vazio saia
# daqui com "concluida com sucesso", que e precisamente o desfecho que este drill
# existe para impedir. A afirmacao e sobre usuarios, e nao sobre cursos: uma
# instalacao recem-inaugurada tem zero cursos legitimamente, mas nunca zero
# usuarios -- `criar_coordenador` e passo da instalacao.
if [ "$USUARIOS" -eq 0 ]; then
  echo "Restauracao vazia: nenhum usuario no banco restaurado." >&2
  exit 1
fi

echo "Conferindo um arquivo de midia do backup:"
restic restore latest --target "$MIDIA_TESTE" --include "$MIDIA"
# `-print -quit` para no primeiro arquivo e nao usa cano nenhum: e a mesma
# armadilha de SIGPIPE do `ls` acima, so que garantida, porque a midia restaurada
# tem milhares de arquivos.
ACHADO=$(find "$MIDIA_TESTE" -type f -print -quit 2>/dev/null || true)
if [ -z "$ACHADO" ]; then
  # Repositorio vazio, `--include` errado, snapshot de outra maquina: em todos, o
  # `restic restore` sai 0 sem trazer arquivo nenhum.
  echo "O restic restore nao trouxe arquivo nenhum de $MIDIA." >&2
  exit 1
fi
echo "Arquivo restaurado: $ACHADO"

echo "Restauracao de teste concluida com sucesso."
