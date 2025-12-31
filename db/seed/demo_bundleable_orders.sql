-- demo_bundleable_orders.sql
-- Seed data for demonstrating delivery bundling with mutually recursive views
-- These orders are at the same store with overlapping delivery windows

-- =============================================================================
-- Bundleable Orders at FreshMart Manhattan 1 (store:MAN-01)
-- 4 orders with overlapping delivery windows that will bundle together
-- =============================================================================

-- Order FM-000501: Customer 1, delivery window +1h to +3h
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
('order:FM-000501', 'order_number', 'FM-000501', 'string'),
('order:FM-000501', 'order_status', 'CREATED', 'string'),
('order:FM-000501', 'order_store', 'store:MAN-01', 'entity_ref'),
('order:FM-000501', 'placed_by', 'customer:00001', 'entity_ref'),
('order:FM-000501', 'delivery_window_start', (NOW() + INTERVAL '1 hour')::text, 'timestamp'),
('order:FM-000501', 'delivery_window_end', (NOW() + INTERVAL '3 hours')::text, 'timestamp'),
('order:FM-000501', 'order_total_amount', '6.75', 'float'),
('order:FM-000501', 'order_created_at', NOW()::text, 'timestamp')
ON CONFLICT DO NOTHING;

-- Order FM-000502: Customer 2, delivery window +1.5h to +3.5h (overlaps with 501)
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
('order:FM-000502', 'order_number', 'FM-000502', 'string'),
('order:FM-000502', 'order_status', 'CREATED', 'string'),
('order:FM-000502', 'order_store', 'store:MAN-01', 'entity_ref'),
('order:FM-000502', 'placed_by', 'customer:00002', 'entity_ref'),
('order:FM-000502', 'delivery_window_start', (NOW() + INTERVAL '1.5 hours')::text, 'timestamp'),
('order:FM-000502', 'delivery_window_end', (NOW() + INTERVAL '3.5 hours')::text, 'timestamp'),
('order:FM-000502', 'order_total_amount', '6.94', 'float'),
('order:FM-000502', 'order_created_at', NOW()::text, 'timestamp')
ON CONFLICT DO NOTHING;

-- Order FM-000503: Customer 3, delivery window +2h to +4h (overlaps with 501, 502)
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
('order:FM-000503', 'order_number', 'FM-000503', 'string'),
('order:FM-000503', 'order_status', 'CREATED', 'string'),
('order:FM-000503', 'order_store', 'store:MAN-01', 'entity_ref'),
('order:FM-000503', 'placed_by', 'customer:00003', 'entity_ref'),
('order:FM-000503', 'delivery_window_start', (NOW() + INTERVAL '2 hours')::text, 'timestamp'),
('order:FM-000503', 'delivery_window_end', (NOW() + INTERVAL '4 hours')::text, 'timestamp'),
('order:FM-000503', 'order_total_amount', '8.65', 'float'),
('order:FM-000503', 'order_created_at', NOW()::text, 'timestamp')
ON CONFLICT DO NOTHING;

-- Order FM-000504: Customer 1, delivery window +2.5h to +4.5h (overlaps with 502, 503)
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
('order:FM-000504', 'order_number', 'FM-000504', 'string'),
('order:FM-000504', 'order_status', 'CREATED', 'string'),
('order:FM-000504', 'order_store', 'store:MAN-01', 'entity_ref'),
('order:FM-000504', 'placed_by', 'customer:00001', 'entity_ref'),
('order:FM-000504', 'delivery_window_start', (NOW() + INTERVAL '2.5 hours')::text, 'timestamp'),
('order:FM-000504', 'delivery_window_end', (NOW() + INTERVAL '4.5 hours')::text, 'timestamp'),
('order:FM-000504', 'order_total_amount', '8.45', 'float'),
('order:FM-000504', 'order_created_at', NOW()::text, 'timestamp')
ON CONFLICT DO NOTHING;

-- =============================================================================
-- Order Lines for Bundleable Orders
-- Using lightweight products available at MAN-01
-- =============================================================================

-- Order lines for FM-000501: Serrano Peppers (3) + Basil (2)
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
('orderline:FM-000501-1', 'line_of_order', 'order:FM-000501', 'entity_ref'),
('orderline:FM-000501-1', 'line_product', 'product:prod0148', 'entity_ref'),
('orderline:FM-000501-1', 'quantity', '3', 'int'),
('orderline:FM-000501-1', 'order_line_unit_price', '0.59', 'float'),
('orderline:FM-000501-1', 'line_sequence', '1', 'int'),
('orderline:FM-000501-2', 'line_of_order', 'order:FM-000501', 'entity_ref'),
('orderline:FM-000501-2', 'line_product', 'product:prod0213', 'entity_ref'),
('orderline:FM-000501-2', 'quantity', '2', 'int'),
('orderline:FM-000501-2', 'order_line_unit_price', '2.49', 'float'),
('orderline:FM-000501-2', 'line_sequence', '2', 'int')
ON CONFLICT DO NOTHING;

-- Order lines for FM-000502: Jalapeno (4) + Mint (2)
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
('orderline:FM-000502-1', 'line_of_order', 'order:FM-000502', 'entity_ref'),
('orderline:FM-000502-1', 'line_product', 'product:prod0147', 'entity_ref'),
('orderline:FM-000502-1', 'quantity', '4', 'int'),
('orderline:FM-000502-1', 'order_line_unit_price', '0.49', 'float'),
('orderline:FM-000502-1', 'line_sequence', '1', 'int'),
('orderline:FM-000502-2', 'line_of_order', 'order:FM-000502', 'entity_ref'),
('orderline:FM-000502-2', 'line_product', 'product:prod0216', 'entity_ref'),
('orderline:FM-000502-2', 'quantity', '2', 'int'),
('orderline:FM-000502-2', 'order_line_unit_price', '2.49', 'float'),
('orderline:FM-000502-2', 'line_sequence', '2', 'int')
ON CONFLICT DO NOTHING;

-- Order lines for FM-000503: Dill (3) + Serrano (2)
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
('orderline:FM-000503-1', 'line_of_order', 'order:FM-000503', 'entity_ref'),
('orderline:FM-000503-1', 'line_product', 'product:prod0217', 'entity_ref'),
('orderline:FM-000503-1', 'quantity', '3', 'int'),
('orderline:FM-000503-1', 'order_line_unit_price', '2.49', 'float'),
('orderline:FM-000503-1', 'line_sequence', '1', 'int'),
('orderline:FM-000503-2', 'line_of_order', 'order:FM-000503', 'entity_ref'),
('orderline:FM-000503-2', 'line_product', 'product:prod0148', 'entity_ref'),
('orderline:FM-000503-2', 'quantity', '2', 'int'),
('orderline:FM-000503-2', 'order_line_unit_price', '0.59', 'float'),
('orderline:FM-000503-2', 'line_sequence', '2', 'int')
ON CONFLICT DO NOTHING;

-- Order lines for FM-000504: Basil (3) + Jalapeno (2)
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
('orderline:FM-000504-1', 'line_of_order', 'order:FM-000504', 'entity_ref'),
('orderline:FM-000504-1', 'line_product', 'product:prod0213', 'entity_ref'),
('orderline:FM-000504-1', 'quantity', '3', 'int'),
('orderline:FM-000504-1', 'order_line_unit_price', '2.49', 'float'),
('orderline:FM-000504-1', 'line_sequence', '1', 'int'),
('orderline:FM-000504-2', 'line_of_order', 'order:FM-000504', 'entity_ref'),
('orderline:FM-000504-2', 'line_product', 'product:prod0147', 'entity_ref'),
('orderline:FM-000504-2', 'quantity', '2', 'int'),
('orderline:FM-000504-2', 'order_line_unit_price', '0.49', 'float'),
('orderline:FM-000504-2', 'line_sequence', '2', 'int')
ON CONFLICT DO NOTHING;
