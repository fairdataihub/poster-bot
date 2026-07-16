# Running posterbot locally (laptop / any Docker host)

A self-contained version of the stack that runs on one machine — pgvector +
a local chat LLM (ollama) + the API/UI — all in Docker, everything on
`127.0.0.1`. Designed to fit an **8GB-VRAM laptop**: the chat model uses the GPU
(~4GB for `llama3.2:3b`), and query embedding runs on **CPU**, so the GPU is
never oversubscribed.

```
browser ──► 127.0.0.1:8722  api (FastAPI + gte-large-en-v1.5 on CPU)
                               ├──► db     pgvector/pgvector:pg15   (31,363 posters)
                               └──► ollama llama3.2:3b on the GPU
```

## Requirements
- Docker + Docker Compose v2+.
- **For GPU:** [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  installed and configured. No GPU / not set up? Delete the `deploy:` block under
  the `ollama` service in `docker-compose.yml` and it runs on CPU (slower, still works).
- The **data**: a `posters.dump` file (~0.5GB) produced from the built database —
  it's too large for git, so transfer it separately (USB / scp / cloud). Produce
  it on a machine where the DB is already built with `scripts/dump.sh`.

## First-time setup

```bash
git clone https://github.com/fairdataihub/poster-bot.git
cd poster-bot
cp .env.example .env          # then edit: set the three passwords (openssl rand …)

# build + start db, ollama, api; pull the chat model
make up

# load the poster data (one time) — point at your transferred dump
make restore DUMP=/path/to/posters.dump

# check everything
make health                   # -> {"db":31363,"model":true,"llm":true}
```

Open **http://127.0.0.1:8722** and ask away. First chat is slow (model warms up),
then it's fast.

## Day-to-day
| Command | What it does |
|---|---|
| `docker compose up -d` | start (after first `make up` build) |
| `make down` | stop (the DB + model volumes persist) |
| `make health` | check db / embedding model / llm |
| `make logs` | tail all services |
| `make pull-model MODEL=llama3.2:1b` | switch to a smaller model if VRAM is tight |
| edit `LLM_MODEL` in `.env`, `make rebuild` | make the API use a different model |

## VRAM notes (8GB laptop)
- `llama3.2:3b` ≈ 4GB on the GPU; query embedding is on CPU (0 VRAM). Comfortable.
- If the laptop also drives its display off the same GPU and you see OOM, switch to
  `llama3.2:1b` (`make pull-model MODEL=llama3.2:1b`, set `LLM_MODEL=llama3.2:1b`,
  `make rebuild`) — ~1.5GB.
- The API container is CPU-only by design, so it never competes for VRAM.

## Rebuilding the data from scratch (no dump available)
If you have the canonical corpus JSONs instead of a dump, you can rebuild — see
the host pipeline in `README.md` (`flatten_posters.py` → `embed_posters.py` →
`load_posters.py` → `init/03_indexes.sql`). On a laptop this takes longer
(embedding 31k posters); the dump path is strongly preferred for a demo.

## Security / privacy
Everything is loopback-only and offline: no query leaves the laptop, the DB role
is read-only, poster text is treated as untrusted, and DOI links are built
server-side. To expose it to others, see `deploy/EXPOSE-via-relay-vps.md`
(and set `EVENT_CODE` first).
