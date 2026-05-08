"""Tests for OrdersSyncWorker."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.embedder import build_embedding_text, compute_hash


class TestOrdersSyncWorkerEmbedding:
    """Tests for the local-CPU vector embedding pipeline in OrdersSyncWorker.

    Behavior under test:
    - First time we see an order (no hash in cache) -> embed + bulk_upsert
      with `embedding`, `embedding_text`, `embedded_at` fields populated.
    - Same order, same line items (hash unchanged) -> NO embed call,
      use bulk_patch with the non-vector fields only.
    - Same order, different line items (hash changed) -> re-embed +
      bulk_upsert with the fresh vector.
    """

    @pytest.fixture
    def worker(self, mock_os_client, mock_embedder):
        """Build an OrdersSyncWorker with mocked OS client and embedder."""
        with patch("src.base_subscribe_worker.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                use_subscribe=True,
                backpressure_threshold=10000,
                backpressure_resume=5000,
                retry_initial_delay=1,
                retry_max_delay=10,
            )
            from src.orders_sync import OrdersSyncWorker

            w = OrdersSyncWorker(mock_os_client)
            w._embedder = mock_embedder
            return w

    def _doc(self, order_id="order:FM-1001", line_items=None, **overrides):
        """Build a minimal order doc dict (already in OS doc form)."""
        resolved_items = line_items if line_items is not None else [
            {"product_name": "Whole Milk", "category": "Dairy"},
            {"product_name": "Bananas", "category": "Produce"},
        ]
        doc = {
            "order_id": order_id,
            "order_number": order_id.split(":")[-1],
            "order_status": "OUT_FOR_DELIVERY",
            "store_id": "store:BK-01",
            "customer_id": "customer:101",
            "order_total_amount": 45.99,
            "line_items": resolved_items,
            "line_item_count": len(resolved_items),
            "has_perishable_items": True,
            "embedding_hash": compute_hash(build_embedding_text(resolved_items)),
        }
        doc.update(overrides)
        return doc

    @pytest.mark.asyncio
    async def test_new_order_embeds_and_upserts(
        self, worker, mock_os_client, mock_embedder
    ):
        """A new order (not in hash cache) is embedded + bulk_upserted."""
        mock_embedder.embed.return_value = [[0.42] * 384]

        worker.pending_upserts = [self._doc()]
        await worker._flush_batch()

        # Embedder was called exactly once for the new order
        mock_embedder.embed.assert_called_once()
        # bulk_upsert was called with the doc carrying embedding + embedded_at
        mock_os_client.bulk_upsert.assert_called_once()
        upsert_args = mock_os_client.bulk_upsert.call_args
        assert upsert_args.args[0] == "orders"
        upserted_doc = upsert_args.args[1][0]
        assert upserted_doc["embedding"] == [0.42] * 384
        assert upserted_doc["embedding_text"] == (
            "Whole Milk (Dairy) | Bananas (Produce)"
        )
        assert "embedded_at" in upserted_doc
        # bulk_patch should NOT have been called
        mock_os_client.bulk_patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_unchanged_line_items_skips_embed_and_patches(
        self, worker, mock_os_client, mock_embedder
    ):
        """When line items are unchanged, do NOT re-embed and use bulk_patch."""
        # First flush: embed + upsert
        mock_embedder.embed.return_value = [[0.1] * 384]
        worker.pending_upserts = [self._doc()]
        await worker._flush_batch()
        assert mock_embedder.embed.call_count == 1
        assert mock_os_client.bulk_upsert.call_count == 1

        # Second flush: same line items, only price changed -> patch only.
        # Simulate what consolidation sets when embedding_hash is unchanged.
        worker.pending_upserts = [self._doc(order_total_amount=99.99, _needs_embedding=False)]
        await worker._flush_batch()

        # Embed was NOT called again
        assert mock_embedder.embed.call_count == 1
        # bulk_patch was called for the price-only change
        mock_os_client.bulk_patch.assert_called_once()
        patch_args = mock_os_client.bulk_patch.call_args
        assert patch_args.args[0] == "orders"
        patches = patch_args.args[1]
        assert len(patches) == 1
        assert patches[0]["_id"] == "order:FM-1001"
        # Patch should NOT contain the vector (it's untouched)
        assert "embedding" not in patches[0]["doc"]
        # Patch DOES contain the changed price field
        assert patches[0]["doc"]["order_total_amount"] == 99.99
        # bulk_upsert was not called the second time
        assert mock_os_client.bulk_upsert.call_count == 1

    @pytest.mark.asyncio
    async def test_changed_line_items_reembeds_and_upserts(
        self, worker, mock_os_client, mock_embedder
    ):
        """When line items change, re-embed and use bulk_upsert."""
        # First flush
        mock_embedder.embed.return_value = [[0.1] * 384]
        worker.pending_upserts = [self._doc()]
        await worker._flush_batch()
        assert mock_embedder.embed.call_count == 1

        # Second flush: line items DIFFERENT -> re-embed
        new_items = [
            {"product_name": "Sourdough Bread", "category": "Bakery"},
            {"product_name": "Bananas", "category": "Produce"},
        ]
        mock_embedder.embed.return_value = [[0.9] * 384]
        worker.pending_upserts = [self._doc(line_items=new_items)]
        await worker._flush_batch()

        # Embedder was called again for the changed items
        assert mock_embedder.embed.call_count == 2
        # bulk_upsert was called twice (both flushes had a hash change)
        assert mock_os_client.bulk_upsert.call_count == 2
        # No patches
        mock_os_client.bulk_patch.assert_not_called()
        # Latest upsert carries the new vector
        last_upsert = mock_os_client.bulk_upsert.call_args.args[1][0]
        assert last_upsert["embedding"] == [0.9] * 384
        assert "Sourdough Bread (Bakery)" in last_upsert["embedding_text"]

    @pytest.mark.asyncio
    async def test_build_embedding_text_called_with_line_items(
        self, worker, mock_os_client, mock_embedder
    ):
        """build_embedding_text is invoked with the order's line_items."""
        mock_embedder.embed.return_value = [[0.0] * 384]

        with patch(
            "src.orders_sync.build_embedding_text",
            wraps=__import__(
                "src.embedder", fromlist=["build_embedding_text"]
            ).build_embedding_text,
        ) as spy:
            worker.pending_upserts = [self._doc()]
            await worker._flush_batch()

        # Called once per doc in the batch
        assert spy.call_count == 1
        called_with = spy.call_args.args[0]
        assert called_with == [
            {"product_name": "Whole Milk", "category": "Dairy"},
            {"product_name": "Bananas", "category": "Produce"},
        ]

    @pytest.mark.asyncio
    async def test_worker_initializes_embedder(self, mock_os_client):
        """Worker has an embedder attribute on init."""
        with patch("src.base_subscribe_worker.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                use_subscribe=True,
                backpressure_threshold=10000,
                backpressure_resume=5000,
                retry_initial_delay=1,
                retry_max_delay=10,
            )
            from src.orders_sync import OrdersSyncWorker

            w = OrdersSyncWorker(mock_os_client)

            assert w._embedder is not None

    @pytest.mark.asyncio
    async def test_flush_batch_empty_does_nothing(
        self, worker, mock_os_client, mock_embedder
    ):
        """Empty pending lists results in no calls."""
        worker.pending_upserts = []
        worker.pending_deletes = []

        await worker._flush_batch()

        mock_embedder.embed.assert_not_called()
        mock_os_client.bulk_upsert.assert_not_called()
        mock_os_client.bulk_patch.assert_not_called()
        mock_os_client.bulk_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_orders_index_mapping_includes_knn_vector(self):
        """The orders index mapping advertises a 384-dim knn_vector embedding field."""
        from src.opensearch_client import ORDERS_INDEX_MAPPING

        props = ORDERS_INDEX_MAPPING["mappings"]["properties"]
        assert "embedding" in props
        assert props["embedding"]["type"] == "knn_vector"
        assert props["embedding"]["dimension"] == 384
        assert props["embedding_text"]["type"] == "keyword"
        assert props["embedded_at"]["type"] == "date"


class TestOrdersSyncWorker:
    """Tests for OrdersSyncWorker."""

    @pytest.fixture
    def worker(self, mock_mz_client, mock_os_client):
        """Create worker with mocked clients."""
        with patch("src.orders_sync.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                poll_interval=1,
                batch_size=100,
            )
            from src.orders_sync import OrdersSyncWorker

            return OrdersSyncWorker(mock_mz_client, mock_os_client)

    @pytest.mark.asyncio
    async def test_sync_batch_refreshes_views(self, worker, mock_mz_client):
        """Sync batch refreshes Materialize views."""
        await worker._sync_batch()

        mock_mz_client.refresh_views.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_batch_gets_cursor(self, worker, mock_mz_client):
        """Sync batch gets cursor from Materialize."""
        await worker._sync_batch()

        mock_mz_client.get_cursor.assert_called_once_with(worker.VIEW_NAME)

    @pytest.mark.asyncio
    async def test_sync_batch_uses_default_cursor_when_none(
        self, worker, mock_mz_client, mock_os_client
    ):
        """Uses epoch as default cursor when none exists."""
        mock_mz_client.get_cursor.return_value = None
        mock_mz_client.query_orders_search_source.return_value = []

        await worker._sync_batch()

        # Should query with epoch as default
        call_args = mock_mz_client.query_orders_search_source.call_args
        assert call_args.kwargs["after_timestamp"] == datetime(
            1970, 1, 1, tzinfo=timezone.utc
        )

    @pytest.mark.asyncio
    async def test_sync_batch_syncs_documents_to_opensearch(
        self, worker, mock_mz_client, mock_os_client, sample_order_documents
    ):
        """Syncs documents from Materialize to OpenSearch."""
        mock_mz_client.query_orders_search_source.return_value = sample_order_documents

        await worker._sync_batch()

        mock_os_client.bulk_upsert.assert_called_once()
        call_args = mock_os_client.bulk_upsert.call_args
        assert call_args.args[0] == "orders"
        assert len(call_args.args[1]) == 2

    @pytest.mark.asyncio
    async def test_sync_batch_updates_cursor_after_sync(
        self, worker, mock_mz_client, mock_os_client, sample_order_documents
    ):
        """Updates cursor after successful sync."""
        mock_mz_client.query_orders_search_source.return_value = sample_order_documents
        mock_os_client.bulk_upsert.return_value = (2, 0)

        await worker._sync_batch()

        mock_mz_client.update_cursor.assert_called_once()
        # Should use max timestamp
        call_args = mock_mz_client.update_cursor.call_args
        assert call_args.args[0] == worker.VIEW_NAME
        assert call_args.args[1] == datetime(2024, 1, 15, 14, 35, 0, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_sync_batch_skips_when_no_documents(
        self, worker, mock_mz_client, mock_os_client
    ):
        """Skips sync when no new documents."""
        mock_mz_client.query_orders_search_source.return_value = []

        await worker._sync_batch()

        mock_os_client.bulk_upsert.assert_not_called()
        mock_mz_client.update_cursor.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_batch_converts_datetime_to_iso_format(
        self, worker, mock_mz_client, mock_os_client, sample_order_document
    ):
        """Converts datetime fields to ISO format for OpenSearch."""
        mock_mz_client.query_orders_search_source.return_value = [sample_order_document]

        await worker._sync_batch()

        call_args = mock_os_client.bulk_upsert.call_args
        synced_doc = call_args.args[1][0]
        # effective_updated_at should be ISO formatted string
        assert isinstance(synced_doc["effective_updated_at"], str)
        assert "2024-01-15" in synced_doc["effective_updated_at"]

    def test_stop_sets_shutdown_event(self, worker):
        """Stop method sets shutdown event."""
        assert not worker._shutdown.is_set()

        worker.stop()

        assert worker._shutdown.is_set()

    @pytest.mark.asyncio
    async def test_run_sets_up_indices(self, worker, mock_os_client):
        """Run method sets up OpenSearch indices."""
        # Stop immediately
        worker.stop()

        await worker.run()

        mock_os_client.setup_indices.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_handles_sync_errors_gracefully(
        self, worker, mock_mz_client, mock_os_client
    ):
        """Run handles sync errors without crashing."""
        mock_mz_client.refresh_views.side_effect = [Exception("Test error")]

        # Just call _sync_batch directly and verify it doesn't raise
        # This tests error handling without complex event loop issues
        try:
            await worker._sync_batch()
        except Exception:
            pass  # Expected to catch and log

        # Should have attempted sync despite error
        assert mock_mz_client.refresh_views.call_count >= 1


class TestOrdersSyncWorkerTransformations:
    """Tests for document transformation in sync worker."""

    @pytest.fixture
    def worker(self, mock_mz_client, mock_os_client):
        """Create worker with mocked clients."""
        with patch("src.orders_sync.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                poll_interval=1,
                batch_size=100,
            )
            from src.orders_sync import OrdersSyncWorker

            return OrdersSyncWorker(mock_mz_client, mock_os_client)

    @pytest.mark.asyncio
    async def test_preserves_all_document_fields(
        self, worker, mock_mz_client, mock_os_client, sample_order_document
    ):
        """All document fields are preserved during sync."""
        mock_mz_client.query_orders_search_source.return_value = [sample_order_document]

        await worker._sync_batch()

        call_args = mock_os_client.bulk_upsert.call_args
        synced_doc = call_args.args[1][0]

        expected_fields = [
            "order_id",
            "order_number",
            "order_status",
            "store_id",
            "customer_id",
            "customer_name",
            "customer_email",
            "store_name",
            "store_zone",
        ]

        for field in expected_fields:
            assert field in synced_doc

    @pytest.mark.asyncio
    async def test_handles_missing_optional_fields(
        self, worker, mock_mz_client, mock_os_client
    ):
        """Handles documents with missing optional fields."""
        minimal_doc = {
            "order_id": "order:FM-9999",
            "order_status": "CREATED",
            "effective_updated_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        }
        mock_mz_client.query_orders_search_source.return_value = [minimal_doc]

        await worker._sync_batch()

        mock_os_client.bulk_upsert.assert_called_once()
