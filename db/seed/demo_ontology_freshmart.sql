-- demo_ontology_freshmart.sql
-- FreshMart Ontology Seed Data

-- =============================================================================
-- Ontology Classes
-- =============================================================================

INSERT INTO ontology_classes (class_name, prefix, description) VALUES
    ('Customer', 'customer', 'A customer who places orders'),
    ('Store', 'store', 'A FreshMart store location'),
    ('Product', 'product', 'A product available for sale'),
    ('InventoryItem', 'inventory', 'Store-product inventory record'),
    ('Order', 'order', 'A customer order'),
    ('OrderLine', 'orderline', 'A line item within an order'),
    ('Courier', 'courier', 'A delivery courier'),
    ('DeliveryTask', 'task', 'A delivery task assigned to a courier')
ON CONFLICT (class_name) DO NOTHING;

-- =============================================================================
-- Ontology Properties
-- =============================================================================

-- Customer properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'customer_name', id, 'string', NULL, FALSE, TRUE, 'Customer full name'
FROM ontology_classes WHERE class_name = 'Customer'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'customer_email', id, 'string', NULL, FALSE, FALSE, 'Customer email address'
FROM ontology_classes WHERE class_name = 'Customer'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'customer_address', id, 'string', NULL, FALSE, TRUE, 'Customer delivery address'
FROM ontology_classes WHERE class_name = 'Customer'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'home_store', c.id, 'entity_ref', s.id, FALSE, FALSE, 'Customer preferred store'
FROM ontology_classes c, ontology_classes s
WHERE c.class_name = 'Customer' AND s.class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

-- Store properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_name', id, 'string', NULL, FALSE, TRUE, 'Store display name'
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_address', id, 'string', NULL, FALSE, TRUE, 'Store physical address'
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_zone', id, 'string', NULL, FALSE, TRUE, 'Store delivery zone code'
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_status', id, 'string', NULL, FALSE, TRUE, 'Store operational status (OPEN, CLOSED, LIMITED)'
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_capacity_orders_per_hour', id, 'int', NULL, FALSE, FALSE, 'Maximum orders per hour'
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

-- Product properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'product_name', id, 'string', NULL, FALSE, TRUE, 'Product display name'
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'category', id, 'string', NULL, FALSE, TRUE, 'Product category'
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'perishable', id, 'bool', NULL, FALSE, TRUE, 'Whether product is perishable'
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'unit_weight_grams', id, 'int', NULL, FALSE, FALSE, 'Product weight in grams'
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'unit_price', id, 'float', NULL, FALSE, TRUE, 'Product unit price in dollars'
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

-- InventoryItem properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'inventory_store', i.id, 'entity_ref', s.id, FALSE, TRUE, 'Store holding this inventory'
FROM ontology_classes i, ontology_classes s
WHERE i.class_name = 'InventoryItem' AND s.class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'inventory_product', i.id, 'entity_ref', p.id, FALSE, TRUE, 'Product in inventory'
FROM ontology_classes i, ontology_classes p
WHERE i.class_name = 'InventoryItem' AND p.class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'stock_level', id, 'int', NULL, FALSE, TRUE, 'Current stock quantity'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'replenishment_eta', id, 'timestamp', NULL, FALSE, FALSE, 'Expected restock time'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

-- InventoryItem dynamic pricing properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'base_price', id, 'float', NULL, FALSE, FALSE, 'Base price before dynamic adjustments'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'live_price', id, 'float', NULL, FALSE, FALSE, 'Current dynamically-calculated price with all adjustments applied'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'price_change', id, 'float', NULL, FALSE, FALSE, 'Difference between live price and base price'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'zone_adjustment', id, 'float', NULL, FALSE, FALSE, 'Zone-based pricing multiplier (e.g., Manhattan premium)'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'perishable_adjustment', id, 'float', NULL, FALSE, FALSE, 'Perishability discount multiplier to move inventory faster'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'local_stock_adjustment', id, 'float', NULL, FALSE, FALSE, 'Local stock scarcity multiplier for this specific store'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'popularity_adjustment', id, 'float', NULL, FALSE, FALSE, 'Product popularity multiplier based on sales rank within category'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'scarcity_adjustment', id, 'float', NULL, FALSE, FALSE, 'Cross-store scarcity multiplier based on total available stock'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'demand_multiplier', id, 'float', NULL, FALSE, FALSE, 'Demand-based pricing multiplier for high-demand products'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'demand_premium', id, 'float', NULL, FALSE, FALSE, 'Additional demand premium for exceptionally high-demand products'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'product_sale_count', id, 'int', NULL, FALSE, FALSE, 'Historical sales count for this product across all stores'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'product_total_stock', id, 'int', NULL, FALSE, FALSE, 'Total stock level for this product across all stores'
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

-- Order properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_number', id, 'string', NULL, FALSE, TRUE, 'Human-readable order number (FM-XXXX)'
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'placed_by', o.id, 'entity_ref', c.id, FALSE, TRUE, 'Customer who placed the order'
FROM ontology_classes o, ontology_classes c
WHERE o.class_name = 'Order' AND c.class_name = 'Customer'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_store', o.id, 'entity_ref', s.id, FALSE, TRUE, 'Store fulfilling the order'
FROM ontology_classes o, ontology_classes s
WHERE o.class_name = 'Order' AND s.class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_status', id, 'string', NULL, FALSE, TRUE, 'Order status (CREATED, PICKING, OUT_FOR_DELIVERY, DELIVERED, CANCELLED)'
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'delivery_window_start', id, 'timestamp', NULL, FALSE, TRUE, 'Delivery window start time'
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'delivery_window_end', id, 'timestamp', NULL, FALSE, TRUE, 'Delivery window end time'
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_total_amount', id, 'float', NULL, FALSE, TRUE, 'Total order amount in dollars'
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_created_at', id, 'timestamp', NULL, FALSE, TRUE, 'Timestamp when the order was created'
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'delivered_at', id, 'timestamp', NULL, FALSE, FALSE, 'Timestamp when the order was delivered'
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

-- OrderLine properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_of_order', ol.id, 'entity_ref', o.id, FALSE, TRUE, 'Parent order'
FROM ontology_classes ol, ontology_classes o
WHERE ol.class_name = 'OrderLine' AND o.class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_product', ol.id, 'entity_ref', p.id, FALSE, TRUE, 'Product on this line'
FROM ontology_classes ol, ontology_classes p
WHERE ol.class_name = 'OrderLine' AND p.class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'quantity', id, 'int', NULL, FALSE, TRUE, 'Quantity ordered'
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_line_unit_price', id, 'float', NULL, FALSE, TRUE, 'Unit price at order time (price snapshot)'
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_amount', id, 'float', NULL, FALSE, FALSE, 'Line total amount (derived: quantity * unit_price)'
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_sequence', id, 'int', NULL, FALSE, TRUE, 'Display sequence within order'
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'perishable_flag', id, 'bool', NULL, FALSE, TRUE, 'Denormalized perishable flag from product for performance'
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_inventory_item', ol.id, 'entity_ref', inv.id, FALSE, FALSE, 'Inventory item used to fulfill this order line'
FROM ontology_classes ol, ontology_classes inv
WHERE ol.class_name = 'OrderLine' AND inv.class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

-- Courier properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'courier_name', id, 'string', NULL, FALSE, TRUE, 'Courier full name'
FROM ontology_classes WHERE class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT c.prop_name, co.id, 'entity_ref', s.id, FALSE, FALSE, 'Courier home store'
FROM (SELECT 'courier_home_store' AS prop_name) c, ontology_classes co, ontology_classes s
WHERE co.class_name = 'Courier' AND s.class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'vehicle_type', id, 'string', NULL, FALSE, TRUE, 'Vehicle type (BIKE, CAR, VAN)'
FROM ontology_classes WHERE class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'courier_status', id, 'string', NULL, FALSE, TRUE, 'Courier status (OFF_SHIFT, AVAILABLE, PICKING, DELIVERING)'
FROM ontology_classes WHERE class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'courier_status_changed_at', id, 'timestamp', NULL, FALSE, FALSE, 'Timestamp when courier status last changed'
FROM ontology_classes WHERE class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'current_task', c.id, 'entity_ref', dt.id, FALSE, FALSE, 'Current delivery task the courier is working on'
FROM ontology_classes c, ontology_classes dt
WHERE c.class_name = 'Courier' AND dt.class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

-- DeliveryTask properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'task_of_order', dt.id, 'entity_ref', o.id, FALSE, TRUE, 'Order being delivered'
FROM ontology_classes dt, ontology_classes o
WHERE dt.class_name = 'DeliveryTask' AND o.class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'assigned_to', dt.id, 'entity_ref', c.id, FALSE, FALSE, 'Assigned courier'
FROM ontology_classes dt, ontology_classes c
WHERE dt.class_name = 'DeliveryTask' AND c.class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'task_status', id, 'string', NULL, FALSE, TRUE, 'Task status (PICKING, DELIVERING, COMPLETED, FAILED, CANCELLED)'
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'task_started_at', id, 'timestamp', NULL, FALSE, FALSE, 'When the current task phase started (for timing task completion)'
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'task_completed_at', id, 'timestamp', NULL, FALSE, FALSE, 'Timestamp when the delivery task was completed'
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'eta', id, 'timestamp', NULL, FALSE, FALSE, 'Estimated delivery time'
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'route_sequence', id, 'int', NULL, FALSE, FALSE, 'Position in courier route'
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;
