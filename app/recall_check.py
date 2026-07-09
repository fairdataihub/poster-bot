#!/usr/bin/env python3
"""HNSW recall + latency spot-check: ANN top-10 (ef_search=100) vs exact scan.

Run after load + index build. Connects as the read-only role. Reports mean
recall@10 against an exact (index-disabled) nearest-neighbor scan on a set of
domain queries, plus the top-3 neighbors per query for eyeballing relevance.
"""
import os
from pathlib import Path

import numpy as np
import psycopg2

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ["CUDA_VISIBLE_DEVICES"] = ""

QUERIES = [
    "FAIR data principles for biomedical datasets",
    "single-cell RNA sequencing analysis pipeline",
    "machine learning for protein structure prediction",
    "Nextflow reproducible bioinformatics workflow",
    "knowledge graph for drug discovery",
    "ontology for genomic metadata harmonization",
    "microbiome 16S rRNA community analysis",
    "variant calling benchmark whole genome sequencing",
]


def env():
    out = {}
    for line in (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main():
    from sentence_transformers import SentenceTransformer
    e = env()
    m = SentenceTransformer("Alibaba-NLP/gte-large-en-v1.5", trust_remote_code=True, device="cpu")
    m.max_seq_length = 512
    conn = psycopg2.connect(host="127.0.0.1", port=int(e["POSTERBOT_DB_PORT"]),
                            dbname="posters", user="posterbot_ro",
                            password=e["POSTERBOT_RO_PASSWORD"])
    conn.set_session(readonly=True)

    def qv(t):
        v = m.encode([t], normalize_embeddings=True)[0]
        return "[" + ",".join(f"{x:.7f}" for x in v.tolist()) + "]"

    recalls = []
    for q in QUERIES:
        v = qv(q)
        with conn.cursor() as cur:
            cur.execute("SET LOCAL hnsw.ef_search = 100")
            cur.execute("""SELECT poster_key, title,
                                  1 - (embedding::halfvec(1024) <=> %s::halfvec(1024)) s
                           FROM posters
                           ORDER BY embedding::halfvec(1024) <=> %s::halfvec(1024)
                           LIMIT 10""", (v, v))
            ann = cur.fetchall()
            cur.execute("SET LOCAL enable_indexscan = off")
            cur.execute("SET LOCAL enable_bitmapscan = off")
            cur.execute("""SELECT poster_key FROM posters
                           ORDER BY embedding::halfvec(1024) <=> %s::halfvec(1024)
                           LIMIT 10""", (v,))
            exact = [r[0] for r in cur.fetchall()]
        rec = len({k for k, _, _ in ann} & set(exact)) / 10
        recalls.append(rec)
        print(f"\n[{q}]  recall@10={rec:.2f}")
        for _, t, s in ann[:3]:
            print(f"   {s:.3f}  {(t or '')[:72]}")
    print(f"\nmean recall@10 = {np.mean(recalls):.3f}  (target >= 0.98)")
    conn.close()


if __name__ == "__main__":
    main()
