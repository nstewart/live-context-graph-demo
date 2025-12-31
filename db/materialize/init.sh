#!/bin/bash
# Initialize Materialize with Three-Tier Architecture
# Run this after docker-compose up to set up Materialize
#
# Architecture:
#   ingest cluster  -> Sources (PostgreSQL logical replication)
#   compute cluster -> Materialized views (persist transformation results)
#   serving cluster -> Indexes (serve queries with low latency)
#
# Pattern:
#   - Regular views for intermediate transformations (no cluster)
#   - Materialized views IN CLUSTER compute for "topmost" views that serve results
#   - Indexes IN CLUSTER serving ON materialized views

set -e

MZ_HOST=${MZ_HOST:-localhost}
MZ_PORT=${MZ_PORT:-6875}

echo "Waiting for Materialize to be ready..."
until psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "SELECT 1" > /dev/null 2>&1; do
    echo "Materialize is not ready yet, waiting..."
    sleep 2
done
echo "Materialize is ready!"

echo "Setting up Three-Tier Architecture clusters..."

# Create clusters (ignore errors if already exist)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE CLUSTER ingest (SIZE = '25cc');" 2>/dev/null || echo "ingest cluster already exists"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE CLUSTER compute (SIZE = '25cc');" 2>/dev/null || echo "compute cluster already exists"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE CLUSTER serving (SIZE = '25cc');" 2>/dev/null || echo "serving cluster already exists"

echo "Creating PostgreSQL connection..."

# Create secret
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE SECRET IF NOT EXISTS pgpass AS 'postgres';"

# Create connection
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE CONNECTION IF NOT EXISTS pg_connection TO POSTGRES (
    HOST 'db',
    PORT 5432,
    USER 'postgres',
    PASSWORD SECRET pgpass,
    DATABASE 'freshmart'
);"

echo "Creating source IN CLUSTER ingest..."

# Create source in ingest cluster
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE SOURCE IF NOT EXISTS pg_source
    IN CLUSTER ingest
    FROM POSTGRES CONNECTION pg_connection (PUBLICATION 'mz_source')
    FOR ALL TABLES;"

echo "Waiting for source to hydrate..."
sleep 5

echo "Creating index on triples source for subject_id lookups..."
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS triples_subject_idx IN CLUSTER serving ON triples (subject_id);"

echo "Creating regular views for intermediate transformations..."

# Create regular views (one at a time due to Materialize transaction requirements)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS customers_flat AS
SELECT
    subject_id AS customer_id,
    MAX(CASE WHEN predicate = 'customer_name' THEN object_value END) AS customer_name,
    MAX(CASE WHEN predicate = 'customer_email' THEN object_value END) AS customer_email,
    MAX(CASE WHEN predicate = 'customer_address' THEN object_value END) AS customer_address,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'customer:%'
GROUP BY subject_id;"

psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS stores_flat AS
SELECT
    subject_id AS store_id,
    MAX(CASE WHEN predicate = 'store_name' THEN object_value END) AS store_name,
    MAX(CASE WHEN predicate = 'store_zone' THEN object_value END) AS store_zone,
    MAX(CASE WHEN predicate = 'store_address' THEN object_value END) AS store_address,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'store:%'
GROUP BY subject_id;"

psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS delivery_tasks_flat AS
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
GROUP BY subject_id;"

psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
GROUP BY subject_id;"

echo "Creating materialized views IN CLUSTER compute..."

# Create materialized views in compute cluster
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS orders_flat_mv IN CLUSTER compute AS
WITH order_line_amounts AS (
    -- Calculate line_amount from quantity * unit_price (derived, not stored)
    SELECT
        subject_id AS line_id,
        MAX(CASE WHEN predicate = 'line_of_order' THEN object_value END) AS order_id,
        (MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT
         * MAX(CASE WHEN predicate = 'order_line_unit_price' THEN object_value END)::DECIMAL(10,2))::DECIMAL(10,2) AS line_amount
    FROM triples
    WHERE subject_id LIKE 'orderline:%'
    GROUP BY subject_id
),
order_totals AS (
    -- Aggregate line amounts per order BEFORE joining with order triples
    SELECT
        order_id,
        COALESCE(SUM(line_amount), 0.00)::DECIMAL(10,2) AS computed_total
    FROM order_line_amounts
    GROUP BY order_id
)
SELECT
    o.subject_id AS order_id,
    MAX(CASE WHEN o.predicate = 'order_number' THEN o.object_value END) AS order_number,
    MAX(CASE WHEN o.predicate = 'order_status' THEN o.object_value END) AS order_status,
    MAX(CASE WHEN o.predicate = 'order_store' THEN o.object_value END) AS store_id,
    MAX(CASE WHEN o.predicate = 'placed_by' THEN o.object_value END) AS customer_id,
    MAX(CASE WHEN o.predicate = 'delivery_window_start' THEN o.object_value END) AS delivery_window_start,
    MAX(CASE WHEN o.predicate = 'delivery_window_end' THEN o.object_value END) AS delivery_window_end,
    MAX(CASE WHEN o.predicate = 'order_created_at' THEN o.object_value END)::TIMESTAMPTZ AS order_created_at,
    -- COMPUTED from line items (not from triple) - auto-calculated, always accurate
    COALESCE(ot.computed_total, 0.00)::DECIMAL(10,2) AS order_total_amount,
    MAX(o.updated_at) AS effective_updated_at
FROM triples o
LEFT JOIN order_totals ot ON ot.order_id = o.subject_id
WHERE o.subject_id LIKE 'order:%'
GROUP BY o.subject_id, ot.computed_total;"

echo "Creating order line views..."

# Order lines base view
# Note: perishable_flag is NOT stored here - it is derived from products in order_lines_flat_mv
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS order_lines_base AS
SELECT
    subject_id AS line_id,
    MAX(CASE WHEN predicate = 'line_of_order' THEN object_value END) AS order_id,
    MAX(CASE WHEN predicate = 'line_product' THEN object_value END) AS product_id,
    MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT AS quantity,
    MAX(CASE WHEN predicate = 'order_line_unit_price' THEN object_value END)::DECIMAL(10,2) AS unit_price,
    -- Calculate line_amount from quantity * unit_price (derived, not stored)
    (MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT
     * MAX(CASE WHEN predicate = 'order_line_unit_price' THEN object_value END)::DECIMAL(10,2))::DECIMAL(10,2) AS line_amount,
    MAX(CASE WHEN predicate = 'line_sequence' THEN object_value END)::INT AS line_sequence,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'orderline:%'
GROUP BY subject_id;"

# Order lines flat materialized view with product enrichment
# perishable_flag is DERIVED from products_flat.perishable (not stored on order line)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS order_lines_flat_mv IN CLUSTER compute AS
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
LEFT JOIN products_flat p ON p.product_id = ol.product_id;"

# Drop first to ensure schema updates are applied
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "DROP MATERIALIZED VIEW IF EXISTS store_inventory_mv CASCADE;" 2>/dev/null
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW store_inventory_mv IN CLUSTER compute AS
WITH order_reservations AS (
    -- Calculate reserved quantity per product per store from pending orders
    SELECT
        o.store_id,
        ol.product_id,
        SUM(ol.quantity) AS reserved_quantity
    FROM order_lines_flat_mv ol
    JOIN orders_flat_mv o ON o.order_id = ol.order_id
    WHERE o.order_status IN ('CREATED', 'PICKING', 'OUT_FOR_DELIVERY')
    GROUP BY o.store_id, ol.product_id
)
SELECT
    inv.inventory_id,
    inv.store_id,
    inv.product_id,
    inv.stock_level,
    -- NEW: Reserved quantity from pending orders
    COALESCE(res.reserved_quantity, 0)::INT AS reserved_quantity,
    -- NEW: Available quantity (stock minus reservations)
    GREATEST(inv.stock_level - COALESCE(res.reserved_quantity, 0), 0)::INT AS available_quantity,
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
    -- Availability flags (based on AVAILABLE quantity, not total stock)
    CASE
        WHEN GREATEST(inv.stock_level - COALESCE(res.reserved_quantity, 0), 0) > 10 THEN 'IN_STOCK'
        WHEN GREATEST(inv.stock_level - COALESCE(res.reserved_quantity, 0), 0) > 0 THEN 'LOW_STOCK'
        ELSE 'OUT_OF_STOCK'
    END AS availability_status,
    (GREATEST(inv.stock_level - COALESCE(res.reserved_quantity, 0), 0) <= 10
     AND GREATEST(inv.stock_level - COALESCE(res.reserved_quantity, 0), 0) > 0) AS low_stock
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
LEFT JOIN order_reservations res ON res.store_id = inv.store_id AND res.product_id = inv.product_id
LEFT JOIN products_flat p ON p.product_id = inv.product_id
LEFT JOIN stores_flat s ON s.store_id = inv.store_id;"

psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
LEFT JOIN delivery_tasks_flat dt ON dt.order_id = o.order_id;"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS order_timestamps AS
SELECT
    subject_id AS order_id,
    MAX(CASE WHEN predicate = 'order_created_at' THEN object_value END) AS order_created_at,
    MAX(CASE WHEN predicate = 'delivered_at' THEN object_value END) AS delivered_at
FROM triples
WHERE subject_id LIKE 'order:%'
GROUP BY subject_id;"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
GROUP BY t_assigned.object_value, t_task.subject_id;"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
    dt.task_started_at,
    dt.task_completed_at,
    CASE
        WHEN ot.delivered_at IS NOT NULL AND ot.order_created_at IS NOT NULL
        THEN EXTRACT(EPOCH FROM (ot.delivered_at::TIMESTAMPTZ - ot.order_created_at::TIMESTAMPTZ)) / 60
        ELSE NULL
    END AS wait_time_minutes
FROM courier_tasks_flat ct
LEFT JOIN order_timestamps ot ON ot.order_id = ct.order_id
LEFT JOIN delivery_tasks_flat dt ON dt.task_id = ct.task_id;"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS couriers_flat AS
SELECT
    subject_id AS courier_id,
    MAX(CASE WHEN predicate = 'courier_name' THEN object_value END) AS courier_name,
    MAX(CASE WHEN predicate = 'courier_home_store' THEN object_value END) AS home_store_id,
    MAX(CASE WHEN predicate = 'vehicle_type' THEN object_value END) AS vehicle_type,
    MAX(CASE WHEN predicate = 'courier_status' THEN object_value END) AS courier_status,
    MAX(CASE WHEN predicate = 'courier_status_changed_at' THEN object_value END) AS status_changed_at,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'courier:%'
GROUP BY subject_id;"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS courier_schedule_mv IN CLUSTER compute AS
SELECT
    cf.courier_id,
    cf.courier_name,
    cf.home_store_id,
    cf.vehicle_type,
    cf.courier_status,
    cf.status_changed_at,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'task_id', ct.task_id,
                'task_status', ct.task_status,
                'order_id', ct.order_id,
                'eta', ct.eta,
                'wait_time_minutes', ct.wait_time_minutes,
                'order_created_at', ct.order_created_at,
                'task_started_at', ct.task_started_at,
                'task_completed_at', ct.task_completed_at
            )
        ) FILTER (WHERE ct.task_id IS NOT NULL),
        '[]'::jsonb
    ) AS tasks,
    cf.effective_updated_at
FROM couriers_flat cf
LEFT JOIN courier_tasks_with_timestamps ct ON ct.courier_id = cf.courier_id
GROUP BY cf.courier_id, cf.courier_name, cf.home_store_id, cf.vehicle_type, cf.courier_status, cf.status_changed_at, cf.effective_updated_at;"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
GROUP BY subject_id;"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS customers_mv IN CLUSTER compute AS
SELECT
    subject_id AS customer_id,
    MAX(CASE WHEN predicate = 'customer_name' THEN object_value END) AS customer_name,
    MAX(CASE WHEN predicate = 'customer_email' THEN object_value END) AS customer_email,
    MAX(CASE WHEN predicate = 'customer_address' THEN object_value END) AS customer_address,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'customer:%'
GROUP BY subject_id;"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS products_mv IN CLUSTER compute AS
SELECT
    subject_id AS product_id,
    MAX(CASE WHEN predicate = 'product_name' THEN object_value END) AS product_name,
    MAX(CASE WHEN predicate = 'category' THEN object_value END) AS category,
    MAX(CASE WHEN predicate = 'unit_price' THEN object_value END)::DECIMAL(10,2) AS unit_price,
    MAX(CASE WHEN predicate = 'perishable' THEN object_value END)::BOOLEAN AS perishable,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'product:%'
GROUP BY subject_id;"

echo "Creating dynamic pricing view with market basket and time-of-day analysis..."

# Dynamic pricing view - regular view with 9 pricing factors including
# market basket analysis (O(n²) self-join) and time-of-day demand patterns
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS inventory_items_with_dynamic_pricing AS
WITH
  -- Get order lines from delivered orders with timestamps
  delivered_order_lines AS (
    SELECT
      ol.line_id,
      ol.order_id,
      ol.product_id,
      ol.category,
      ol.unit_price,
      ol.quantity,
      ol.perishable_flag,
      o.order_status,
      o.delivery_window_start,
      ol.effective_updated_at
    FROM order_lines_flat_mv ol
    JOIN orders_flat_mv o ON o.order_id = ol.order_id
    WHERE o.order_status = 'DELIVERED'
  ),

  -- ==========================================================================
  -- MARKET BASKET ANALYSIS (Expensive O(n²) self-join)
  -- Find products frequently bought together to enable anchor pricing strategy
  -- ==========================================================================
  product_pairs AS (
    -- Self-join order lines to find co-purchased products (expensive!)
    SELECT
      ol1.product_id AS product_a,
      ol2.product_id AS product_b,
      ol1.order_id
    FROM order_lines_flat_mv ol1
    JOIN order_lines_flat_mv ol2
      ON ol1.order_id = ol2.order_id
      AND ol1.product_id < ol2.product_id
  ),

  cross_sell_affinity AS (
    -- Calculate affinity scores for each product pair
    SELECT
      product_a,
      product_b,
      COUNT(*) AS co_purchase_count,
      COUNT(*)::numeric / NULLIF(
        (SELECT COUNT(DISTINCT order_id) FROM order_lines_flat_mv WHERE product_id = product_a), 0
      ) AS affinity_score_a,
      COUNT(*)::numeric / NULLIF(
        (SELECT COUNT(DISTINCT order_id) FROM order_lines_flat_mv WHERE product_id = product_b), 0
      ) AS affinity_score_b
    FROM product_pairs
    GROUP BY product_a, product_b
    HAVING COUNT(*) >= 2
  ),

  basket_metrics AS (
    SELECT
      product_id,
      COUNT(*) AS num_affinity_products,
      AVG(affinity_score) AS avg_affinity_score,
      MAX(co_purchase_count) AS max_copurchase_count,
      CASE
        WHEN COUNT(*) >= 5 AND AVG(affinity_score) > 0.3 THEN TRUE
        ELSE FALSE
      END AS is_basket_driver
    FROM (
      SELECT product_a AS product_id, affinity_score_a AS affinity_score, co_purchase_count
      FROM cross_sell_affinity
      UNION ALL
      SELECT product_b AS product_id, affinity_score_b AS affinity_score, co_purchase_count
      FROM cross_sell_affinity
    ) all_affinities
    GROUP BY product_id
  ),

  -- Note: TIME-OF-DAY DEMAND PATTERNS are NOT included in Materialize
  -- because NOW() cannot be used in materialized views (mz_now() only works in WHERE/HAVING)
  -- PostgreSQL views include time-of-day pricing; Materialize uses 8 factors instead of 9

  -- Sales velocity
  sales_velocity AS (
    SELECT
      product_id,
      SUM(quantity) FILTER (WHERE rn <= 5) AS recent_sales,
      SUM(quantity) FILTER (WHERE rn > 5 AND rn <= 15) AS prior_sales,
      SUM(quantity) AS total_sales
    FROM (
      SELECT
        product_id,
        quantity,
        ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY effective_updated_at DESC) AS rn
      FROM delivered_order_lines
    ) ranked_sales
    WHERE rn <= 15
    GROUP BY product_id
  ),

  popularity_score AS (
    SELECT
      product_id,
      category,
      SUM(quantity) AS sale_count,
      RANK() OVER (PARTITION BY category ORDER BY SUM(quantity) DESC) AS popularity_rank
    FROM delivered_order_lines
    GROUP BY product_id, category
  ),

  inventory_status AS (
    SELECT
      product_id,
      SUM(stock_level) AS total_stock,
      RANK() OVER (ORDER BY SUM(stock_level) ASC) AS scarcity_rank
    FROM store_inventory_mv
    GROUP BY product_id
  ),

  high_demand_products AS (
    SELECT
      product_id,
      sale_count,
      CASE
        WHEN sale_count > (SELECT AVG(sale_count) FROM popularity_score) THEN TRUE
        ELSE FALSE
      END AS is_high_demand
    FROM popularity_score
  ),

  pricing_factors AS (
    SELECT
      ps.product_id,
      ps.category,
      ps.sale_count,
      ps.popularity_rank,
      CASE
        WHEN ps.popularity_rank <= 3 THEN 1.20
        WHEN ps.popularity_rank BETWEEN 4 AND 10 THEN 1.10
        ELSE 0.90
      END AS popularity_adjustment,
      CASE
        WHEN inv.scarcity_rank <= 3 THEN 1.15
        WHEN inv.scarcity_rank BETWEEN 4 AND 10 THEN 1.08
        WHEN inv.scarcity_rank BETWEEN 11 AND 20 THEN 1.00
        ELSE 0.95
      END AS scarcity_adjustment,
      CASE
        WHEN sv.prior_sales > 0 THEN
          LEAST(GREATEST(
            1.0 + ((sv.recent_sales::numeric / sv.prior_sales) - 1.0) * 0.25,
            0.85
          ), 1.25)
        WHEN sv.recent_sales > 0 THEN 1.10
        ELSE 1.0
      END AS demand_multiplier,
      CASE WHEN hd.is_high_demand THEN 1.05 ELSE 1.0 END AS demand_premium,
      -- MARKET BASKET ADJUSTMENT
      CASE
        WHEN bm.is_basket_driver THEN 0.95
        WHEN bm.num_affinity_products >= 3 THEN 0.98
        ELSE 1.0
      END AS basket_adjustment,
      inv.total_stock,
      sv.recent_sales,
      sv.prior_sales,
      sv.total_sales,
      bm.num_affinity_products,
      bm.is_basket_driver
    FROM popularity_score ps
    LEFT JOIN inventory_status inv ON inv.product_id = ps.product_id
    LEFT JOIN sales_velocity sv ON sv.product_id = ps.product_id
    LEFT JOIN high_demand_products hd ON hd.product_id = ps.product_id
    LEFT JOIN basket_metrics bm ON bm.product_id = ps.product_id
  )

SELECT
  inv.inventory_id,
  inv.store_id,
  inv.store_name,
  inv.store_zone,
  inv.product_id,
  inv.product_name,
  inv.category,
  inv.stock_level,
  inv.reserved_quantity,
  inv.available_quantity,
  inv.perishable,
  inv.unit_price AS base_price,
  CASE
    WHEN inv.store_zone = 'MAN' THEN 1.15
    WHEN inv.store_zone = 'BK' THEN 1.05
    WHEN inv.store_zone = 'QNS' THEN 1.00
    WHEN inv.store_zone = 'BX' THEN 0.98
    WHEN inv.store_zone = 'SI' THEN 0.95
    ELSE 1.00
  END AS zone_adjustment,
  CASE
    WHEN inv.perishable = TRUE THEN 0.95
    ELSE 1.0
  END AS perishable_adjustment,
  CASE
    WHEN inv.available_quantity <= 5 THEN 1.10
    WHEN inv.available_quantity <= 15 THEN 1.03
    ELSE 1.0
  END AS local_stock_adjustment,
  pf.popularity_adjustment,
  pf.scarcity_adjustment,
  pf.demand_multiplier,
  pf.demand_premium,
  pf.basket_adjustment,
  pf.sale_count AS product_sale_count,
  pf.total_stock AS product_total_stock,
  -- Computed dynamic price with 8 factors (time-of-day excluded for Materialize)
  ROUND(
    (COALESCE(inv.unit_price, 0) *
    CASE WHEN inv.store_zone = 'MAN' THEN 1.15
         WHEN inv.store_zone = 'BK' THEN 1.05
         WHEN inv.store_zone = 'QNS' THEN 1.00
         WHEN inv.store_zone = 'BX' THEN 0.98
         WHEN inv.store_zone = 'SI' THEN 0.95
         ELSE 1.00 END *
    CASE WHEN inv.perishable = TRUE THEN 0.95 ELSE 1.0 END *
    CASE WHEN inv.available_quantity <= 5 THEN 1.10
         WHEN inv.available_quantity <= 15 THEN 1.03
         ELSE 1.0 END *
    COALESCE(pf.popularity_adjustment, 1.0) *
    COALESCE(pf.scarcity_adjustment, 1.0) *
    COALESCE(pf.demand_multiplier, 1.0) *
    COALESCE(pf.demand_premium, 1.0) *
    COALESCE(pf.basket_adjustment, 1.0))::numeric,
    2
  ) AS live_price,
  ROUND(
    ((COALESCE(inv.unit_price, 0) *
      CASE WHEN inv.store_zone = 'MAN' THEN 1.15
           WHEN inv.store_zone = 'BK' THEN 1.05
           WHEN inv.store_zone = 'QNS' THEN 1.00
           WHEN inv.store_zone = 'BX' THEN 0.98
           WHEN inv.store_zone = 'SI' THEN 0.95
           ELSE 1.00 END *
      CASE WHEN inv.perishable = TRUE THEN 0.95 ELSE 1.0 END *
      CASE WHEN inv.available_quantity <= 5 THEN 1.10
           WHEN inv.available_quantity <= 15 THEN 1.03
           ELSE 1.0 END *
      COALESCE(pf.popularity_adjustment, 1.0) *
      COALESCE(pf.scarcity_adjustment, 1.0) *
      COALESCE(pf.demand_multiplier, 1.0) *
      COALESCE(pf.demand_premium, 1.0) *
      COALESCE(pf.basket_adjustment, 1.0)
    ) - COALESCE(inv.unit_price, 0))::numeric,
    2
  ) AS price_change,
  inv.effective_updated_at
FROM store_inventory_mv inv
LEFT JOIN pricing_factors pf ON pf.product_id = inv.product_id
WHERE inv.unit_price IS NOT NULL;"

# Orders with aggregated line items and search fields (customer, store, delivery info)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS orders_with_lines_mv IN CLUSTER compute AS
SELECT
    o.order_id,
    o.order_number,
    o.order_status,
    o.store_id,
    o.customer_id,
    o.delivery_window_start,
    o.delivery_window_end,
    o.order_created_at,
    o.order_total_amount,
    -- Customer fields for search
    c.customer_name,
    c.customer_email,
    c.customer_address,
    -- Store fields for search
    s.store_name,
    s.store_zone,
    s.store_address,
    -- Delivery task fields for search
    dt.assigned_courier_id,
    dt.task_status AS delivery_task_status,
    dt.eta AS delivery_eta,
    -- Line items (static order data only - no dynamic pricing)
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
    SUM(ol.quantity * COALESCE(ol.unit_weight_grams, 0)::DECIMAL / 1000.0) AS total_weight_kg,
    GREATEST(
        o.effective_updated_at,
        MAX(ol.effective_updated_at),
        c.effective_updated_at,
        s.effective_updated_at,
        dt.effective_updated_at
    ) AS effective_updated_at
FROM orders_flat_mv o
LEFT JOIN customers_flat c ON c.customer_id = o.customer_id
LEFT JOIN stores_flat s ON s.store_id = o.store_id
LEFT JOIN delivery_tasks_flat dt ON dt.order_id = o.order_id
LEFT JOIN order_lines_flat_mv ol ON ol.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_number,
    o.order_status,
    o.store_id,
    o.customer_id,
    o.delivery_window_start,
    o.delivery_window_end,
    o.order_created_at,
    o.order_total_amount,
    o.effective_updated_at,
    c.customer_name,
    c.customer_email,
    c.customer_address,
    c.effective_updated_at,
    s.store_name,
    s.store_zone,
    s.store_address,
    s.effective_updated_at,
    dt.assigned_courier_id,
    dt.task_status,
    dt.eta,
    dt.effective_updated_at;"

echo "Creating dynamic pricing materialized view and indexes..."

# Materialize the dynamic pricing view
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS inventory_items_with_dynamic_pricing_mv
IN CLUSTER compute AS
SELECT * FROM inventory_items_with_dynamic_pricing;"
echo "Creating indexes IN CLUSTER serving on materialized views..."

# Create indexes in serving cluster on materialized views
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_flat_idx IN CLUSTER serving ON orders_flat_mv (order_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS store_inventory_idx IN CLUSTER serving ON store_inventory_mv (inventory_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_search_source_idx IN CLUSTER serving ON orders_search_source_mv (order_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS courier_schedule_idx IN CLUSTER serving ON courier_schedule_mv (courier_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS stores_idx IN CLUSTER serving ON stores_mv (store_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS customers_idx IN CLUSTER serving ON customers_mv (customer_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS products_idx IN CLUSTER serving ON products_mv (product_id);"

# Order line indexes
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS order_lines_order_id_idx IN CLUSTER serving ON order_lines_flat_mv (order_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS order_lines_product_id_idx IN CLUSTER serving ON order_lines_flat_mv (product_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS order_lines_order_sequence_idx IN CLUSTER serving ON order_lines_flat_mv (order_id, line_sequence);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_with_lines_idx IN CLUSTER serving ON orders_with_lines_mv (effective_updated_at DESC);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_with_lines_status_idx IN CLUSTER serving ON orders_with_lines_mv (order_status);"

# Dynamic pricing indexes
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_dynamic_pricing_idx IN CLUSTER serving ON inventory_items_with_dynamic_pricing_mv (inventory_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_dynamic_pricing_product_idx IN CLUSTER serving ON inventory_items_with_dynamic_pricing_mv (product_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_dynamic_pricing_store_idx IN CLUSTER serving ON inventory_items_with_dynamic_pricing_mv (store_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_dynamic_pricing_zone_idx IN CLUSTER serving ON inventory_items_with_dynamic_pricing_mv (store_zone);"

echo "Creating CEO metrics materialized views..."

# 1. Pricing Yield MV - tracks revenue premium from dynamic pricing
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS pricing_yield_mv IN CLUSTER compute AS
SELECT
    ol.line_id,
    ol.order_id,
    o.store_id,
    s.store_zone,
    ol.product_id,
    ol.category,
    ol.quantity,
    ol.unit_price AS order_price,
    ol.current_product_price AS base_price,
    (ol.unit_price - ol.current_product_price) * ol.quantity AS price_premium,
    o.order_status,
    o.effective_updated_at
FROM order_lines_flat_mv ol
JOIN orders_flat_mv o ON o.order_id = ol.order_id
JOIN stores_flat s ON s.store_id = o.store_id
WHERE o.order_status = 'DELIVERED'
  AND ol.current_product_price IS NOT NULL;"

# 2. Inventory Risk MV - identifies products at risk of stockout with revenue impact
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS inventory_risk_mv IN CLUSTER compute AS
WITH pending_reservations AS (
    SELECT
        o.store_id,
        ol.product_id,
        SUM(ol.quantity) AS pending_qty,
        SUM(ol.line_amount) AS pending_value
    FROM order_lines_flat_mv ol
    JOIN orders_flat_mv o ON o.order_id = ol.order_id
    WHERE o.order_status IN ('CREATED', 'PICKING', 'OUT_FOR_DELIVERY')
    GROUP BY o.store_id, ol.product_id
)
SELECT
    inv.inventory_id,
    inv.store_id,
    inv.store_name,
    inv.store_zone,
    inv.product_id,
    inv.product_name,
    inv.category,
    inv.stock_level,
    COALESCE(pr.pending_qty, 0)::INT AS pending_reservations,
    COALESCE(pr.pending_value, 0) AS revenue_at_risk,
    inv.perishable,
    CASE
        WHEN GREATEST(inv.stock_level - COALESCE(pr.pending_qty, 0), 0) <= 0 THEN 'CRITICAL'
        WHEN GREATEST(inv.stock_level - COALESCE(pr.pending_qty, 0), 0) <= 5 THEN 'HIGH'
        WHEN GREATEST(inv.stock_level - COALESCE(pr.pending_qty, 0), 0) <= 10 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS risk_level,
    CASE WHEN inv.perishable
        THEN COALESCE(pr.pending_value, 0) * 2
        ELSE COALESCE(pr.pending_value, 0)
    END AS risk_weighted_value,
    inv.effective_updated_at
FROM store_inventory_mv inv
LEFT JOIN pending_reservations pr
    ON pr.store_id = inv.store_id AND pr.product_id = inv.product_id
WHERE inv.unit_price IS NOT NULL;"

# 3. Store Capacity Health MV - monitors store utilization and capacity constraints
#
# CAPACITY MODEL EXPLANATION:
# - Hourly capacity (store_capacity_orders_per_hour): Number of new orders a store can accept per hour
# - Concurrent capacity: Total number of orders a store can handle simultaneously
#   Formula: hourly_rate × average_fulfillment_time
#
# The 4-hour multiplier represents the average fulfillment time for same-day delivery:
#   - Order placed → Picking (1-2 hours) → Packing (30 min) → Delivery (1-2 hours)
#   - This allows orders to arrive continuously while previous orders are still being fulfilled
#
# Example: A store with 10 orders/hour capacity can handle 40 concurrent orders
#   - New orders arrive at 10/hour
#   - Each order takes ~4 hours to complete
#   - At steady state: 40 orders in various stages of fulfillment
#
# Utilization is calculated as: active_orders / concurrent_capacity
# This gives a more accurate view of store workload than comparing to hourly intake rate alone.
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS store_capacity_health_mv IN CLUSTER compute AS
WITH active_workload AS (
    SELECT
        store_id,
        COUNT(*) AS active_orders,
        SUM(order_total_amount) AS active_value
    FROM orders_flat_mv
    WHERE order_status IN ('CREATED', 'PICKING', 'OUT_FOR_DELIVERY')
    GROUP BY store_id
),
store_with_capacity AS (
    SELECT
        s.store_id,
        s.store_name,
        s.store_zone,
        s.store_capacity_orders_per_hour,
        -- Concurrent capacity = hourly rate × 4 hours avg fulfillment time
        -- See comment block above for detailed explanation
        s.store_capacity_orders_per_hour * 4 AS concurrent_capacity,
        COALESCE(aw.active_orders, 0) AS active_orders,
        s.effective_updated_at
    FROM stores_mv s
    LEFT JOIN active_workload aw ON aw.store_id = s.store_id
)
SELECT
    store_id,
    store_name,
    store_zone,
    store_capacity_orders_per_hour,
    active_orders AS current_active_orders,
    ROUND((active_orders::DECIMAL / NULLIF(concurrent_capacity, 0)) * 100, 1) AS current_utilization_pct,
    concurrent_capacity - active_orders AS headroom,
    CASE
        WHEN (active_orders::DECIMAL / NULLIF(concurrent_capacity, 0)) >= 0.90 THEN 'CRITICAL'
        WHEN (active_orders::DECIMAL / NULLIF(concurrent_capacity, 0)) >= 0.70 THEN 'STRAINED'
        WHEN (active_orders::DECIMAL / NULLIF(concurrent_capacity, 0)) >= 0.40 THEN 'HEALTHY'
        ELSE 'UNDERUTILIZED'
    END AS health_status,
    CASE
        WHEN (active_orders::DECIMAL / NULLIF(concurrent_capacity, 0)) >= 0.90 THEN 'CLOSE_INTAKE'
        WHEN (active_orders::DECIMAL / NULLIF(concurrent_capacity, 0)) >= 0.70 THEN 'SURGE_PRICING'
        WHEN (active_orders::DECIMAL / NULLIF(concurrent_capacity, 0)) < 0.40 THEN 'PROMOTE_DEMAND'
        ELSE 'MONITOR'
    END AS recommended_action,
    effective_updated_at
FROM store_with_capacity;"

echo "Creating indexes for CEO metrics..."

# Pricing yield indexes
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS pricing_yield_zone_idx IN CLUSTER serving ON pricing_yield_mv (store_zone, category);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS pricing_yield_store_idx IN CLUSTER serving ON pricing_yield_mv (store_id);"

# Inventory risk indexes
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_risk_level_idx IN CLUSTER serving ON inventory_risk_mv (risk_level, store_zone);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_risk_store_idx IN CLUSTER serving ON inventory_risk_mv (store_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_risk_category_idx IN CLUSTER serving ON inventory_risk_mv (category);"

# Store capacity health indexes
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS store_capacity_health_idx IN CLUSTER serving ON store_capacity_health_mv (health_status, store_zone);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS store_capacity_store_idx IN CLUSTER serving ON store_capacity_health_mv (store_id);"

# =============================================================================
# COURIER DISPATCH VIEWS
# These views support the courier-driven order fulfillment system where:
# - Couriers handle both picking (2 min) and delivery (2 min)
# - Orders queue up if no couriers are available
# - Materialize incrementally maintains all courier/order state
# =============================================================================

echo "Creating courier dispatch views..."

# View 1: Available couriers per store
# Couriers who are AVAILABLE and not currently assigned to an active task
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS couriers_available AS
SELECT
    cf.courier_id,
    cf.courier_name,
    cf.home_store_id,
    cf.vehicle_type,
    cf.courier_status,
    cf.effective_updated_at
FROM couriers_flat cf
WHERE cf.courier_status = 'AVAILABLE'
  AND NOT EXISTS (
    SELECT 1 FROM delivery_tasks_flat dt
    WHERE dt.assigned_courier_id = cf.courier_id
      AND dt.task_status IN ('PICKING', 'DELIVERING')
  );"

# View 2: Orders awaiting courier assignment
# Orders in CREATED status that don't have an active delivery task
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS orders_awaiting_courier AS
SELECT
    o.order_id,
    o.order_number,
    o.store_id,
    o.customer_id,
    o.order_total_amount,
    o.delivery_window_start,
    o.delivery_window_end,
    o.effective_updated_at AS created_at
FROM orders_flat_mv o
WHERE o.order_status = 'CREATED'
  AND NOT EXISTS (
    SELECT 1 FROM delivery_tasks_flat dt
    WHERE dt.order_id = o.order_id
      AND dt.task_status IN ('PICKING', 'DELIVERING')
  );"

# View 3: Active delivery tasks with timing info
# Tasks currently being worked on, with expected completion time
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS delivery_tasks_active AS
SELECT
    dt.task_id,
    dt.order_id,
    dt.assigned_courier_id AS courier_id,
    dt.task_status,
    dt.task_started_at,
    o.store_id,
    o.customer_id,
    cf.courier_name,
    cf.vehicle_type,
    -- Expected completion time: task_started_at + 5 seconds
    dt.task_started_at + INTERVAL '5 seconds' AS expected_completion_at,
    dt.effective_updated_at
FROM delivery_tasks_flat dt
JOIN orders_flat_mv o ON o.order_id = dt.order_id
LEFT JOIN couriers_flat cf ON cf.courier_id = dt.assigned_courier_id
WHERE dt.task_status IN ('PICKING', 'DELIVERING')
  AND dt.task_started_at IS NOT NULL;"

# View 4: Tasks ready to advance (timer elapsed)
# Uses mz_now() for real-time filtering - tasks where 2 minutes have passed
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS tasks_ready_to_advance AS
SELECT
    task_id,
    order_id,
    courier_id,
    task_status,
    task_started_at,
    store_id,
    expected_completion_at
FROM delivery_tasks_active
WHERE expected_completion_at <= mz_now();"

# Materialized View 5: Store courier metrics
# Aggregated metrics per store for operational visibility
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS store_courier_metrics_mv IN CLUSTER compute AS
WITH courier_counts AS (
    SELECT
        cf.home_store_id AS store_id,
        COUNT(*) FILTER (WHERE cf.courier_status = 'AVAILABLE') AS available_couriers,
        COUNT(*) FILTER (WHERE cf.courier_status IN ('PICKING', 'DELIVERING')) AS busy_couriers,
        COUNT(*) FILTER (WHERE cf.courier_status = 'OFF_SHIFT') AS off_shift_couriers,
        COUNT(*) AS total_couriers
    FROM couriers_flat cf
    GROUP BY cf.home_store_id
),
queue_counts AS (
    SELECT
        store_id,
        COUNT(*) AS orders_in_queue
    FROM orders_awaiting_courier
    GROUP BY store_id
),
active_task_counts AS (
    SELECT
        store_id,
        COUNT(*) FILTER (WHERE task_status = 'PICKING') AS orders_picking,
        COUNT(*) FILTER (WHERE task_status = 'DELIVERING') AS orders_delivering
    FROM delivery_tasks_active
    GROUP BY store_id
)
SELECT
    s.store_id,
    s.store_name,
    s.store_zone,
    COALESCE(cc.total_couriers, 0)::INT AS total_couriers,
    COALESCE(cc.available_couriers, 0)::INT AS available_couriers,
    COALESCE(cc.busy_couriers, 0)::INT AS busy_couriers,
    COALESCE(cc.off_shift_couriers, 0)::INT AS off_shift_couriers,
    COALESCE(qc.orders_in_queue, 0)::INT AS orders_in_queue,
    COALESCE(atc.orders_picking, 0)::INT AS orders_picking,
    COALESCE(atc.orders_delivering, 0)::INT AS orders_delivering,
    -- Estimated wait time in minutes: (queue_depth / available_couriers) * 10 sec per order
    -- 10 seconds = 5 sec picking + 5 sec delivery
    CASE
        WHEN COALESCE(cc.available_couriers, 0) = 0 AND COALESCE(qc.orders_in_queue, 0) > 0
        THEN -1  -- Infinite wait (no couriers)
        WHEN COALESCE(cc.available_couriers, 0) = 0
        THEN 0   -- No queue, no couriers
        ELSE ROUND((COALESCE(qc.orders_in_queue, 0)::DECIMAL / cc.available_couriers) * (10.0 / 60.0), 1)
    END AS estimated_wait_minutes,
    -- Courier utilization percentage
    CASE
        WHEN COALESCE(cc.total_couriers, 0) = 0 THEN 0
        ELSE ROUND((COALESCE(cc.busy_couriers, 0)::DECIMAL / cc.total_couriers) * 100, 1)
    END AS courier_utilization_pct,
    s.effective_updated_at
FROM stores_flat s
LEFT JOIN courier_counts cc ON cc.store_id = s.store_id
LEFT JOIN queue_counts qc ON qc.store_id = s.store_id
LEFT JOIN active_task_counts atc ON atc.store_id = s.store_id;"

echo "Creating courier dispatch indexes..."

# Indexes for courier dispatch views
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS couriers_available_store_idx IN CLUSTER serving ON couriers_flat (home_store_id, courier_status);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS store_courier_metrics_idx IN CLUSTER serving ON store_courier_metrics_mv (store_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS store_courier_metrics_zone_idx IN CLUSTER serving ON store_courier_metrics_mv (store_zone);"

# =============================================================================
# TIME-SERIES VIEWS FOR SPARKLINES AND TREND ANALYSIS
# Uses mz_now() temporal filters to maintain a rolling 30-minute window
# =============================================================================

echo "Creating time-series views for sparklines..."

# Orders bucketed into 1-minute time windows (rolling 60-minute history)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS orders_time_bucketed AS
SELECT
    o.order_id,
    o.store_id,
    o.order_status,
    o.order_created_at,
    date_bin('1 minute', o.order_created_at, '2000-01-01 00:00:00+00'::timestamptz) + INTERVAL '1 minute' AS window_end
FROM orders_flat_mv o
WHERE o.order_created_at IS NOT NULL
  AND mz_now() <= EXTRACT(EPOCH FROM o.order_created_at)::bigint * 1000 + 3600000;"

# Store metrics aggregated by time window
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
GROUP BY ob.store_id, ob.window_end;"

# Delivery tasks flat with timestamps (intermediate view for wait time calculation)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
GROUP BY subject_id;"

# Delivery task timestamps with wait time bucketing
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
  AND mz_now() <= EXTRACT(EPOCH FROM dt.task_started_at)::bigint * 1000 + 3600000;"

# Store wait time metrics by time window
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
GROUP BY wb.store_id, wb.window_end;"

# Combined store metrics timeseries for UI consumption
# ID is generated from store_id + window_end for Zero single-column PK requirement
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
    ON sm.store_id = wt.store_id AND sm.window_end = wt.window_end;"

# System-wide aggregate timeseries for executive dashboard
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
GROUP BY window_end;"

echo "Creating indexes for timeseries queries..."

# Indexes for timeseries queries
# IMPORTANT: id index must come first - Zero requires an index on the primary key column
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS idx_store_metrics_timeseries_id IN CLUSTER serving ON store_metrics_timeseries_mv (id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS idx_system_metrics_timeseries_id IN CLUSTER serving ON system_metrics_timeseries_mv (id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS idx_store_metrics_timeseries_store_id IN CLUSTER serving ON store_metrics_timeseries_mv (store_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS idx_store_metrics_timeseries_window IN CLUSTER serving ON store_metrics_timeseries_mv (window_end);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS idx_system_metrics_timeseries_window IN CLUSTER serving ON system_metrics_timeseries_mv (window_end);"

# =============================================================================
# DELIVERY BUNDLING WITH MUTUALLY RECURSIVE CONSTRAINTS
# Demonstrates Materialize's WITH MUTUALLY RECURSIVE for Datalog-style logic
#
# Bundle orders that:
# 1. Share the same store (required for pickup efficiency)
# 2. Have overlapping delivery windows
# 3. Don't exceed available inventory when combined
# 4. Fit within courier vehicle capacity
#
# The mutual recursion pattern:
#   - compatible_pair: base pairwise compatibility check
#   - bundle_membership: assigns orders to bundles, referencing itself for clique validation
#   - Fixed-point iteration until bundle assignments stabilize
# =============================================================================

echo "Creating delivery bundling views with mutual recursion..."

# Helper view: Order weights (total weight per order)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS order_weights AS
SELECT
    ol.order_id,
    SUM(ol.quantity * COALESCE(ol.unit_weight_grams, 0))::INT AS total_weight_grams
FROM order_lines_flat_mv ol
GROUP BY ol.order_id;"

# Main mutually recursive view for delivery bundling
# Produces one row per bundle with JSON array of orders
# Each order appears in at most one bundle (greedy assignment to smallest bundle_id)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS delivery_bundles_mv IN CLUSTER compute AS
WITH MUTUALLY RECURSIVE (RETURN AT RECURSION LIMIT 100)
    -- CTE 1: Pairwise compatibility - orders that CAN be bundled together
    compatible_pair (order_a TEXT, order_b TEXT, store_id TEXT) AS (
        SELECT
            o1.order_id AS order_a,
            o2.order_id AS order_b,
            o1.store_id
        FROM orders_flat_mv o1
        JOIN orders_flat_mv o2
            ON o1.store_id = o2.store_id
            AND o1.order_id < o2.order_id
        LEFT JOIN order_weights w1 ON w1.order_id = o1.order_id
        LEFT JOIN order_weights w2 ON w2.order_id = o2.order_id
        WHERE o1.order_status = 'CREATED'
          AND o2.order_status = 'CREATED'
          -- Overlapping delivery windows
          AND o1.delivery_window_start::timestamptz <= o2.delivery_window_end::timestamptz
          AND o2.delivery_window_start::timestamptz <= o1.delivery_window_end::timestamptz
          -- Combined weight fits in VAN (50kg max)
          AND (COALESCE(w1.total_weight_grams, 0) + COALESCE(w2.total_weight_grams, 0)) <= 50000
          -- No inventory conflict
          AND NOT EXISTS (
              SELECT 1
              FROM order_lines_flat_mv ol1
              JOIN order_lines_flat_mv ol2
                  ON ol2.order_id = o2.order_id
                  AND ol2.product_id = ol1.product_id
              JOIN store_inventory_mv inv
                  ON inv.product_id = ol1.product_id
                  AND inv.store_id = o1.store_id
              WHERE ol1.order_id = o1.order_id
                AND ol1.quantity + ol2.quantity > inv.available_quantity
          )
          -- At least one compatible courier exists
          AND EXISTS (
              SELECT 1 FROM couriers_flat c
              WHERE c.home_store_id = o1.store_id
                AND c.courier_status = 'AVAILABLE'
                AND (
                    c.vehicle_type = 'VAN' OR
                    (c.vehicle_type = 'CAR' AND
                     COALESCE(w1.total_weight_grams, 0) + COALESCE(w2.total_weight_grams, 0) <= 20000) OR
                    (c.vehicle_type = 'BIKE' AND
                     COALESCE(w1.total_weight_grams, 0) + COALESCE(w2.total_weight_grams, 0) <= 5000)
                )
          )
    ),

    -- CTE 2: Bundle membership - assigns each order to a bundle
    -- Bundle is identified by smallest order_id among mutually compatible orders
    bundle_membership (order_id TEXT, bundle_id TEXT, store_id TEXT) AS (
        -- Base: every CREATED order starts in its own bundle
        SELECT o.order_id, o.order_id AS bundle_id, o.store_id
        FROM orders_flat_mv o
        WHERE o.order_status = 'CREATED'

        UNION

        -- Merge: order joins a smaller bundle if compatible with ALL its members
        SELECT
            bm1.order_id,
            bm2.bundle_id,
            bm1.store_id
        FROM bundle_membership bm1
        JOIN bundle_membership bm2
            ON bm2.store_id = bm1.store_id
            AND bm2.bundle_id < bm1.bundle_id
        WHERE
            -- Must be pairwise compatible with the bundle anchor
            EXISTS (
                SELECT 1 FROM compatible_pair cp
                WHERE cp.store_id = bm1.store_id
                  AND ((cp.order_a = bm2.bundle_id AND cp.order_b = bm1.order_id)
                    OR (cp.order_a = bm1.order_id AND cp.order_b = bm2.bundle_id))
            )
            -- Must be compatible with ALL other orders already in that bundle
            AND NOT EXISTS (
                SELECT 1 FROM bundle_membership other
                WHERE other.bundle_id = bm2.bundle_id
                  AND other.order_id != bm1.order_id
                  AND other.order_id != bm2.bundle_id
                  AND NOT EXISTS (
                      SELECT 1 FROM compatible_pair cp2
                      WHERE cp2.store_id = bm1.store_id
                        AND ((cp2.order_a = other.order_id AND cp2.order_b = bm1.order_id)
                          OR (cp2.order_a = bm1.order_id AND cp2.order_b = other.order_id))
                  )
            )
    )

-- Final output: one row per bundle with JSON array of orders
SELECT
    final.bundle_id,
    final.store_id,
    s.store_name,
    jsonb_agg(final.order_id ORDER BY final.order_id) AS orders,
    COUNT(*) AS bundle_size
FROM (
    -- Each order gets assigned to its SMALLEST valid bundle_id
    SELECT order_id, MIN(bundle_id) AS bundle_id, store_id
    FROM bundle_membership
    GROUP BY order_id, store_id
) final
JOIN stores_mv s ON s.store_id = final.store_id
GROUP BY final.bundle_id, final.store_id, s.store_name
ORDER BY bundle_size DESC, bundle_id;"

echo "Creating delivery bundling indexes..."

# Serving indexes for delivery bundles
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS delivery_bundles_id_idx IN CLUSTER serving ON delivery_bundles_mv (bundle_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS delivery_bundles_store_idx IN CLUSTER serving ON delivery_bundles_mv (store_id);"
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS delivery_bundles_size_idx IN CLUSTER serving ON delivery_bundles_mv (bundle_size);"

echo "Verifying three-tier setup..."
echo ""
echo "=== Clusters ==="
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -t -c "SELECT name, replicas FROM (SHOW CLUSTERS) WHERE name IN ('ingest', 'compute', 'serving');"

echo ""
echo "=== Regular Views (intermediate transformations) ==="
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -t -c "SELECT name FROM (SHOW VIEWS);"

echo ""
echo "=== Materialized Views (IN CLUSTER compute) ==="
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -t -c "SELECT name, cluster FROM (SHOW MATERIALIZED VIEWS);"

echo ""
echo "=== Indexes (IN CLUSTER serving) ==="
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -t -c "SELECT name, on AS view_name, cluster FROM (SHOW INDEXES);"

echo ""
echo "=== Order Count ==="
COUNT=$(psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -t -c "SET CLUSTER = serving; SELECT count(*) FROM orders_search_source_mv;")
echo "Orders in Materialize: $COUNT"

echo ""
echo "Materialize three-tier initialization complete!"
