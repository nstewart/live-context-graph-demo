#!/bin/bash
# Initialize Materialize with Three-Tier Architecture
# Run this after docker-compose up to set up Materialize
#
# Architecture:
#   ingest cluster  -> Sources (PostgreSQL connection)
#   compute cluster -> (reserved for future transformations)
#   serving cluster -> Indexes on views

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

echo "Creating source in ingest cluster..."

# Create source in ingest cluster
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE SOURCE IF NOT EXISTS pg_source
    IN CLUSTER ingest
    FROM POSTGRES CONNECTION pg_connection (PUBLICATION 'mz_source')
    FOR ALL TABLES;" || true

echo "Waiting for source to hydrate..."
sleep 5

echo "Creating views..."

# Create views (one at a time due to Materialize transaction requirements)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS orders_flat AS
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
CREATE VIEW IF NOT EXISTS store_inventory AS
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

psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "
CREATE VIEW IF NOT EXISTS orders_search_source AS
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
FROM orders_flat o
LEFT JOIN customers_flat c ON c.customer_id = o.customer_id
LEFT JOIN stores_flat s ON s.store_id = o.store_id
LEFT JOIN delivery_tasks_flat dt ON dt.order_id = o.order_id;" || true

echo "Creating indexes in serving cluster..."

# Create indexes in serving cluster (makes views queryable with low latency)
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_flat_idx IN CLUSTER serving ON orders_flat (order_id);" || true
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS store_inventory_idx IN CLUSTER serving ON store_inventory (inventory_id);" || true
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -c "CREATE INDEX IF NOT EXISTS orders_search_source_idx IN CLUSTER serving ON orders_search_source (order_id);" || true

echo "Verifying setup..."
echo ""
echo "=== Clusters ==="
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -t -c "SELECT name, replicas FROM (SHOW CLUSTERS) WHERE name IN ('ingest', 'compute', 'serving');"

echo ""
echo "=== Views ==="
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -t -c "SELECT name FROM (SHOW VIEWS);"

echo ""
echo "=== Indexes ==="
psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -t -c "SELECT name, on AS view_name, cluster FROM (SHOW INDEXES);"

echo ""
echo "=== Order Count ==="
COUNT=$(psql -h "$MZ_HOST" -p "$MZ_PORT" -U materialize -t -c "SET CLUSTER = serving; SELECT count(*) FROM orders_search_source;")
echo "Orders in Materialize: $COUNT"

echo ""
echo "Materialize three-tier initialization complete!"
