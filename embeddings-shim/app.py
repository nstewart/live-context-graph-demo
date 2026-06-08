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

import logging
import os
from typing import List, Union

from fastapi import FastAPI
from fastembed import TextEmbedding
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("embeddings-shim")

MODEL_NAME = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.environ.get("EMBED_DIM", "384"))

app = FastAPI(title="Local OpenAI-compatible embeddings", version="1.0.0")

# Lazy module-level singleton: constructing TextEmbedding downloads/loads the
# ONNX model (~130MB, ~1s warm-up), so do it once and reuse across requests.
_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


class EmbeddingsRequest(BaseModel):
    # OpenAI allows a single string or a list of strings. The SMT sends one
    # string per call (the changed column value), but we accept both.
    input: Union[str, List[str]]
    model: str | None = None
    # Accepted for OpenAI compatibility; bge-small is fixed at 384 dims so we
    # only validate, we don't truncate.
    dimensions: int | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL_NAME, "dimensions": EMBEDDING_DIM}


@app.post("/v1/embeddings")
def embeddings(req: EmbeddingsRequest) -> dict:
    texts = [req.input] if isinstance(req.input, str) else list(req.input)
    vectors = [[float(x) for x in v] for v in get_model().embed(texts)]
    data = [
        {"object": "embedding", "index": i, "embedding": vec}
        for i, vec in enumerate(vectors)
    ]
    return {
        "object": "list",
        "model": req.model or MODEL_NAME,
        "data": data,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }
