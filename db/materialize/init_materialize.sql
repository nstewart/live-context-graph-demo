-- Materialize Initialization Script (Three-Tier Architecture)
-- Sets up PostgreSQL source connection, clusters, views, and indexes
-- Run this after Materialize starts: psql -h localhost -p 6875 -U materialize -f init_materialize.sql
--
-- Architecture:
--   ingest cluster  -> Sources (PostgreSQL logical replication)
--   compute cluster -> Materialized views (persist transformation results)
--   serving cluster -> Indexes (serve queries with low latency)
--
-- Pattern:
--   - Regular views for intermediate transformations (no cluster)
--   - Materialized views IN CLUSTER compute for "topmost" views that serve results
--   - Indexes IN CLUSTER serving ON materialized views

-- =============================================================================
-- Create secret for PostgreSQL password
-- =============================================================================
CREATE SECRET IF NOT EXISTS pgpass AS 'postgres';

-- =============================================================================
-- Create connection to PostgreSQL
-- =============================================================================
CREATE CONNECTION IF NOT EXISTS pg_connection TO POSTGRES (
    HOST 'db',
    PORT 5432,
    USER 'postgres',
    PASSWORD SECRET pgpass,
    DATABASE 'freshmart'
);

-- =============================================================================
-- Create source from PostgreSQL in ingest cluster
-- (requires publication 'mz_source' to exist in PostgreSQL)
-- =============================================================================
CREATE SOURCE IF NOT EXISTS pg_source
    IN CLUSTER ingest
    FROM POSTGRES CONNECTION pg_connection (PUBLICATION 'mz_source')
    FOR ALL TABLES;

-- =============================================================================
-- Regular Views for Intermediate Transformations
-- These are logical definitions - no cluster specified
-- =============================================================================
CREATE VIEW IF NOT EXISTS customers_flat AS
SELECT
    subject_id AS customer_id,
    MAX(CASE WHEN predicate = 'customer_name' THEN object_value END) AS customer_name,
    MAX(CASE WHEN predicate = 'customer_email' THEN object_value END) AS customer_email,
    MAX(CASE WHEN predicate = 'customer_address' THEN object_value END) AS customer_address,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'customer:%'
GROUP BY subject_id;

CREATE VIEW IF NOT EXISTS stores_flat AS
SELECT
    subject_id AS store_id,
    MAX(CASE WHEN predicate = 'store_name' THEN object_value END) AS store_name,
    MAX(CASE WHEN predicate = 'store_zone' THEN object_value END) AS store_zone,
    MAX(CASE WHEN predicate = 'store_address' THEN object_value END) AS store_address,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'store:%'
GROUP BY subject_id;

CREATE VIEW IF NOT EXISTS delivery_tasks_flat AS
SELECT
    subject_id AS task_id,
    MAX(CASE WHEN predicate = 'task_of_order' THEN object_value END) AS order_id,
    MAX(CASE WHEN predicate = 'assigned_to' THEN object_value END) AS assigned_courier_id,
    MAX(CASE WHEN predicate = 'task_status' THEN object_value END) AS task_status,
    MAX(CASE WHEN predicate = 'eta' THEN object_value END) AS eta,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'task:%'
GROUP BY subject_id;

-- =============================================================================
-- Materialized Views IN CLUSTER compute
-- These are the "topmost" views that persist results for serving
-- =============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS orders_flat_mv IN CLUSTER compute AS
SELECT
    subject_id AS order_id,
    MAX(CASE WHEN predicate = 'order_number' THEN object_value END) AS order_number,
    MAX(CASE WHEN predicate = 'order_status' THEN object_value END) AS order_status,
    MAX(CASE WHEN predicate = 'order_store' THEN object_value END) AS store_id,
    MAX(CASE WHEN predicate = 'placed_by' THEN object_value END) AS customer_id,
    MAX(CASE WHEN predicate = 'delivery_window_start' THEN object_value END) AS delivery_window_start,
    MAX(CASE WHEN predicate = 'delivery_window_end' THEN object_value END) AS delivery_window_end,
    MAX(CASE WHEN predicate = 'order_total_amount' THEN object_value END)::DECIMAL(10,2) AS order_total_amount,
    MAX(CASE WHEN predicate = 'order_created_at' THEN object_value END)::TIMESTAMPTZ AS order_created_at,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'order:%'
GROUP BY subject_id;

-- Products flat view (needed for inventory enrichment)
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

-- Materialized view with product and store enrichment for OpenSearch
-- Drop first to ensure schema updates are applied
DROP MATERIALIZED VIEW IF EXISTS store_inventory_mv CASCADE;
CREATE MATERIALIZED VIEW store_inventory_mv IN CLUSTER compute AS
SELECT
    inv.inventory_id,
    inv.store_id,
    inv.product_id,
    inv.stock_level,
    inv.replenishment_eta,
    inv.effective_updated_at,
    -- Product details
    p.product_name,
    p.category,
    p.unit_price,
    p.perishable,
    p.unit_weight_grams,
    -- Store details
    s.store_name,
    s.store_zone,
    s.store_address,
    -- Availability flags
    CASE
        WHEN inv.stock_level > 10 THEN 'IN_STOCK'
        WHEN inv.stock_level > 0 THEN 'LOW_STOCK'
        ELSE 'OUT_OF_STOCK'
    END AS availability_status,
    (inv.stock_level <= 10 AND inv.stock_level > 0) AS low_stock
FROM (
    SELECT
        subject_id AS inventory_id,
        MAX(CASE WHEN predicate = 'inventory_store' THEN object_value END) AS store_id,
        MAX(CASE WHEN predicate = 'inventory_product' THEN object_value END) AS product_id,
        MAX(CASE WHEN predicate = 'stock_level' THEN object_value END)::INT AS stock_level,
        MAX(CASE WHEN predicate = 'replenishment_eta' THEN object_value END) AS replenishment_eta,
        MAX(updated_at) AS effective_updated_at
    FROM triples
    WHERE subject_id LIKE 'inventory:%'
    GROUP BY subject_id
) inv
LEFT JOIN products_flat p ON p.product_id = inv.product_id
LEFT JOIN stores_flat s ON s.store_id = inv.store_id;

CREATE MATERIALIZED VIEW IF NOT EXISTS orders_search_source_mv IN CLUSTER compute AS
SELECT
    o.order_id,
    o.order_number,
    o.order_status,
    o.store_id,
    o.customer_id,
    o.delivery_window_start,
    o.delivery_window_end,
    o.order_total_amount,
    c.customer_name,
    c.customer_email,
    c.customer_address,
    s.store_name,
    s.store_zone,
    s.store_address,
    dt.assigned_courier_id,
    dt.task_status AS delivery_task_status,
    dt.eta AS delivery_eta,
    GREATEST(o.effective_updated_at, c.effective_updated_at, s.effective_updated_at, dt.effective_updated_at) AS effective_updated_at
FROM orders_flat_mv o
LEFT JOIN customers_flat c ON c.customer_id = o.customer_id
LEFT JOIN stores_flat s ON s.store_id = o.store_id
LEFT JOIN delivery_tasks_flat dt ON dt.order_id = o.order_id;

-- Order timestamps view for joining with tasks
CREATE VIEW IF NOT EXISTS order_timestamps AS
SELECT
    subject_id AS order_id,
    MAX(CASE WHEN predicate = 'order_created_at' THEN object_value END) AS order_created_at,
    MAX(CASE WHEN predicate = 'delivered_at' THEN object_value END) AS delivered_at
FROM triples
WHERE subject_id LIKE 'order:%'
GROUP BY subject_id;

-- Courier tasks intermediate view
CREATE VIEW IF NOT EXISTS courier_tasks_flat AS
SELECT
    t_assigned.object_value AS courier_id,
    t_task.subject_id AS task_id,
    MAX(CASE WHEN t_task.predicate = 'task_status' THEN t_task.object_value END) AS task_status,
    MAX(CASE WHEN t_task.predicate = 'task_of_order' THEN t_task.object_value END) AS order_id,
    MAX(CASE WHEN t_task.predicate = 'eta' THEN t_task.object_value END) AS eta,
    MAX(CASE WHEN t_task.predicate = 'route_sequence' THEN t_task.object_value END)::INT AS route_sequence
FROM triples t_assigned
JOIN triples t_task ON t_task.subject_id = t_assigned.subject_id
WHERE t_assigned.predicate = 'assigned_to'
    AND t_assigned.object_type = 'entity_ref'
GROUP BY t_assigned.object_value, t_task.subject_id;

-- Courier tasks with order timestamps
CREATE VIEW IF NOT EXISTS courier_tasks_with_timestamps AS
SELECT
    ct.courier_id,
    ct.task_id,
    ct.task_status,
    ct.order_id,
    ct.eta,
    ct.route_sequence,
    ot.order_created_at,
    ot.delivered_at,
    CASE
        WHEN ot.delivered_at IS NOT NULL AND ot.order_created_at IS NOT NULL
        THEN EXTRACT(EPOCH FROM (ot.delivered_at::TIMESTAMPTZ - ot.order_created_at::TIMESTAMPTZ)) / 60
        ELSE NULL
    END AS wait_time_minutes
FROM courier_tasks_flat ct
LEFT JOIN order_timestamps ot ON ot.order_id = ct.order_id;

-- Couriers flat intermediate view
CREATE VIEW IF NOT EXISTS couriers_flat AS
SELECT
    subject_id AS courier_id,
    MAX(CASE WHEN predicate = 'courier_name' THEN object_value END) AS courier_name,
    MAX(CASE WHEN predicate = 'courier_home_store' THEN object_value END) AS home_store_id,
    MAX(CASE WHEN predicate = 'vehicle_type' THEN object_value END) AS vehicle_type,
    MAX(CASE WHEN predicate = 'courier_status' THEN object_value END) AS courier_status,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'courier:%'
GROUP BY subject_id;

CREATE MATERIALIZED VIEW IF NOT EXISTS courier_schedule_mv IN CLUSTER compute AS
SELECT
    cf.courier_id,
    cf.courier_name,
    cf.home_store_id,
    cf.vehicle_type,
    cf.courier_status,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'task_id', ct.task_id,
                'task_status', ct.task_status,
                'order_id', ct.order_id,
                'eta', ct.eta,
                'wait_time_minutes', ct.wait_time_minutes,
                'order_created_at', ct.order_created_at
            )
        ) FILTER (WHERE ct.task_id IS NOT NULL),
        '[]'::jsonb
    ) AS tasks,
    cf.effective_updated_at
FROM couriers_flat cf
LEFT JOIN courier_tasks_with_timestamps ct ON ct.courier_id = cf.courier_id
GROUP BY cf.courier_id, cf.courier_name, cf.home_store_id, cf.vehicle_type, cf.courier_status, cf.effective_updated_at;

-- Materialized view for stores (for direct store queries)
CREATE MATERIALIZED VIEW IF NOT EXISTS stores_mv IN CLUSTER compute AS
SELECT
    subject_id AS store_id,
    MAX(CASE WHEN predicate = 'store_name' THEN object_value END) AS store_name,
    MAX(CASE WHEN predicate = 'store_zone' THEN object_value END) AS store_zone,
    MAX(CASE WHEN predicate = 'store_address' THEN object_value END) AS store_address,
    MAX(CASE WHEN predicate = 'store_status' THEN object_value END) AS store_status,
    MAX(CASE WHEN predicate = 'store_capacity_orders_per_hour' THEN object_value END)::INT AS store_capacity_orders_per_hour,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'store:%'
GROUP BY subject_id;

-- Materialized view for customers (for direct customer queries)
CREATE MATERIALIZED VIEW IF NOT EXISTS customers_mv IN CLUSTER compute AS
SELECT
    subject_id AS customer_id,
    MAX(CASE WHEN predicate = 'customer_name' THEN object_value END) AS customer_name,
    MAX(CASE WHEN predicate = 'customer_email' THEN object_value END) AS customer_email,
    MAX(CASE WHEN predicate = 'customer_address' THEN object_value END) AS customer_address,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'customer:%'
GROUP BY subject_id;

-- =============================================================================
-- Indexes IN CLUSTER serving ON materialized views
-- These make the materialized views queryable with low latency
-- =============================================================================
CREATE INDEX IF NOT EXISTS orders_flat_idx IN CLUSTER serving ON orders_flat_mv (order_id);
CREATE INDEX IF NOT EXISTS store_inventory_idx IN CLUSTER serving ON store_inventory_mv (inventory_id);
CREATE INDEX IF NOT EXISTS orders_search_source_idx IN CLUSTER serving ON orders_search_source_mv (order_id);
CREATE INDEX IF NOT EXISTS courier_schedule_idx IN CLUSTER serving ON courier_schedule_mv (courier_id);
CREATE INDEX IF NOT EXISTS stores_idx IN CLUSTER serving ON stores_mv (store_id);
CREATE INDEX IF NOT EXISTS customers_idx IN CLUSTER serving ON customers_mv (customer_id);

-- =============================================================================
-- Time-Series Views for Sparklines and Trend Analysis
-- Uses mz_now() temporal filters to maintain a rolling 30-minute window
-- =============================================================================

-- Orders bucketed into 1-minute time windows (rolling 60-minute history)
CREATE VIEW IF NOT EXISTS orders_time_bucketed AS
SELECT
    o.order_id,
    o.store_id,
    o.order_status,
    o.order_created_at,
    date_bin('1 minute', o.order_created_at, '2000-01-01 00:00:00+00'::timestamptz) + INTERVAL '1 minute' AS window_end
FROM orders_flat_mv o
WHERE o.order_created_at IS NOT NULL
  AND mz_now() <= EXTRACT(EPOCH FROM o.order_created_at)::bigint * 1000 + 3600000;

-- Store metrics aggregated by time window
CREATE MATERIALIZED VIEW IF NOT EXISTS store_metrics_by_window_mv IN CLUSTER compute AS
SELECT
    ob.store_id,
    ob.window_end,
    COUNT(*) FILTER (WHERE ob.order_status = 'CREATED') AS queue_depth,
    COUNT(*) FILTER (WHERE ob.order_status IN ('PICKING', 'OUT_FOR_DELIVERY')) AS in_progress,
    COUNT(*) AS total_orders
FROM orders_time_bucketed ob
WHERE mz_now() >= EXTRACT(EPOCH FROM ob.window_end)::bigint * 1000
  AND mz_now() < EXTRACT(EPOCH FROM ob.window_end)::bigint * 1000 + 1800000
GROUP BY ob.store_id, ob.window_end;

-- Delivery tasks flat with timestamps (intermediate view for wait time calculation)
CREATE VIEW IF NOT EXISTS delivery_tasks_flat_with_timestamps AS
SELECT
    subject_id AS task_id,
    MAX(CASE WHEN predicate = 'task_of_order' THEN object_value END) AS order_id,
    MAX(CASE WHEN predicate = 'assigned_to' THEN object_value END) AS assigned_courier_id,
    MAX(CASE WHEN predicate = 'task_status' THEN object_value END) AS task_status,
    MAX(CASE WHEN predicate = 'task_started_at' THEN object_value END)::TIMESTAMPTZ AS task_started_at,
    MAX(CASE WHEN predicate = 'task_completed_at' THEN object_value END)::TIMESTAMPTZ AS task_completed_at,
    MAX(CASE WHEN predicate = 'eta' THEN object_value END) AS eta,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'task:%'
GROUP BY subject_id;

-- Delivery task timestamps with wait time bucketing
CREATE VIEW IF NOT EXISTS wait_times_bucketed AS
SELECT
    dt.order_id,
    o.store_id,
    dt.task_started_at,
    EXTRACT(EPOCH FROM (dt.task_started_at - o.order_created_at)) / 60.0 AS wait_minutes,
    date_bin('1 minute', dt.task_started_at, '2000-01-01 00:00:00+00'::timestamptz) + INTERVAL '1 minute' AS window_end
FROM delivery_tasks_flat_with_timestamps dt
JOIN orders_flat_mv o ON dt.order_id = o.order_id
WHERE dt.task_started_at IS NOT NULL
  AND o.order_created_at IS NOT NULL
  AND mz_now() <= EXTRACT(EPOCH FROM dt.task_started_at)::bigint * 1000 + 3600000;

-- Store wait time metrics by time window
CREATE MATERIALIZED VIEW IF NOT EXISTS store_wait_time_by_window_mv IN CLUSTER compute AS
SELECT
    wb.store_id,
    wb.window_end,
    AVG(wb.wait_minutes)::numeric(10,2) AS avg_wait_minutes,
    MAX(wb.wait_minutes)::numeric(10,2) AS max_wait_minutes,
    COUNT(*) AS orders_picked_up
FROM wait_times_bucketed wb
WHERE mz_now() >= EXTRACT(EPOCH FROM wb.window_end)::bigint * 1000
  AND mz_now() < EXTRACT(EPOCH FROM wb.window_end)::bigint * 1000 + 1800000
GROUP BY wb.store_id, wb.window_end;

-- Combined store metrics timeseries for UI consumption
-- ID is generated from store_id + window_end for Zero single-column PK requirement
CREATE MATERIALIZED VIEW IF NOT EXISTS store_metrics_timeseries_mv IN CLUSTER compute AS
SELECT
    COALESCE(sm.store_id, wt.store_id) || ':' || EXTRACT(EPOCH FROM COALESCE(sm.window_end, wt.window_end))::bigint::text AS id,
    COALESCE(sm.store_id, wt.store_id) AS store_id,
    EXTRACT(EPOCH FROM COALESCE(sm.window_end, wt.window_end))::bigint * 1000 AS window_end,
    COALESCE(sm.queue_depth, 0) AS queue_depth,
    COALESCE(sm.in_progress, 0) AS in_progress,
    COALESCE(sm.total_orders, 0) AS total_orders,
    wt.avg_wait_minutes,
    wt.max_wait_minutes,
    COALESCE(wt.orders_picked_up, 0) AS orders_picked_up
FROM store_metrics_by_window_mv sm
FULL JOIN store_wait_time_by_window_mv wt
    ON sm.store_id = wt.store_id AND sm.window_end = wt.window_end;

-- System-wide aggregate timeseries for executive dashboard
CREATE MATERIALIZED VIEW IF NOT EXISTS system_metrics_timeseries_mv IN CLUSTER compute AS
SELECT
    window_end::text AS id,
    window_end,
    SUM(queue_depth) AS total_queue_depth,
    SUM(in_progress) AS total_in_progress,
    SUM(total_orders) AS total_orders,
    AVG(avg_wait_minutes)::numeric(10,2) AS avg_wait_minutes,
    MAX(max_wait_minutes) AS max_wait_minutes,
    SUM(orders_picked_up) AS total_orders_picked_up
FROM store_metrics_timeseries_mv
GROUP BY window_end;

-- Indexes for timeseries queries
CREATE INDEX IF NOT EXISTS idx_store_metrics_timeseries_store_id IN CLUSTER serving ON store_metrics_timeseries_mv (store_id);
CREATE INDEX IF NOT EXISTS idx_store_metrics_timeseries_window IN CLUSTER serving ON store_metrics_timeseries_mv (window_end);
CREATE INDEX IF NOT EXISTS idx_system_metrics_timeseries_window IN CLUSTER serving ON system_metrics_timeseries_mv (window_end);
