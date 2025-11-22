-- 040_views_search_source.sql
-- Search projection views for OpenSearch sync

-- Orders Search Source View
-- Enriched order data optimized for search indexing
CREATE OR REPLACE VIEW orders_search_source AS
SELECT
    ofm.order_id,
    ofm.order_number,
    ofm.order_status,
    ofm.store_id,
    ofm.customer_id,
    ofm.delivery_window_start,
    ofm.delivery_window_end,
    ofm.order_total_amount,
    -- Customer details
    MAX(CASE WHEN c.predicate = 'customer_name' THEN c.object_value END) AS customer_name,
    MAX(CASE WHEN c.predicate = 'customer_email' THEN c.object_value END) AS customer_email,
    MAX(CASE WHEN c.predicate = 'customer_address' THEN c.object_value END) AS customer_address,
    -- Store details
    MAX(CASE WHEN s.predicate = 'store_name' THEN s.object_value END) AS store_name,
    MAX(CASE WHEN s.predicate = 'store_zone' THEN s.object_value END) AS store_zone,
    MAX(CASE WHEN s.predicate = 'store_address' THEN s.object_value END) AS store_address,
    -- Order lines (aggregated)
    COALESCE(
        (
            SELECT json_agg(line_data)
            FROM (
                SELECT json_build_object(
                    'line_id', ol_lines.subject_id,
                    'product_id', MAX(CASE WHEN ol_lines.predicate = 'line_product' THEN ol_lines.object_value END),
                    'quantity', MAX(CASE WHEN ol_lines.predicate = 'quantity' THEN ol_lines.object_value END)::INT,
                    'line_amount', MAX(CASE WHEN ol_lines.predicate = 'line_amount' THEN ol_lines.object_value END)::DECIMAL(10,2)
                ) AS line_data
                FROM triples ol_ref
                JOIN triples ol_lines ON ol_lines.subject_id = ol_ref.subject_id
                WHERE ol_ref.predicate = 'line_of_order'
                    AND ol_ref.object_value = ofm.order_id
                GROUP BY ol_lines.subject_id
            ) subq
        ),
        '[]'::json
    ) AS order_lines,
    -- Delivery task info
    MAX(CASE WHEN dt.predicate = 'assigned_to' THEN dt.object_value END) AS assigned_courier_id,
    MAX(CASE WHEN dt.predicate = 'task_status' THEN dt.object_value END) AS delivery_task_status,
    MAX(CASE WHEN dt.predicate = 'eta' THEN dt.object_value END) AS delivery_eta,
    -- Timestamp for incremental sync
    GREATEST(
        ofm.effective_updated_at,
        MAX(c.updated_at),
        MAX(s.updated_at)
    ) AS effective_updated_at
FROM orders_flat ofm
-- Join customer triples
LEFT JOIN triples c ON c.subject_id = ofm.customer_id
-- Join store triples
LEFT JOIN triples s ON s.subject_id = ofm.store_id
-- Join delivery task (via task_of_order)
LEFT JOIN triples dt_ref ON dt_ref.predicate = 'task_of_order' AND dt_ref.object_value = ofm.order_id
LEFT JOIN triples dt ON dt.subject_id = dt_ref.subject_id
GROUP BY
    ofm.order_id,
    ofm.order_number,
    ofm.order_status,
    ofm.store_id,
    ofm.customer_id,
    ofm.delivery_window_start,
    ofm.delivery_window_end,
    ofm.order_total_amount,
    ofm.effective_updated_at;

-- Sync cursor tracking table
CREATE TABLE IF NOT EXISTS sync_cursors (
    view_name TEXT PRIMARY KEY,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT '1970-01-01'::TIMESTAMPTZ,
    last_synced_id TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Initialize cursor for orders
INSERT INTO sync_cursors (view_name) VALUES ('orders_search_source')
ON CONFLICT (view_name) DO NOTHING;

-- Insert migration record
INSERT INTO schema_migrations (version) VALUES ('040_views_search_source')
ON CONFLICT (version) DO NOTHING;
