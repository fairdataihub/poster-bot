#!/usr/bin/env bash
# Stops and removes ONLY the posterbot-db container. Data survives in
# /mnt/fast/posterbot_pgdata (delete that dir manually for full teardown).
set -euo pipefail
docker rm -f posterbot-db
echo "posterbot-db removed; pgdata retained at /mnt/fast/posterbot_pgdata"
