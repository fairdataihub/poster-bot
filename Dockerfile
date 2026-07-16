# posterbot API image (CPU). Query embedding (gte-large-en-v1.5) runs on CPU so
# the laptop GPU is reserved entirely for the chat LLM (ollama). The model is
# baked in at build time so the container runs fully offline at the venue.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# CPU-only torch is ~5x smaller than the CUDA build and is all we need here.
# Versions pinned to match the corpus embeddings (must be identical for cosine KNN).
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 \
 && pip install \
      sentence-transformers==3.4.1 \
      transformers==4.57.1 \
      einops \
      "psycopg2-binary==2.9.10" \
      "fastapi>=0.115,<0.120" \
      "uvicorn[standard]>=0.34,<0.52" \
      httpx orjson

# Pre-download the embedding model + its trust_remote_code implementation so the
# running container needs no network (venue wifi is unreliable).
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('Alibaba-NLP/gte-large-en-v1.5', trust_remote_code=True, device='cpu')"

COPY app/ /app/

ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    POSTERBOT_LOG_DIR=/app/logs \
    POSTERBOT_EMBED_THREADS=4

EXPOSE 8722
# bind 0.0.0.0 INSIDE the container only; compose publishes to 127.0.0.1 on the host
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8722"]
