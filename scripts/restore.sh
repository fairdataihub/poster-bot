#!/usr/bin/env bash
# Restore a transferred posters dump into the running compose `db` service, then
# grant read access to the app role. Run after `docker compose up -d db`.
set -euo pipefail
cd "$(dirname "$0")/.."
DUMP="${1:-backup/posters.dump}"
[ -f "$DUMP" ] || { echo "dump not found: $DUMP — put the transferred file there first"; exit 1; }

echo "restoring $DUMP into the db service ..."
# warnings about the vector/pg_trgm extensions already existing are expected (the
# init script created them) and harmless, hence '|| true'.
docker compose exec -T db pg_restore --no-owner --no-privileges -U postgres -d posters < "$DUMP" || true

echo "granting read access to posterbot_ro ..."
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U postgres -d posters \
  -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO posterbot_ro;"

echo -n "verify: "
docker compose exec -T db psql -U posterbot_ro -d posters -tAc \
  "SELECT count(*) || ' posters, ' || count(embedding) || ' embeddings' FROM posters;"
