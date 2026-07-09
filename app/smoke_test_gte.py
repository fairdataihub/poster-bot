#!/usr/bin/env python3
"""GTE-large-en-v1.5 smoke test for the posterbot ingest.

Verifies: offline load from HF cache, CUDA, 1024-dim L2-normalized output,
and VRAM behavior for a worst-case long batch at the ingest settings
(fp32, max_seq_length=3072). Run: CUDA_VISIBLE_DEVICES=0 nice -n 10 python smoke_test_gte.py
"""
import os, time
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch
from sentence_transformers import SentenceTransformer

assert torch.cuda.is_available(), "CUDA not available"
dev = torch.cuda.get_device_name(0)
torch.cuda.set_per_process_memory_fraction(0.35, 0)  # hard courtesy cap ~1/3 of the card

t0 = time.time()
model = SentenceTransformer("Alibaba-NLP/gte-large-en-v1.5",
                            trust_remote_code=True, device="cuda")  # fp32 on purpose
model.max_seq_length = 3072
model.eval()
print(f"loaded on {dev} in {time.time()-t0:.1f}s (fp32, max_seq_length=3072)")

short = ["FAIR data sharing practices for machine-actionable scientific posters."] * 8
t0 = time.time()
e = model.encode(short, normalize_embeddings=True)
n = float((e[0] ** 2).sum()) ** 0.5
print(f"short batch: shape={e.shape} norm={n:.4f} in {time.time()-t0:.2f}s")
assert e.shape == (8, 1024) and abs(n - 1.0) < 1e-3

# worst-case: 16 documents that all truncate at the full 3072-token window
long_doc = " ".join(["poster section content describing methods results"] * 700)  # ~4900 words
t0 = time.time()
torch.cuda.reset_peak_memory_stats(0)
e2 = model.encode([long_doc] * 16, batch_size=16, normalize_embeddings=True)
dt = time.time() - t0
peak = torch.cuda.max_memory_allocated(0) / 2**30
print(f"long batch (16 x 3072 tok): shape={e2.shape} in {dt:.1f}s  peak VRAM {peak:.2f} GiB")
print(f"=> est. full-corpus wall-clock at this rate: "
      f"{31363 * (dt/16) / 60 / 4:.0f}-{31363 * (dt/16) / 60:.0f} min "
      f"(most posters are ~1/4 this length)")
print("SMOKE TEST PASS")
