"""OpenAI-compatible embeddings endpoint backed by a local fastembed model.

This is the "cheap local model" that the perfect-embeddings Kafka Connect SMT
calls instead of the real OpenAI API. The SMT is configured with
``transforms.embed.openai.endpoint=http://embeddings:8080/v1/embeddings`` and
hits this service once per changed text column.

It deliberately mirrors the contract exercised by perfect-embedding's
``MockEmbeddingsServer`` in its e2e test:

    POST /v1/embeddings
        request:  {"input": "<text>" | ["<text>", ...], "model": "..."}
        response: {"object": "list",
                   "model": "...",
                   "data": [{"object": "embedding", "index": 0,
                             "embedding": [<float>, ...]}]}

The model is ``BAAI/bge-small-en-v1.5`` (384-dim) — the SAME model the demo's
API uses for query-time embedding, so indexed vectors and query vectors share
a vector space. Keeping this identical is what lets us swap the old Python
search-sync worker for the Kafka/SMT path without re-indexing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("embeddings-shim")

MODEL_NAME = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.environ.get("EMBED_DIM", "384"))
# Cross-encoder reranker: jointly scores (query, document) pairs. Used by the
# API's reranked vector search as a precision second stage over the kNN recall.
RERANK_MODEL = os.environ.get("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")

app = FastAPI(title="Local OpenAI-compatible embeddings + reranker", version="1.0.0")

# Lazy module-level singletons: constructing these downloads/loads ONNX models
# (~130MB embed, ~90MB rerank), so do it once and reuse across requests.
_model: TextEmbedding | None = None
_reranker: TextCrossEncoder | None = None


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def get_reranker() -> TextCrossEncoder:
    global _reranker
    if _reranker is None:
        logger.info("Loading cross-encoder reranker: %s", RERANK_MODEL)
        _reranker = TextCrossEncoder(model_name=RERANK_MODEL)
    return _reranker


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL_NAME, "dimensions": EMBEDDING_DIM, "rerank_model": RERANK_MODEL}


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    # Parse the raw body ourselves rather than relying on FastAPI's
    # Content-Type-sensitive body binding — keeps us robust to any client
    # (the SMT's HTTP client, curl, OpenAI SDKs) regardless of headers.
    raw = await request.body()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    inp = payload.get("input")
    if inp is None:
        logger.warning(
            "Bad /v1/embeddings request: content-type=%r len=%d body=%.200r",
            request.headers.get("content-type"),
            len(raw),
            raw,
        )
        return JSONResponse(status_code=400, content={"error": "missing 'input'"})

    texts = [inp] if isinstance(inp, str) else list(inp)
    vectors = [[float(x) for x in v] for v in get_model().embed(texts)]
    data = [
        {"object": "embedding", "index": i, "embedding": vec}
        for i, vec in enumerate(vectors)
    ]
    return {
        "object": "list",
        "model": payload.get("model") or MODEL_NAME,
        "data": data,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@app.post("/rerank")
async def rerank(request: Request):
    """Cross-encoder rerank. Returns one relevance score per document, aligned
    to input order, so the caller can reorder its candidate set.

        request:  {"query": "<text>", "documents": ["<doc>", ...]}
        response: {"model": "...", "scores": [<float>, ...]}
    """
    raw = await request.body()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}

    query = payload.get("query")
    documents = payload.get("documents")
    if not isinstance(query, str) or not isinstance(documents, list):
        return JSONResponse(
            status_code=400,
            content={"error": "expected {'query': str, 'documents': [str, ...]}"},
        )
    if not documents:
        return {"model": RERANK_MODEL, "scores": []}

    # rerank() is synchronous and CPU-bound — run it off the event loop so a
    # single inference can't block other requests (mirrors the embed path).
    raw_scores = await asyncio.to_thread(get_reranker().rerank, query, documents)
    scores = [float(s) for s in raw_scores]
    return {"model": RERANK_MODEL, "scores": scores}
