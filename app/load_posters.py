#!/usr/bin/env python3
"""Load flattened posters + embedding shards into posterbot-db (127.0.0.1:5445).

Joins scratch/posters.jsonl with shards/*.npz on poster_key and upserts via
execute_values in pages of 200. Idempotent (ON CONFLICT poster_key DO UPDATE).
Connects as posterbot_owner; the serving role stays read-only.
"""
import json
from pathlib import Path

import numpy as np
import psycopg2
from psycopg2.extras import Json, execute_values


def denul(v):
    """Recursively strip NUL bytes — PostgreSQL text/jsonb reject 0x00."""
    if isinstance(v, str):
        return v.replace("\x00", " ")
    if isinstance(v, list):
        return [denul(x) for x in v]
    if isinstance(v, dict):
        return {k: denul(x) for k, x in v.items()}
    return v

ROOT = Path("/storage/posterbot")


def env():
    out = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


COLS = ("poster_key doi repo_id source title description subjects creators "
        "creators_text conference_name conference_year publication_year research_field "
        "rights license_class license_blocked n_sections embed_tokens full_text url "
        "embedding").split()
UPDATE = ", ".join(f"{c}=EXCLUDED.{c}" for c in COLS[1:])
SQL = (f"INSERT INTO posters ({', '.join(COLS)}) VALUES %s "
       f"ON CONFLICT (poster_key) DO UPDATE SET {UPDATE}")
TEMPLATE = "(" + ", ".join(["%s"] * (len(COLS) - 1)) + ", %s::vector)"


def main():
    vecs = {}
    for f in sorted((ROOT / "shards").glob("shard_*.npz")):
        d = np.load(f, allow_pickle=False)
        for k, v in zip(d["keys"].tolist(), d["emb"]):
            vecs[k] = v
    print(f"vectors: {len(vecs)}")

    rows, missing, seen_doi = [], [], set()
    with open(ROOT / "scratch/posters.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = denul(json.loads(line))
            v = vecs.get(r["poster_key"])
            if v is None:
                missing.append(r["poster_key"])
                continue
            doi = r["doi"]
            if doi is not None:
                if doi in seen_doi:
                    print(f"duplicate doi {doi} -> storing NULL doi for {r['poster_key']}")
                    doi = None
                else:
                    seen_doi.add(doi)
            emb = "[" + ",".join(f"{x:.7f}" for x in v.tolist()) + "]"
            rows.append((
                r["poster_key"], doi, r["repo_id"], r["source"],
                r["title"], r["description"], r["subjects"],
                Json(r["creators"]) if r["creators"] is not None else None,
                r["creators_text"], r["conference_name"], r["conference_year"],
                r["publication_year"], r["research_field"], r["rights"],
                r["license_class"], r["license_blocked"], r["n_sections"],
                r["embed_tokens"], r["embed_text"], r["url"], emb,
            ))
    print(f"rows to upsert: {len(rows)}; missing vectors: {len(missing)}")
    if missing[:5]:
        print("  e.g.", missing[:5])

    e = env()
    conn = psycopg2.connect(host="127.0.0.1", port=int(e["POSTERBOT_DB_PORT"]),
                            dbname="posters", user="posterbot_owner",
                            password=e["POSTERBOT_OWNER_PASSWORD"])
    conn.autocommit = False
    with conn, conn.cursor() as cur:
        for i in range(0, len(rows), 2000):
            execute_values(cur, SQL, rows[i:i + 2000],
                           template=TEMPLATE, page_size=200)
            print(f"  upserted {min(i + 2000, len(rows))}/{len(rows)}", flush=True)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), count(embedding), count(*) FILTER (WHERE license_class='allowed') FROM posters")
        total, with_emb, allowed = cur.fetchone()
        print(f"DB: {total} rows, {with_emb} embeddings, {allowed} allowed-license")
    conn.close()


if __name__ == "__main__":
    main()
