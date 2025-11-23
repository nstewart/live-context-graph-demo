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
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE SECRET IF NOT EXISTS pgpass AS 'postgres';" || true

# Create connection
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE CONNECTION IF NOT EXISTS pg_connection TO POSTGRES (
    HOST 'db',
    PORT 5432,
    USER 'postgres',
    PASSWORD SECRET pgpass,
    DATABASE 'freshmart'
);" || true

echo "Creating source IN CLUSTER ingest..."

# Create source in ingest cluster
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE SOURCE IF NOT EXISTS pg_source
    IN CLUSTER ingest
    FROM POSTGRES CONNECTION pg_connection (PUBLICATION 'mz_source')
    FOR ALL TABLES;" || true

echo "Waiting for source to hydrate..."
sleep 5

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
GROUP BY subject_id;" || true

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
GROUP BY subject_id;" || true

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
GROUP BY subject_id;" || true

echo "Creating materialized views IN CLUSTER compute..."

# Create materialized views in compute cluster
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
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
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'order:%'
GROUP BY subject_id;" || true

psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE MATERIALIZED VIEW IF NOT EXISTS store_inventory_mv IN CLUSTER compute AS
SELECT
    subject_id AS inventory_id,
    MAX(CASE WHEN predicate = 'inventory_store' THEN object_value END) AS store_id,
    MAX(CASE WHEN predicate = 'inventory_product' THEN object_value END) AS product_id,
    MAX(CASE WHEN predicate = 'stock_level' THEN object_value END)::INT AS stock_level,
    MAX(CASE WHEN predicate = 'replenishment_eta' THEN object_value END) AS replenishment_eta,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'inventory:%'
GROUP BY subject_id;" || true

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
LEFT JOIN delivery_tasks_flat dt ON dt.order_id = o.order_id;" || true

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
GROUP BY t_assigned.object_value, t_task.subject_id;" || true

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
GROUP BY subject_id;" || true

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
GROUP BY cf.courier_id, cf.courier_name, cf.home_store_id, cf.vehicle_type, cf.courier_status, cf.effective_updated_at;" || true

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
GROUP BY subject_id;" || true

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
GROUP BY subject_id;" || true

echo "Creating indexes IN CLUSTER serving on materialized views..."

# Create indexes in serving cluster on materialized views
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_flat_idx IN CLUSTER serving ON orders_flat_mv (order_id);" || true
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS store_inventory_idx IN CLUSTER serving ON store_inventory_mv (inventory_id);" || true
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_search_source_idx IN CLUSTER serving ON orders_search_source_mv (order_id);" || true
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS courier_schedule_idx IN CLUSTER serving ON courier_schedule_mv (courier_id);" || true
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS stores_idx IN CLUSTER serving ON stores_mv (store_id);" || true
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS customers_idx IN CLUSTER serving ON customers_mv (customer_id);" || true

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
