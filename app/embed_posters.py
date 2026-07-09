#!/usr/bin/env python3
"""Embed flattened posters with gte-large-en-v1.5 (fp32) into resumable .npz shards.

Device is chosen by a pre-flight gate BEFORE torch loads: GPU0 if >=10GB free
(its tenants are desktop/media only), else GPU1 if >=30GB free (leaves >=18GB
slack for the transient qwen loads), else CPU. VRAM is hard-capped at ~8.5GB.
Batches are token-budgeted at 48k tokens (16 x 3072 measured 5.6GiB fp32).

Run:  nice -n 10 ionice -c2 -n7 python embed_posters.py \
        --in /storage/posterbot/scratch/posters.jsonl
"""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("OMP_NUM_THREADS", "8")
# variable batch shapes fragment the caching allocator (first run OOMed at the
# 8.5GB cap with 1.8GB reserved-but-unallocated); expandable segments fix that
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

SHARDS = Path("/storage/posterbot/shards")
MAX_SEQ = 3072
BATCH_TOKEN_BUDGET = 36_000
MAX_BATCH_DOCS = 256
SHARD_DOCS = 2000
VRAM_CAP_GB = 8.5


def pick_device():
    """(cuda_visible_devices or None, human reason) — runs before torch import."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.free,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        gpus = {int(a): (int(b), int(c)) for a, b, c in
                (tuple(x.strip() for x in l.split(",")) for l in out)}
    except Exception as e:
        return None, f"CPU (nvidia-smi failed: {e})"
    if 0 in gpus and gpus[0][0] >= 10_000:
        return "0", f"GPU0 RTX4090 (free {gpus[0][0]} MiB, util {gpus[0][1]}%)"
    if 1 in gpus and gpus[1][0] >= 30_000:
        return "1", f"GPU1 (free {gpus[1][0]} MiB, util {gpus[1][1]}%) — capped, >=18GB slack kept"
    return None, f"CPU (gate failed: {gpus})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    args = ap.parse_args()

    dev, why = pick_device()
    if dev is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = dev
    print(f"device gate: {why}", flush=True)

    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    use_cuda = dev is not None and torch.cuda.is_available()
    if use_cuda:
        total_gb = torch.cuda.get_device_properties(0).total_memory / 2**30
        torch.cuda.set_per_process_memory_fraction(min(1.0, VRAM_CAP_GB / total_gb), 0)
    else:
        torch.set_num_threads(16)

    SHARDS.mkdir(exist_ok=True)
    done = set()
    for f in sorted(SHARDS.glob("shard_*.npz")):
        done.update(np.load(f, allow_pickle=False)["keys"].tolist())
    shard_idx = len(list(SHARDS.glob("shard_*.npz")))
    print(f"resume: {len(done)} vectors in {shard_idx} existing shards", flush=True)

    rows = []
    with open(args.inp, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["poster_key"] not in done:
                rows.append((r["poster_key"], r["embed_text"],
                             min(int(r["embed_tokens"]), MAX_SEQ)))
    total = len(rows)
    print(f"to embed: {total}", flush=True)
    if not total:
        print("nothing to do"); return

    rows.sort(key=lambda r: -r[2])           # uniform-length batches
    model = SentenceTransformer("Alibaba-NLP/gte-large-en-v1.5",
                                trust_remote_code=True,
                                device="cuda" if use_cuda else "cpu")   # fp32
    model.max_seq_length = MAX_SEQ
    model.eval()
    print("model loaded (fp32)", flush=True)

    buf_keys, buf_vecs, done_n, t0 = [], [], 0, time.time()

    def flush():
        nonlocal shard_idx, buf_keys, buf_vecs
        if not buf_keys:
            return
        np.savez(SHARDS / f"shard_{shard_idx:05d}.npz",
                 keys=np.array(buf_keys), emb=np.vstack(buf_vecs).astype(np.float32))
        shard_idx += 1
        buf_keys, buf_vecs = [], []

    i = 0
    while i < total:
        batch, cost = [], 0
        while i < total and len(batch) < MAX_BATCH_DOCS:
            c = max(rows[i][2], 32)
            if batch and cost + c > BATCH_TOKEN_BUDGET:
                break
            batch.append(rows[i]); cost += c; i += 1
        embs = model.encode([b[1] for b in batch], batch_size=len(batch),
                            normalize_embeddings=True, show_progress_bar=False)
        buf_keys.extend(b[0] for b in batch)
        buf_vecs.append(embs)
        done_n += len(batch)
        if len(buf_keys) >= SHARD_DOCS:
            flush()
            if use_cuda:
                torch.cuda.empty_cache()
            rate = done_n / (time.time() - t0)
            vram = (f", peak VRAM {torch.cuda.max_memory_allocated(0)/2**30:.1f}G"
                    if use_cuda else "")
            print(f"{done_n}/{total}  {rate:.0f} docs/s  "
                  f"ETA {(total-done_n)/rate/60:.1f} min{vram}", flush=True)
    flush()
    print(f"DONE: {done_n} embedded in {(time.time()-t0)/60:.1f} min "
          f"({shard_idx} shards total)", flush=True)


if __name__ == "__main__":
    main()
