-- 070_order_lines_views.sql
-- Migration: Create materialized views for order lines (three-tier hierarchy)
-- Phase 1, Issue #3: Create Materialized Views for Order Lines

-- =============================================================================
-- Tier 1: Base view for order lines (non-materialized for flexibility)
-- Note: perishable_flag is NOT stored here - it is derived from products in Tier 2
-- =============================================================================
CREATE OR REPLACE VIEW order_lines_base AS
SELECT
    subject_id AS line_id,
    MAX(CASE WHEN predicate = 'line_of_order' THEN object_value END) AS order_id,
    MAX(CASE WHEN predicate = 'line_product' THEN object_value END) AS product_id,
    MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT AS quantity,
    MAX(CASE WHEN predicate = 'order_line_unit_price' THEN object_value END)::DECIMAL(10,2) AS unit_price,
    -- Calculate line_amount from quantity * unit_price (derived, not stored)
    -- This matches Materialize behavior so totals update when quantity changes
    (MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT
     * MAX(CASE WHEN predicate = 'order_line_unit_price' THEN object_value END)::DECIMAL(10,2))::DECIMAL(10,2) AS line_amount,
    MAX(CASE WHEN predicate = 'line_sequence' THEN object_value END)::INT AS line_sequence,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'orderline:%'
GROUP BY subject_id;

-- =============================================================================
-- Tier 2: Flattened order lines with product enrichment
-- This view will be materialized in Materialize for fast queries
-- perishable_flag is DERIVED from products_flat.perishable (not stored on order line)
-- =============================================================================
CREATE OR REPLACE VIEW order_lines_flat AS
SELECT
    ol.line_id,
    ol.order_id,
    ol.product_id,
    ol.quantity,
    ol.unit_price,
    ol.line_amount,
    ol.line_sequence,
    p.perishable AS perishable_flag,  -- Derived from product
    p.product_name,
    p.category,
    p.unit_price AS current_product_price,
    p.unit_weight_grams,
    GREATEST(ol.effective_updated_at, p.effective_updated_at) AS effective_updated_at
FROM order_lines_base ol
LEFT JOIN products_flat p ON p.product_id = ol.product_id;

-- =============================================================================
-- Tier 3: Orders with aggregated line items (JSONB)
-- This view provides orders with nested line items for UI display
-- =============================================================================
CREATE OR REPLACE VIEW orders_with_lines AS
SELECT
    o.*,
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
                'perishable_flag', ol.perishable_flag
            ) ORDER BY ol.line_sequence
        ) FILTER (WHERE ol.line_id IS NOT NULL),
        '[]'::jsonb
    ) AS line_items,
    COUNT(ol.line_id) AS line_item_count,
    SUM(ol.line_amount) AS computed_total,
    BOOL_OR(ol.perishable_flag) AS has_perishable_items
FROM orders_flat o
LEFT JOIN order_lines_flat ol ON ol.order_id = o.order_id
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
-- Create indexes on order_lines_flat for performance
-- =============================================================================
-- Note: In PostgreSQL these are just recommendations
-- In Materialize, indexes will be created explicitly

COMMENT ON VIEW order_lines_base IS 'Base view for order lines - intermediate transformation';
COMMENT ON VIEW order_lines_flat IS 'Flattened order lines with product enrichment - ready for materialization';
COMMENT ON VIEW orders_with_lines IS 'Orders with aggregated line items as JSONB - UI-ready format';

-- Insert migration record
INSERT INTO schema_migrations (version) VALUES ('070_order_lines_views')
ON CONFLICT (version) DO NOTHING;
