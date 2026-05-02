"""Local CPU vector embedding for orders.

Uses the `fastembed` ONNX runtime with the small BGE model
(`BAAI/bge-small-en-v1.5`, 384 dims, ~130MB) to embed an order's
line items into a `knn_vector` for OpenSearch.

Design:
- ``build_embedding_text`` builds a deterministic text representation
  of an order's line items: ``"name (category) | name (category) | ..."``.
- ``compute_hash`` returns a stable MD5 hex digest used to dedup
  re-embedding work — only re-embed when the embedding text changes.
- ``Embedder.embed`` wraps fastembed's ``TextEmbedding`` and returns
  ``list[list[float]]`` (one 384-dim vector per input string).

The model is lazily constructed on first use so importing this module
is cheap (e.g., for tests), and the model is cached at module level
to amortize the ~1s warm-up across many calls.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Public constants
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384


# Resilient import: in test environments we may not have fastembed installed.
# We expose `TextEmbedding` as a module-level attribute so tests can
# `patch("src.embedder.TextEmbedding")` regardless of whether the real
# package is available.
try:
    from fastembed import TextEmbedding  # type: ignore
except ImportError:  # pragma: no cover - exercised only without fastembed
    TextEmbedding = None  # type: ignore[assignment]


# Module-level cached model instance.
_model: Optional["TextEmbedding"] = None  # type: ignore[name-defined]


def get_model():
    """Return the (lazily constructed) shared TextEmbedding instance.

    The model is constructed once and reused. Constructing fastembed's
    ``TextEmbedding`` downloads/loads the ONNX model which is expensive,
    so we do it lazily on first call.
    """
    global _model
    if _model is None:
        if TextEmbedding is None:
            raise RuntimeError(
                "fastembed is not installed. Add `fastembed` to requirements.txt "
                "or install it with `pip install fastembed`."
            )
        logger.info(f"Loading embedding model: {MODEL_NAME}")
        _model = TextEmbedding(model_name=MODEL_NAME)
    return _model


def build_embedding_text(line_items: list[dict]) -> str:
    """Build the canonical text representation of an order's line items.

    Format: ``"<product_name> (<category>) | <product_name> (<category>) | ..."``.
    Items missing ``product_name`` are skipped. Missing ``category`` becomes
    an empty string in the parentheses.

    Args:
        line_items: List of line item dicts from the order document.

    Returns:
        A single string suitable for hashing and embedding. Empty list
        returns the empty string.
    """
    parts = [
        f"{li.get('product_name', '')} ({li.get('category', '')})"
        for li in line_items
        if li.get("product_name")
    ]
    return " | ".join(parts)


def compute_hash(text: str) -> str:
    """Return a deterministic MD5 hex digest of ``text``.

    Used to detect when an order's embedding-relevant fields change —
    if the hash is unchanged, we can skip re-embedding (price/qty
    changes don't affect the hash).
    """
    return hashlib.md5(text.encode()).hexdigest()


class Embedder:
    """Thin wrapper around fastembed's ``TextEmbedding``.

    Hides the lazy-loading / iterator behavior so callers get a plain
    ``list[list[float]]`` back.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` into 384-dim float vectors.

        Args:
            texts: List of strings to embed. Empty list returns ``[]``
                without loading the model.

        Returns:
            One ``list[float]`` per input string, in input order. Each
            vector has ``EMBEDDING_DIM`` (384) elements.
        """
        if not texts:
            return []
        model = get_model()
        return [list(v) for v in model.embed(texts)]
