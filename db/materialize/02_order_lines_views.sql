-- Materialize Views for Order Lines (Three-Tier Architecture)
-- Phase 1, Issue #3: Create Materialized Views for Order Lines
--
-- Run this after Materialize starts and 01_init_mz.sql completes:
-- psql -h localhost -p 6875 -U materialize -f 02_order_lines_views.sql

-- =============================================================================
-- Regular Views for Intermediate Transformations (no cluster specified)
-- =============================================================================

-- Tier 1: Base view for order lines
CREATE VIEW IF NOT EXISTS order_lines_base AS
SELECT
    subject_id AS line_id,
    MAX(CASE WHEN predicate = 'line_of_order' THEN object_value END) AS order_id,
    MAX(CASE WHEN predicate = 'line_product' THEN object_value END) AS product_id,
    MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT AS quantity,
    MAX(CASE WHEN predicate = 'order_line_unit_price' THEN object_value END)::DECIMAL(10,2) AS unit_price,
    MAX(CASE WHEN predicate = 'line_amount' THEN object_value END)::DECIMAL(10,2) AS line_amount,
    MAX(CASE WHEN predicate = 'line_sequence' THEN object_value END)::INT AS line_sequence,
    MAX(CASE WHEN predicate = 'perishable_flag' THEN object_value END)::BOOLEAN AS perishable_flag,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'orderline:%'
GROUP BY subject_id;

-- Products flat view (if not already created)
CREATE VIEW IF NOT EXISTS products_flat AS
SELECT
    subject_id AS product_id,
    MAX(CASE WHEN predicate = 'product_name' THEN object_value END) AS product_name,
    MAX(CASE WHEN predicate = 'category' THEN object_value END) AS category,
    MAX(CASE WHEN predicate = 'unit_price' THEN object_value END)::DECIMAL(10,2) AS unit_price,
    MAX(CASE WHEN predicate = 'perishable' THEN object_value END)::BOOLEAN AS perishable,
    MAX(CASE WHEN predicate = 'unit_weight_grams' THEN object_value END)::INT AS unit_weight_grams,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'product:%'
GROUP BY subject_id;

-- =============================================================================
-- Materialized Views IN CLUSTER compute
-- These persist results for serving
-- =============================================================================

-- Tier 2: Flattened order lines with product enrichment and pricing
CREATE MATERIALIZED VIEW IF NOT EXISTS order_lines_flat_mv IN CLUSTER compute AS
SELECT
    ol.line_id,
    ol.order_id,
    ol.product_id,
    ol.quantity,
    ol.unit_price,
    ol.line_amount,
    ol.line_sequence,
    ol.perishable_flag,
    p.product_name,
    p.category,
    p.unit_price AS current_product_price,
    p.unit_weight_grams,
    ol.effective_updated_at,
    -- Pricing columns for UI display
    p.unit_price AS base_price,  -- Static catalog price (base)
    COALESCE(inv.live_price, p.unit_price) AS live_price  -- Dynamic price or fallback to base
FROM order_lines_base ol
LEFT JOIN products_flat p ON p.product_id = ol.product_id
LEFT JOIN (
    -- Get order's store_id to join with inventory pricing
    SELECT
        subject_id AS order_id,
        MAX(CASE WHEN predicate = 'store_id' THEN object_value END) AS store_id
    FROM triples
    WHERE subject_id LIKE 'order:%'
    GROUP BY subject_id
) o ON o.order_id = ol.order_id
LEFT JOIN inventory_items_with_dynamic_pricing_mv inv
    ON inv.store_id = o.store_id AND inv.product_id = ol.product_id;

-- Tier 3: Orders with aggregated line items (JSONB)
CREATE MATERIALIZED VIEW IF NOT EXISTS orders_with_lines_mv IN CLUSTER compute AS
SELECT
    o.order_id,
    o.order_number,
    o.order_status,
    o.store_id,
    o.customer_id,
    o.delivery_window_start,
    o.delivery_window_end,
    o.order_total_amount,
    o.effective_updated_at,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'line_id', ol.line_id,
                'product_id', ol.product_id,
                'product_name', ol.product_name,
                'category', ol.category,
                'quantity', ol.quantity,
                'unit_price', ol.unit_price,
                'line_amount', ol.line_amount,
                'line_sequence', ol.line_sequence,
                'perishable_flag', ol.perishable_flag,
                'unit_weight_grams', ol.unit_weight_grams
            ) ORDER BY ol.line_sequence
        ) FILTER (WHERE ol.line_id IS NOT NULL),
        '[]'::jsonb
    ) AS line_items,
    COUNT(ol.line_id) AS line_item_count,
    SUM(ol.line_amount) AS computed_total,
    BOOL_OR(ol.perishable_flag) AS has_perishable_items,
    SUM(ol.quantity * COALESCE(ol.unit_weight_grams, 0)::DECIMAL / 1000.0) AS total_weight_kg
FROM orders_flat_mv o
LEFT JOIN order_lines_flat_mv ol ON ol.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.order_status,
    o.store_id,
    o.customer_id,
    o.delivery_window_start,
    o.delivery_window_end,
    o.order_total_amount,
    o.effective_updated_at;

-- =============================================================================
-- Indexes IN CLUSTER serving ON materialized views
-- These enable low-latency queries
-- =============================================================================

-- Primary access pattern: query line items by order
CREATE INDEX IF NOT EXISTS order_lines_order_id_idx IN CLUSTER serving
    ON order_lines_flat_mv (order_id);

-- Secondary access pattern: query line items by product (analytics)
CREATE INDEX IF NOT EXISTS order_lines_product_id_idx IN CLUSTER serving
    ON order_lines_flat_mv (product_id);

-- Composite index for efficient sorting within orders
CREATE INDEX IF NOT EXISTS order_lines_order_sequence_idx IN CLUSTER serving
    ON order_lines_flat_mv (order_id, line_sequence);

-- Primary access pattern for orders with lines
CREATE INDEX IF NOT EXISTS orders_with_lines_idx IN CLUSTER serving
    ON orders_with_lines_mv (order_id);

-- Query by status with timestamp ordering
CREATE INDEX IF NOT EXISTS orders_with_lines_status_idx IN CLUSTER serving
    ON orders_with_lines_mv (order_status, effective_updated_at DESC);
