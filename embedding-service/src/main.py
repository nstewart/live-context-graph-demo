"""OpenAI-compatible embedding service.

A thin HTTP facade over the same local `fastembed` model the rest of the
stack uses (`BAAI/bge-small-en-v1.5`, 384 dims). It speaks OpenAI's
``POST /v1/embeddings`` request/response shape so the Kafka Connect
embedding SMT (and the API's query path) can call it as if it were OpenAI.

The `model` field in the request and any `Authorization` bearer token are
ignored — this facade always serves bge-small/384. No OpenAI calls, no cost.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, Union

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("embedding-service")
logging.basicConfig(level=logging.INFO)

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

app = FastAPI(title="Embedding Service", version="1.0.0")


# --- Lazy model singleton --------------------------------------------------

_model = None


def get_model():
    """Return the lazily constructed shared TextEmbedding instance.

    Constructing fastembed's ``TextEmbedding`` loads the ONNX model, which is
    expensive, so we do it once on first use and reuse it across requests.
    """
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        logger.info("Loading embedding model: %s", MODEL_NAME)
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def _embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = get_model()
    return [[float(x) for x in v] for v in model.embed(texts)]


# --- OpenAI-compatible request/response models ------------------------------


class EmbeddingsRequest(BaseModel):
    # OpenAI accepts a single string or a list of strings. We ignore the
    # token-array form (list[list[int]]) since callers here send text.
    input: Union[str, list[str]]
    model: Optional[str] = None
    encoding_format: Optional[str] = None
    dimensions: Optional[int] = None
    user: Optional[str] = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": MODEL_NAME, "dimension": EMBEDDING_DIM}


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> JSONResponse:
    # Parse the body ourselves rather than relying on FastAPI's content-type
    # -gated model binding: various HTTP clients (incl. the Kafka Connect SMT's
    # java.net.http client) send a Content-Type that FastAPI won't treat as
    # JSON, which would otherwise yield a spurious 422. Real OpenAI accepts the
    # body regardless of Content-Type, so we do too.
    raw = await request.body()
    if not raw:
        return JSONResponse(status_code=400, content={"error": "empty request body"})
    try:
        payload = json.loads(raw)
        req = EmbeddingsRequest.model_validate(payload)
    except Exception as e:
        logger.warning(
            "Bad embeddings request (content-type=%r, %d bytes): %s",
            request.headers.get("content-type"), len(raw), e,
        )
        return JSONResponse(status_code=400, content={"error": f"invalid request body: {e}"})

    texts = [req.input] if isinstance(req.input, str) else list(req.input)

    # Offload the CPU-bound embed call so the event loop stays responsive.
    vectors = await asyncio.to_thread(_embed, texts)

    data = [
        {"object": "embedding", "index": i, "embedding": vec}
        for i, vec in enumerate(vectors)
    ]
    # Rough token estimate (whitespace words) — the SMT ignores usage, but we
    # populate it for OpenAI-shape compatibility.
    approx_tokens = sum(len(t.split()) for t in texts)
    return JSONResponse(content={
        "object": "list",
        "data": data,
        "model": req.model or MODEL_NAME,
        "usage": {"prompt_tokens": approx_tokens, "total_tokens": approx_tokens},
    })
