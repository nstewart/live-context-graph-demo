-- demo_ontology_freshmart.sql
-- Ontology SHAPE: the eight classes, their prefixes, and the 60 properties
-- with their domains and range kinds. Identical for every label.
--
-- Descriptions are seeded NULL on purpose. They are prose a customer reads on
-- the Knowledge Graph tab, so they belong to the label, not to this file:
-- db/scripts/apply_ontology_labels.py writes them from labels/<name>.yaml
-- immediately after this runs. A NULL that survives means that step did not
-- run -- visibly blank beats silently showing the wrong vertical's wording.

-- =============================================================================
-- Ontology Classes
-- =============================================================================

INSERT INTO ontology_classes (class_name, prefix, description) VALUES
    ('Customer', 'customer', NULL),
    ('Store', 'store', NULL),
    ('Product', 'product', NULL),
    ('InventoryItem', 'inventory', NULL),
    ('Order', 'order', NULL),
    ('OrderLine', 'orderline', NULL),
    ('Courier', 'courier', NULL),
    ('DeliveryTask', 'task', NULL)
ON CONFLICT (class_name) DO NOTHING;

-- =============================================================================
-- Ontology Properties
-- =============================================================================

-- Customer properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'customer_name', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Customer'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'customer_email', id, 'string', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'Customer'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'customer_address', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Customer'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'home_store', c.id, 'entity_ref', s.id, FALSE, FALSE, NULL
FROM ontology_classes c, ontology_classes s
WHERE c.class_name = 'Customer' AND s.class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

-- Store properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_name', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_address', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_zone', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_status', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'store_capacity_orders_per_hour', id, 'int', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

-- Product properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'product_name', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'category', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'perishable', id, 'bool', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'unit_weight_grams', id, 'int', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'unit_price', id, 'float', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

-- InventoryItem properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'inventory_store', i.id, 'entity_ref', s.id, FALSE, TRUE, NULL
FROM ontology_classes i, ontology_classes s
WHERE i.class_name = 'InventoryItem' AND s.class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'inventory_product', i.id, 'entity_ref', p.id, FALSE, TRUE, NULL
FROM ontology_classes i, ontology_classes p
WHERE i.class_name = 'InventoryItem' AND p.class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'stock_level', id, 'int', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'replenishment_eta', id, 'timestamp', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

-- InventoryItem dynamic pricing properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'base_price', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'live_price', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'price_change', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'zone_adjustment', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'perishable_adjustment', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'local_stock_adjustment', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'popularity_adjustment', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'scarcity_adjustment', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'demand_multiplier', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'demand_premium', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'product_sale_count', id, 'int', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'product_total_stock', id, 'int', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

-- Order properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_number', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'placed_by', o.id, 'entity_ref', c.id, FALSE, TRUE, NULL
FROM ontology_classes o, ontology_classes c
WHERE o.class_name = 'Order' AND c.class_name = 'Customer'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_store', o.id, 'entity_ref', s.id, FALSE, TRUE, NULL
FROM ontology_classes o, ontology_classes s
WHERE o.class_name = 'Order' AND s.class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_status', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'delivery_window_start', id, 'timestamp', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'delivery_window_end', id, 'timestamp', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_total_amount', id, 'float', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_created_at', id, 'timestamp', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'delivered_at', id, 'timestamp', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

-- OrderLine properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_of_order', ol.id, 'entity_ref', o.id, FALSE, TRUE, NULL
FROM ontology_classes ol, ontology_classes o
WHERE ol.class_name = 'OrderLine' AND o.class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_product', ol.id, 'entity_ref', p.id, FALSE, TRUE, NULL
FROM ontology_classes ol, ontology_classes p
WHERE ol.class_name = 'OrderLine' AND p.class_name = 'Product'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'quantity', id, 'int', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_line_unit_price', id, 'float', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_amount', id, 'float', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_sequence', id, 'int', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'perishable_flag', id, 'bool', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_inventory_item', ol.id, 'entity_ref', inv.id, FALSE, FALSE, NULL
FROM ontology_classes ol, ontology_classes inv
WHERE ol.class_name = 'OrderLine' AND inv.class_name = 'InventoryItem'
ON CONFLICT (prop_name) DO NOTHING;

-- Courier properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'courier_name', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT c.prop_name, co.id, 'entity_ref', s.id, FALSE, FALSE, NULL
FROM (SELECT 'courier_home_store' AS prop_name) c, ontology_classes co, ontology_classes s
WHERE co.class_name = 'Courier' AND s.class_name = 'Store'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'vehicle_type', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'courier_status', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'courier_status_changed_at', id, 'timestamp', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'current_task', c.id, 'entity_ref', dt.id, FALSE, FALSE, NULL
FROM ontology_classes c, ontology_classes dt
WHERE c.class_name = 'Courier' AND dt.class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

-- DeliveryTask properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'task_of_order', dt.id, 'entity_ref', o.id, FALSE, TRUE, NULL
FROM ontology_classes dt, ontology_classes o
WHERE dt.class_name = 'DeliveryTask' AND o.class_name = 'Order'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'assigned_to', dt.id, 'entity_ref', c.id, FALSE, FALSE, NULL
FROM ontology_classes dt, ontology_classes c
WHERE dt.class_name = 'DeliveryTask' AND c.class_name = 'Courier'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'task_status', id, 'string', NULL, FALSE, TRUE, NULL
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'task_started_at', id, 'timestamp', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'task_completed_at', id, 'timestamp', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'eta', id, 'timestamp', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'route_sequence', id, 'int', NULL, FALSE, FALSE, NULL
FROM ontology_classes WHERE class_name = 'DeliveryTask'
ON CONFLICT (prop_name) DO NOTHING;
