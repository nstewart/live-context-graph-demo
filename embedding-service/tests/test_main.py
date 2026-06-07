"""Smoke tests for the OpenAI-compatible embedding service.

The fastembed model is mocked so these run without downloading weights.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

import src.main as main
from src.main import app, EMBEDDING_DIM

client = TestClient(app)


def _fake_embed(texts):
    # One deterministic EMBEDDING_DIM-length vector per input.
    return [[0.1] * EMBEDDING_DIM for _ in texts]


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["dimension"] == EMBEDDING_DIM


def test_embeddings_single_string():
    with patch.object(main, "_embed", side_effect=_fake_embed):
        resp = client.post("/v1/embeddings", json={"input": "apple (produce)", "model": "x"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "list"
    assert len(body["data"]) == 1
    assert body["data"][0]["index"] == 0
    assert len(body["data"][0]["embedding"]) == EMBEDDING_DIM


def test_embeddings_list_input_preserves_order():
    with patch.object(main, "_embed", side_effect=_fake_embed):
        resp = client.post(
            "/v1/embeddings",
            json={"input": ["a", "b", "c"], "model": "x"},
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [d["index"] for d in data] == [0, 1, 2]
    assert all(len(d["embedding"]) == EMBEDDING_DIM for d in data)
