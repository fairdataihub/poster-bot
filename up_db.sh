#!/usr/bin/env bash
# posterbot-db launcher. Plain `docker run` on purpose: docker here is the snap,
# whose CLIENT cannot read files outside $HOME (no compose/--env-file), and whose
# daemon namespace lacks /storage entirely — binds under /storage silently go to a
# phantom dir. /mnt/fast IS propagated (verified 2026-07-09), so pgdata lives at
# /mnt/fast/posterbot_pgdata. Same pattern as the pubverse_pgvector deployment.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a

mkdir -p /mnt/fast/posterbot_pgdata

if docker ps -a --format '{{.Names}}' | grep -qx posterbot-db; then
  echo "posterbot-db already exists — use ./down_db.sh first (data survives in /mnt/fast/posterbot_pgdata)"
  exit 1
fi

docker run -d --name posterbot-db \
  --restart unless-stopped \
  --cpus 4 --memory 6g --shm-size 1g \
  -p "127.0.0.1:${POSTERBOT_DB_PORT}:5432" \
  -e POSTGRES_PASSWORD="${POSTERBOT_PG_SUPER_PASSWORD}" \
  -e POSTGRES_DB=posters \
  -v /mnt/fast/posterbot_pgdata:/var/lib/postgresql/data \
  --health-cmd 'pg_isready -U postgres -d posters' \
  --health-interval 10s --health-timeout 5s --health-retries 12 \
  pgvector/pgvector:pg15 \
  postgres \
    -c shared_buffers=2GB \
    -c effective_cache_size=4GB \
    -c maintenance_work_mem=1GB \
    -c max_parallel_maintenance_workers=2 \
    -c max_connections=50 \
    -c log_min_duration_statement=2000

echo -n "waiting for healthy"
for _ in $(seq 1 30); do
  st=$(docker inspect -f '{{.State.Health.Status}}' posterbot-db 2>/dev/null || echo starting)
  [ "$st" = healthy ] && { echo " — healthy"; exit 0; }
  echo -n "."
  sleep 2
done
echo " — NOT healthy, check: docker logs posterbot-db"
exit 1
