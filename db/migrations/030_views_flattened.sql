-- 030_views_flattened.sql
-- Flattened views for operational queries

-- Orders Flattened View
-- Provides a denormalized view of orders with key operational context
CREATE OR REPLACE VIEW orders_flat AS
WITH order_subjects AS (
    SELECT DISTINCT subject_id
    FROM triples
    WHERE subject_id LIKE 'order:%'
)
SELECT
    os.subject_id AS order_id,
    MAX(CASE WHEN t.predicate = 'order_number' THEN t.object_value END) AS order_number,
    MAX(CASE WHEN t.predicate = 'order_status' THEN t.object_value END) AS order_status,
    MAX(CASE WHEN t.predicate = 'order_store' THEN t.object_value END) AS store_id,
    MAX(CASE WHEN t.predicate = 'placed_by' THEN t.object_value END) AS customer_id,
    MAX(CASE WHEN t.predicate = 'delivery_window_start' THEN t.object_value END) AS delivery_window_start,
    MAX(CASE WHEN t.predicate = 'delivery_window_end' THEN t.object_value END) AS delivery_window_end,
    MAX(CASE WHEN t.predicate = 'order_total_amount' THEN t.object_value END)::DECIMAL(10,2) AS order_total_amount,
    MAX(t.updated_at) AS effective_updated_at
FROM order_subjects os
LEFT JOIN triples t ON t.subject_id = os.subject_id
GROUP BY os.subject_id;

-- Store Inventory Flattened View
-- Shows current inventory levels per store and product
CREATE OR REPLACE VIEW store_inventory_flat AS
WITH inventory_subjects AS (
    SELECT DISTINCT subject_id
    FROM triples
    WHERE subject_id LIKE 'inventory:%'
)
SELECT
    inv.subject_id AS inventory_id,
    MAX(CASE WHEN t.predicate = 'inventory_store' THEN t.object_value END) AS store_id,
    MAX(CASE WHEN t.predicate = 'inventory_product' THEN t.object_value END) AS product_id,
    MAX(CASE WHEN t.predicate = 'stock_level' THEN t.object_value END)::INT AS stock_level,
    MAX(CASE WHEN t.predicate = 'replenishment_eta' THEN t.object_value END) AS replenishment_eta,
    MAX(t.updated_at) AS effective_updated_at
FROM inventory_subjects inv
LEFT JOIN triples t ON t.subject_id = inv.subject_id
GROUP BY inv.subject_id;

-- Courier Schedule Flattened View
-- Shows couriers with their current status and assigned tasks
CREATE OR REPLACE VIEW courier_schedule_flat AS
WITH courier_subjects AS (
    SELECT DISTINCT subject_id
    FROM triples
    WHERE subject_id LIKE 'courier:%'
),
courier_tasks AS (
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
    GROUP BY t_assigned.object_value, t_task.subject_id
)
SELECT
    cs.subject_id AS courier_id,
    MAX(CASE WHEN t.predicate = 'courier_name' THEN t.object_value END) AS courier_name,
    MAX(CASE WHEN t.predicate = 'home_store' THEN t.object_value END) AS home_store_id,
    MAX(CASE WHEN t.predicate = 'vehicle_type' THEN t.object_value END) AS vehicle_type,
    MAX(CASE WHEN t.predicate = 'courier_status' THEN t.object_value END) AS courier_status,
    COALESCE(
        json_agg(
            json_build_object(
                'task_id', ct.task_id,
                'task_status', ct.task_status,
                'order_id', ct.order_id,
                'eta', ct.eta,
                'route_sequence', ct.route_sequence
            )
        ) FILTER (WHERE ct.task_id IS NOT NULL),
        '[]'::json
    ) AS tasks,
    MAX(t.updated_at) AS effective_updated_at
FROM courier_subjects cs
LEFT JOIN triples t ON t.subject_id = cs.subject_id
LEFT JOIN courier_tasks ct ON ct.courier_id = cs.subject_id
GROUP BY cs.subject_id;

-- Stores Flattened View
-- Shows all stores with their attributes
CREATE OR REPLACE VIEW stores_flat AS
WITH store_subjects AS (
    SELECT DISTINCT subject_id
    FROM triples
    WHERE subject_id LIKE 'store:%'
)
SELECT
    ss.subject_id AS store_id,
    MAX(CASE WHEN t.predicate = 'store_name' THEN t.object_value END) AS store_name,
    MAX(CASE WHEN t.predicate = 'store_zone' THEN t.object_value END) AS store_zone,
    MAX(CASE WHEN t.predicate = 'store_address' THEN t.object_value END) AS store_address,
    MAX(CASE WHEN t.predicate = 'store_status' THEN t.object_value END) AS store_status,
    MAX(CASE WHEN t.predicate = 'store_capacity_orders_per_hour' THEN t.object_value END)::INT AS store_capacity_orders_per_hour,
    MAX(t.updated_at) AS effective_updated_at
FROM store_subjects ss
LEFT JOIN triples t ON t.subject_id = ss.subject_id
GROUP BY ss.subject_id;

-- Customers Flattened View
-- Shows all customers with their attributes
CREATE OR REPLACE VIEW customers_flat AS
WITH customer_subjects AS (
    SELECT DISTINCT subject_id
    FROM triples
    WHERE subject_id LIKE 'customer:%'
)
SELECT
    cs.subject_id AS customer_id,
    MAX(CASE WHEN t.predicate = 'customer_name' THEN t.object_value END) AS customer_name,
    MAX(CASE WHEN t.predicate = 'customer_email' THEN t.object_value END) AS customer_email,
    MAX(CASE WHEN t.predicate = 'customer_address' THEN t.object_value END) AS customer_address,
    MAX(t.updated_at) AS effective_updated_at
FROM customer_subjects cs
LEFT JOIN triples t ON t.subject_id = cs.subject_id
GROUP BY cs.subject_id;

-- Insert migration record
INSERT INTO schema_migrations (version) VALUES ('030_views_flattened')
ON CONFLICT (version) DO NOTHING;
