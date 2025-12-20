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
    -- Extract line_amount for each orderline
    SELECT
        subject_id AS line_id,
        MAX(CASE WHEN predicate = 'line_of_order' THEN object_value END) AS order_id,
        MAX(CASE WHEN predicate = 'line_amount' THEN object_value END)::DECIMAL(10,2) AS line_amount
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
    -- COMPUTED from line items (not from triple) - auto-calculated, always accurate
    COALESCE(ot.computed_total, 0.00)::DECIMAL(10,2) AS order_total_amount,
    MAX(o.updated_at) AS effective_updated_at
FROM triples o
LEFT JOIN order_totals ot ON ot.order_id = o.subject_id
WHERE o.subject_id LIKE 'order:%'
GROUP BY o.subject_id, ot.computed_total;"

echo "Creating order line views..."

# Order lines base view
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
GROUP BY subject_id;"

# Order lines flat materialized view with product enrichment
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
    ol.perishable_flag,
    p.product_name,
    p.category,
    p.unit_price AS current_product_price,
    p.unit_weight_grams,
    ol.effective_updated_at
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
CREATE VIEW IF NOT EXISTS couriers_flat AS
SELECT
    subject_id AS courier_id,
    MAX(CASE WHEN predicate = 'courier_name' THEN object_value END) AS courier_name,
    MAX(CASE WHEN predicate = 'home_store' THEN object_value END) AS home_store_id,
    MAX(CASE WHEN predicate = 'vehicle_type' THEN object_value END) AS vehicle_type,
    MAX(CASE WHEN predicate = 'courier_status' THEN object_value END) AS courier_status,
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
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'task_id', ct.task_id,
                'task_status', ct.task_status,
                'order_id', ct.order_id,
                'eta', ct.eta,
                'route_sequence', ct.route_sequence
            )
        ) FILTER (WHERE ct.task_id IS NOT NULL),
        '[]'::jsonb
    ) AS tasks,
    cf.effective_updated_at
FROM couriers_flat cf
LEFT JOIN courier_tasks_flat ct ON ct.courier_id = cf.courier_id
GROUP BY cf.courier_id, cf.courier_name, cf.home_store_id, cf.vehicle_type, cf.courier_status, cf.effective_updated_at;"
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

echo "Creating dynamic pricing view..."

# Dynamic pricing view - regular view with pricing logic
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

  -- Calculate average price from last 10 sales per product
  recent_prices AS (
    SELECT
      product_id,
      AVG(unit_price) AS avg_recent_price,
      COUNT(*) AS recent_sale_count
    FROM (
      SELECT
        product_id,
        unit_price,
        effective_updated_at,
        ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY effective_updated_at DESC) AS rn
      FROM delivered_order_lines
    ) ranked_sales
    WHERE rn <= 10
    GROUP BY product_id
  ),

  -- Rank products by popularity (sales frequency) within category
  popularity_score AS (
    SELECT
      product_id,
      category,
      COUNT(*) AS sale_count,
      RANK() OVER (PARTITION BY category ORDER BY COUNT(*) DESC) AS popularity_rank
    FROM delivered_order_lines
    GROUP BY product_id, category
  ),

  -- Calculate total stock across all stores per product and rank by scarcity
  inventory_status AS (
    SELECT
      product_id,
      SUM(stock_level) AS total_stock,
      RANK() OVER (ORDER BY SUM(stock_level) ASC) AS scarcity_rank
    FROM store_inventory_mv
    GROUP BY product_id
  ),

  -- Identify high demand products (above average sales)
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

  -- Combine all product-level pricing factors
  pricing_factors AS (
    SELECT
      ps.product_id,
      ps.category,
      ps.sale_count,
      ps.popularity_rank,

      -- Popularity adjustment: Top 3 get 20% premium, 4-10 get 10%, rest get 10% discount
      CASE
        WHEN ps.popularity_rank <= 3 THEN 1.20
        WHEN ps.popularity_rank BETWEEN 4 AND 10 THEN 1.10
        ELSE 0.90
      END AS popularity_adjustment,

      -- Stock scarcity adjustment: Low stock (high scarcity rank) gets premium
      CASE
        WHEN inv.scarcity_rank <= 3 THEN 1.15
        WHEN inv.scarcity_rank BETWEEN 4 AND 10 THEN 1.08
        WHEN inv.scarcity_rank BETWEEN 11 AND 20 THEN 1.00
        ELSE 0.95
      END AS scarcity_adjustment,

      -- Demand multiplier: Compare current base price to recent avg
      CASE
        WHEN rp.avg_recent_price IS NOT NULL THEN
          1.0 + ((rp.avg_recent_price - ol_sample.sample_base_price) / NULLIF(ol_sample.sample_base_price, 0)) * 0.5
        ELSE 1.0
      END AS demand_multiplier,

      -- High demand flag for additional premium
      CASE WHEN hd.is_high_demand THEN 1.05 ELSE 1.0 END AS demand_premium,

      inv.total_stock,
      rp.avg_recent_price,
      rp.recent_sale_count

    FROM popularity_score ps
    LEFT JOIN inventory_status inv ON inv.product_id = ps.product_id
    LEFT JOIN recent_prices rp ON rp.product_id = ps.product_id
    LEFT JOIN high_demand_products hd ON hd.product_id = ps.product_id
    LEFT JOIN (
      -- Sample to get most recent base price per product
      SELECT
        product_id,
        unit_price AS sample_base_price
      FROM (
        SELECT
          product_id,
          unit_price,
          ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY effective_updated_at DESC) AS rn
        FROM order_lines_flat_mv
      ) ranked
      WHERE rn = 1
    ) ol_sample ON ol_sample.product_id = ps.product_id
  )

-- Final SELECT: Apply all adjustments to each inventory item
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

  -- Store-specific adjustments
  CASE
    WHEN inv.store_zone = 'MAN' THEN 1.15
    WHEN inv.store_zone = 'BK' THEN 1.05
    WHEN inv.store_zone = 'QNS' THEN 1.00
    WHEN inv.store_zone = 'BX' THEN 0.98
    WHEN inv.store_zone = 'SI' THEN 0.95
    ELSE 1.00
  END AS zone_adjustment,

  -- Perishable discount to move inventory faster
  CASE
    WHEN inv.perishable = TRUE THEN 0.95
    ELSE 1.0
  END AS perishable_adjustment,

  -- Low available stock at this specific store gets additional premium
  CASE
    WHEN inv.available_quantity <= 5 THEN 1.10
    WHEN inv.available_quantity <= 15 THEN 1.03
    ELSE 1.0
  END AS local_stock_adjustment,

  -- Product-level factors from CTEs
  pf.popularity_adjustment,
  pf.scarcity_adjustment,
  pf.demand_multiplier,
  pf.demand_premium,
  pf.sale_count AS product_sale_count,
  pf.total_stock AS product_total_stock,

  -- Computed dynamic price with all factors (using available quantity, not total stock)
  ROUND(
    COALESCE(inv.unit_price, 0) *
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
    COALESCE(pf.demand_premium, 1.0),
    2
  ) AS live_price,

  -- Price difference for easy comparison
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
      COALESCE(pf.demand_premium, 1.0)
    ) - COALESCE(inv.unit_price, 0),
    2
  ) AS price_change,

  inv.effective_updated_at

FROM store_inventory_mv inv
LEFT JOIN pricing_factors pf ON pf.product_id = inv.product_id
WHERE inv.availability_status != 'OUT_OF_STOCK'
  AND inv.unit_price IS NOT NULL;"

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
    -- Line items with dynamic pricing
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
                'unit_weight_grams', ol.unit_weight_grams,
                'inventory_id', inv.inventory_id,
                'base_price', inv.base_price,
                'live_price', inv.live_price,
                'price_change', inv.price_change,
                'zone_adjustment', inv.zone_adjustment,
                'perishable_adjustment', inv.perishable_adjustment,
                'local_stock_adjustment', inv.local_stock_adjustment,
                'popularity_adjustment', inv.popularity_adjustment,
                'scarcity_adjustment', inv.scarcity_adjustment,
                'demand_multiplier', inv.demand_multiplier,
                'demand_premium', inv.demand_premium,
                'product_sale_count', inv.product_sale_count,
                'product_total_stock', inv.product_total_stock,
                'current_stock_level', inv.available_quantity
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
LEFT JOIN inventory_items_with_dynamic_pricing inv
    ON inv.product_id = ol.product_id
    AND inv.store_id = o.store_id
GROUP BY
    o.order_id,
    o.order_number,
    o.order_status,
    o.store_id,
    o.customer_id,
    o.delivery_window_start,
    o.delivery_window_end,
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
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_flat_idx IN CLUSTER serving ON orders_flat_mv (order_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS store_inventory_idx IN CLUSTER serving ON store_inventory_mv (inventory_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_search_source_idx IN CLUSTER serving ON orders_search_source_mv (order_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS courier_schedule_idx IN CLUSTER serving ON courier_schedule_mv (courier_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS stores_idx IN CLUSTER serving ON stores_mv (store_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS customers_idx IN CLUSTER serving ON customers_mv (customer_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS products_idx IN CLUSTER serving ON products_mv (product_id);"
# Order line indexes
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS order_lines_order_id_idx IN CLUSTER serving ON order_lines_flat_mv (order_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS order_lines_product_id_idx IN CLUSTER serving ON order_lines_flat_mv (product_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS order_lines_order_sequence_idx IN CLUSTER serving ON order_lines_flat_mv (order_id, line_sequence);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_with_lines_idx IN CLUSTER serving ON orders_with_lines_mv (effective_updated_at DESC);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_with_lines_status_idx IN CLUSTER serving ON orders_with_lines_mv (order_status);"
# Dynamic pricing indexes
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_dynamic_pricing_idx IN CLUSTER serving ON inventory_items_with_dynamic_pricing_mv (inventory_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_dynamic_pricing_product_idx IN CLUSTER serving ON inventory_items_with_dynamic_pricing_mv (product_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_dynamic_pricing_store_idx IN CLUSTER serving ON inventory_items_with_dynamic_pricing_mv (store_id);"psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS inventory_dynamic_pricing_zone_idx IN CLUSTER serving ON inventory_items_with_dynamic_pricing_mv (store_zone);"

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
# Concurrent capacity = hourly throughput × avg fulfillment time (4 hours for same-day delivery)
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
