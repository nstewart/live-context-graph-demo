"""Tests for the shim's /rerank endpoint.

The cross-encoder model is replaced with a stub so these run without loading or
downloading any weights — they exercise the endpoint's contract (validation,
empty input, score alignment), not the model itself.

Run with:  cd embeddings-shim && pip install -r requirements.txt pytest && pytest
"""

import os
import sys

# app.py lives one directory up; put it on the path so `import app` works no
# matter where pytest is invoked from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import app as shim


class _StubReranker:
    """Returns a descending score per document so order is observable."""

    def rerank(self, query, documents):
        return [float(len(documents) - i) for i in range(len(documents))]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(shim, "get_reranker", lambda: _StubReranker())
    return TestClient(shim.app)


def test_returns_one_score_per_document_in_order(client):
    r = client.post("/rerank", json={"query": "veggies", "documents": ["a", "b", "c"]})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == shim.RERANK_MODEL
    assert body["scores"] == [3.0, 2.0, 1.0]  # aligned to input order


def test_empty_documents_returns_empty_scores_without_calling_model(client, monkeypatch):
    # If the model were invoked with no docs it would raise; assert it isn't.
    def _boom():
        raise AssertionError("reranker should not be called for empty documents")

    monkeypatch.setattr(shim, "get_reranker", _boom)
    r = client.post("/rerank", json={"query": "veggies", "documents": []})
    assert r.status_code == 200
    assert r.json()["scores"] == []


def test_malformed_json_is_rejected(client):
    r = client.post(
        "/rerank", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"documents": ["a"]},               # missing query
        {"query": "q"},                     # missing documents
        {"query": 5, "documents": ["a"]},   # query wrong type
        {"query": "q", "documents": "a"},   # documents wrong type
    ],
)
def test_wrong_types_return_400(client, payload):
    r = client.post("/rerank", json=payload)
    assert r.status_code == 400
