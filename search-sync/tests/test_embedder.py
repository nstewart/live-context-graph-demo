"""Tests for the embedder module.

Covers:
- build_embedding_text(line_items): formats line items into a single embedding string
- compute_hash(text): deterministic MD5 hex string
- Embedder.embed(texts): wraps fastembed TextEmbedding (mocked here)
"""

import hashlib
from unittest.mock import MagicMock, patch

import pytest


class TestBuildEmbeddingText:
    """Tests for build_embedding_text()."""

    def test_returns_empty_string_for_empty_list(self):
        """Empty line items list returns empty string."""
        from src.embedder import build_embedding_text

        assert build_embedding_text([]) == ""

    def test_formats_single_line_item(self):
        """Single line item is formatted as 'name (category)'."""
        from src.embedder import build_embedding_text

        line_items = [{"product_name": "Whole Milk", "category": "Dairy"}]
        assert build_embedding_text(line_items) == "Whole Milk (Dairy)"

    def test_joins_multiple_line_items_with_pipe(self):
        """Multiple items joined by ' | '."""
        from src.embedder import build_embedding_text

        line_items = [
            {"product_name": "Whole Milk", "category": "Dairy"},
            {"product_name": "Sourdough Bread", "category": "Bakery"},
            {"product_name": "Bananas", "category": "Produce"},
        ]
        result = build_embedding_text(line_items)
        assert (
            result
            == "Whole Milk (Dairy) | Sourdough Bread (Bakery) | Bananas (Produce)"
        )

    def test_skips_items_without_product_name(self):
        """Line items without product_name are skipped."""
        from src.embedder import build_embedding_text

        line_items = [
            {"product_name": "Whole Milk", "category": "Dairy"},
            {"category": "Bakery"},  # missing product_name
            {"product_name": "Bananas", "category": "Produce"},
        ]
        result = build_embedding_text(line_items)
        assert result == "Whole Milk (Dairy) | Bananas (Produce)"

    def test_handles_missing_category(self):
        """Missing category becomes empty string in parentheses."""
        from src.embedder import build_embedding_text

        line_items = [{"product_name": "Mystery Item"}]
        assert build_embedding_text(line_items) == "Mystery Item ()"


class TestComputeHash:
    """Tests for compute_hash()."""

    def test_returns_md5_hex_string(self):
        """Returns 32-character hex MD5 string."""
        from src.embedder import compute_hash

        result = compute_hash("hello world")
        assert isinstance(result, str)
        assert len(result) == 32
        # All chars must be lowercase hex
        assert all(c in "0123456789abcdef" for c in result)

    def test_is_deterministic(self):
        """Same input produces same hash."""
        from src.embedder import compute_hash

        text = "Whole Milk (Dairy) | Bananas (Produce)"
        assert compute_hash(text) == compute_hash(text)

    def test_matches_md5_of_input(self):
        """Hash matches the MD5 hex of the UTF-8 encoded input."""
        from src.embedder import compute_hash

        text = "the quick brown fox"
        expected = hashlib.md5(text.encode()).hexdigest()
        assert compute_hash(text) == expected

    def test_different_inputs_produce_different_hashes(self):
        """Different inputs produce different hashes."""
        from src.embedder import compute_hash

        assert compute_hash("foo") != compute_hash("bar")

    def test_handles_empty_string(self):
        """Empty string produces a valid MD5 hash."""
        from src.embedder import compute_hash

        result = compute_hash("")
        assert result == hashlib.md5(b"").hexdigest()


class TestEmbedder:
    """Tests for Embedder class."""

    def test_embed_empty_list_returns_empty_list(self):
        """Embedding an empty list returns []."""
        # Reset module-level model cache so we don't accidentally instantiate fastembed
        with patch("src.embedder.TextEmbedding") as mock_cls:
            import src.embedder as embedder_mod

            embedder_mod._model = None  # reset cache

            embedder = embedder_mod.Embedder()
            result = embedder.embed([])
            assert result == []
            # Model should not be loaded for empty input
            mock_cls.assert_not_called()

    def test_embed_returns_list_of_lists_of_floats(self):
        """Embedding returns list[list[float]] with correct dim."""
        with patch("src.embedder.TextEmbedding") as mock_cls:
            import src.embedder as embedder_mod

            embedder_mod._model = None

            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.embed.return_value = iter(
                [[0.1] * 384, [0.2] * 384]
            )

            embedder = embedder_mod.Embedder()
            vectors = embedder.embed(["text one", "text two"])

            assert isinstance(vectors, list)
            assert len(vectors) == 2
            assert all(isinstance(v, list) for v in vectors)
            assert all(len(v) == 384 for v in vectors)
            assert all(isinstance(x, float) for x in vectors[0])

    def test_embed_uses_fastembed_text_embedding(self):
        """Embedder calls TextEmbedding under the hood."""
        with patch("src.embedder.TextEmbedding") as mock_cls:
            import src.embedder as embedder_mod

            embedder_mod._model = None

            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            mock_instance.embed.return_value = iter([[0.5] * 384])

            embedder = embedder_mod.Embedder()
            embedder.embed(["the quick brown fox"])

            # Model should be constructed lazily with bge-small-en-v1.5
            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args.kwargs
            assert call_kwargs.get("model_name") == "BAAI/bge-small-en-v1.5"
            # And .embed() should have been called with the texts
            mock_instance.embed.assert_called_once_with(["the quick brown fox"])

    def test_embedding_dim_constant_is_384(self):
        """The EMBEDDING_DIM constant is 384."""
        from src.embedder import EMBEDDING_DIM

        assert EMBEDDING_DIM == 384

    def test_model_name_constant_is_bge_small(self):
        """The MODEL_NAME constant is the BAAI bge-small-en-v1.5 model."""
        from src.embedder import MODEL_NAME

        assert MODEL_NAME == "BAAI/bge-small-en-v1.5"

    def test_get_model_caches_instance(self):
        """get_model() returns the same instance across calls."""
        with patch("src.embedder.TextEmbedding") as mock_cls:
            import src.embedder as embedder_mod

            embedder_mod._model = None
            mock_cls.return_value = MagicMock()

            m1 = embedder_mod.get_model()
            m2 = embedder_mod.get_model()
            assert m1 is m2
            # Constructed exactly once
            assert mock_cls.call_count == 1
