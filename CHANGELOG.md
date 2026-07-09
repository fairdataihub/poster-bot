# Changelog

All notable changes to poster-bot. Format follows [Keep a Changelog](https://keepachangelog.com);
versioning follows [SemVer](https://semver.org).

## [Unreleased]

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
- systemd --user units for the dedicated ollama instance and the API.
