"""Materialize client for querying views using psycopg."""

from datetime import datetime
from typing import Optional

import psycopg

from src.config import get_settings


class MaterializeClient:
    """Client for querying Materialize views."""

    def __init__(self):
        settings = get_settings()
        self._conninfo = settings.mz_conninfo

    async def close(self):
        """Close resources (no-op for psycopg sync connections)."""
        pass

    async def query_orders_search_source(
        self,
        after_timestamp: datetime,
        batch_size: int = 100,
    ) -> list[dict]:
        """
        Query orders_search_source for changed documents.

        Args:
            after_timestamp: Only return rows updated after this time
            batch_size: Maximum rows to return

        Returns:
            List of order documents ready for indexing
        """
        with psycopg.connect(self._conninfo) as conn:
            with conn.cursor() as cur:
                # Use the serving cluster for indexed queries
                cur.execute("SET CLUSTER = serving")
                # Note: Materialize requires LIMIT to be a constant expression,
                # so we embed the batch_size directly in the query string
                cur.execute(
                    f"""
                    SELECT
                        order_id,
                        order_number,
                        order_status,
                        store_id,
                        customer_id,
                        delivery_window_start,
                        delivery_window_end,
                        order_total_amount,
                        customer_name,
                        customer_email,
                        customer_address,
                        store_name,
                        store_zone,
                        store_address,
                        assigned_courier_id,
                        delivery_task_status,
                        delivery_eta,
                        effective_updated_at
                    FROM orders_search_source
                    WHERE effective_updated_at > %s
                    ORDER BY effective_updated_at
                    LIMIT {int(batch_size)}
                    """,
                    (after_timestamp,),
                )
                rows = cur.fetchall()

        return [
            {
                "order_id": row[0],
                "order_number": row[1],
                "order_status": row[2],
                "store_id": row[3],
                "customer_id": row[4],
                "delivery_window_start": row[5],
                "delivery_window_end": row[6],
                "order_total_amount": float(row[7]) if row[7] else None,
                "customer_name": row[8],
                "customer_email": row[9],
                "customer_address": row[10],
                "store_name": row[11],
                "store_zone": row[12],
                "store_address": row[13],
                "assigned_courier_id": row[14],
                "delivery_task_status": row[15],
                "delivery_eta": row[16],
                "effective_updated_at": row[17],
            }
            for row in rows
        ]

    async def get_cursor(self, view_name: str) -> Optional[datetime]:
        """Get the last synced timestamp for a view.

        Note: Materialize doesn't support tables with primary keys, so we don't
        persist cursors. The sync worker will re-sync all recent data each time.
        """
        # Return None to always do a full sync - Materialize views handle this efficiently
        return None

    async def update_cursor(self, view_name: str, timestamp: datetime):
        """Update the cursor for a view.

        Note: Materialize doesn't support tables with primary keys, so we don't
        persist cursors. This is a no-op.
        """
        pass  # No-op - cursor tracking not supported in Materialize

    async def refresh_views(self):
        """Trigger refresh of views.

        Note: In real Materialize, views are automatically maintained via
        streaming updates from the source. No manual refresh is needed.
        """
        pass  # No-op - Materialize maintains views automatically
