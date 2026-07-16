# Changelog

All notable changes to poster-bot. Format follows [Keep a Changelog](https://keepachangelog.com);
versioning follows [SemVer](https://semver.org).

## [Unreleased]

### Added
- **Portable local deployment** (`docker compose`): `Dockerfile` (CPU API image
  with the embedding model baked in), `docker-compose.yml` (pgvector + ollama +
  API, all loopback, GPU-optional), first-boot DB init, `scripts/dump.sh` /
  `scripts/restore.sh` for shipping the built database to another machine,
  a `Makefile`, and [LOCAL-DEPLOY.md](LOCAL-DEPLOY.md). Runs on an 8GB-VRAM
  laptop (chat model on GPU, query embedding on CPU). Restore path verified
  end-to-end against a fresh container.
- Route B public exposure guide (relay VPS + reverse-SSH tunnel).

### Changed
- `app.py` config is now fully environment-driven (DB host/port/creds, LLM URL,
  log dir, model) so the same code runs as a host systemd service or a container.

## [0.1.0] - 2026-07-09

First working end-to-end stack: 31,363 posters embedded, indexed, and queryable
through hybrid retrieval + grounded local-LLM chat. Loopback-only; public
exposure is a later milestone. Recall@10 = 1.000 vs exact scan; chat latency ~3s.

### Added
- pgvector (pg15, 0.8.2) database launcher with loopback-only binding, resource caps,
  read-only serving role, and `posters` schema (metadata + `vector(1024)` + generated tsvector).
- Corpus flattener for the canonical posters.science merged dirs (31,363 records):
  sanitization per the corpus anomaly audits, license classification via the corpus
  repo's `license_policy.py`, DOI-first keying.
- Resumable GPU embedding pipeline (gte-large-en-v1.5, fp32, max_seq 3072,
  VRAM-capped, device-gated, token-budgeted batches, `.npz` shards).
- Idempotent bulk loader and post-load HNSW halfvec (m=16, ef_construction=128) +
  GIN/btree index build.
- FastAPI service: hybrid retrieval (HNSW + FTS, reciprocal-rank fusion),
  SSE chat grounded in top-8 posters via a local ollama model, license-aware
  context (full text only for `allowed`), per-session rate limits, query logging.
- Dependency-free chat UI with escape-by-default rendering and DOI citation cards.
- systemd --user units for the dedicated ollama instance and the API
  (CUDA-pinned to a single GPU, context-length-pinned, generous memory).
- `recall_check.py` HNSW-vs-exact recall spot-check.
