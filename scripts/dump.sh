#!/usr/bin/env bash
# Produce a portable data dump of the posters DB, to transfer to another machine
# (e.g. the CoFest laptop). Run on a host where the posterbot-db container is up.
# Output: backup/posters.dump  (custom format, --no-owner/--no-privileges so it
# restores cleanly under any role setup).
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${1:-backup/posters.dump}"
mkdir -p "$(dirname "$OUT")"

docker exec posterbot-db pg_dump -U postgres --no-owner --no-privileges -Fc posters > "$OUT"

echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
echo "transfer it to the target machine's ./backup/posters.dump, then run: make restore"
