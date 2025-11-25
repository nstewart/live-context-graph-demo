-- demo_data_freshmart.sql
-- FreshMart Demo Data - Realistic same-day delivery scenario

-- =============================================================================
-- Stores (5 locations)
-- =============================================================================
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
    -- Store BK-01: Brooklyn Main
    ('store:BK-01', 'store_name', 'FreshMart Brooklyn Main', 'string'),
    ('store:BK-01', 'store_address', '123 Atlantic Ave, Brooklyn, NY 11201', 'string'),
    ('store:BK-01', 'store_zone', 'BK', 'string'),
    ('store:BK-01', 'store_status', 'OPEN', 'string'),
    ('store:BK-01', 'store_capacity_orders_per_hour', '50', 'int'),
    -- Store BK-02: Brooklyn Heights
    ('store:BK-02', 'store_name', 'FreshMart Brooklyn Heights', 'string'),
    ('store:BK-02', 'store_address', '456 Court St, Brooklyn, NY 11231', 'string'),
    ('store:BK-02', 'store_zone', 'BK', 'string'),
    ('store:BK-02', 'store_status', 'OPEN', 'string'),
    ('store:BK-02', 'store_capacity_orders_per_hour', '35', 'int'),
    -- Store MAN-01: Manhattan Downtown
    ('store:MAN-01', 'store_name', 'FreshMart Manhattan Downtown', 'string'),
    ('store:MAN-01', 'store_address', '789 Broadway, New York, NY 10003', 'string'),
    ('store:MAN-01', 'store_zone', 'MAN', 'string'),
    ('store:MAN-01', 'store_status', 'OPEN', 'string'),
    ('store:MAN-01', 'store_capacity_orders_per_hour', '60', 'int'),
    -- Store MAN-02: Manhattan Midtown
    ('store:MAN-02', 'store_name', 'FreshMart Midtown', 'string'),
    ('store:MAN-02', 'store_address', '500 5th Ave, New York, NY 10110', 'string'),
    ('store:MAN-02', 'store_zone', 'MAN', 'string'),
    ('store:MAN-02', 'store_status', 'LIMITED', 'string'),
    ('store:MAN-02', 'store_capacity_orders_per_hour', '25', 'int'),
    -- Store QNS-01: Queens
    ('store:QNS-01', 'store_name', 'FreshMart Astoria', 'string'),
    ('store:QNS-01', 'store_address', '31-01 Steinway St, Astoria, NY 11103', 'string'),
    ('store:QNS-01', 'store_zone', 'QNS', 'string'),
    ('store:QNS-01', 'store_status', 'OPEN', 'string'),
    ('store:QNS-01', 'store_capacity_orders_per_hour', '40', 'int')
ON CONFLICT (subject_id, predicate, object_value) DO NOTHING;

-- =============================================================================
-- Products (15 items)
-- =============================================================================
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
    -- Dairy
    ('product:milk-1L', 'product_name', 'Organic Whole Milk 1L', 'string'),
    ('product:milk-1L', 'category', 'Dairy', 'string'),
    ('product:milk-1L', 'perishable', 'true', 'bool'),
    ('product:milk-1L', 'unit_weight_grams', '1030', 'int'),
    ('product:milk-1L', 'unit_price', '4.99', 'float'),

    ('product:eggs-12', 'product_name', 'Free Range Eggs (12 pack)', 'string'),
    ('product:eggs-12', 'category', 'Dairy', 'string'),
    ('product:eggs-12', 'perishable', 'true', 'bool'),
    ('product:eggs-12', 'unit_weight_grams', '720', 'int'),
    ('product:eggs-12', 'unit_price', '6.49', 'float'),

    ('product:cheese-cheddar', 'product_name', 'Sharp Cheddar Cheese 200g', 'string'),
    ('product:cheese-cheddar', 'category', 'Dairy', 'string'),
    ('product:cheese-cheddar', 'perishable', 'true', 'bool'),
    ('product:cheese-cheddar', 'unit_weight_grams', '200', 'int'),
    ('product:cheese-cheddar', 'unit_price', '5.99', 'float'),

    -- Produce
    ('product:bananas-bunch', 'product_name', 'Organic Bananas (bunch)', 'string'),
    ('product:bananas-bunch', 'category', 'Produce', 'string'),
    ('product:bananas-bunch', 'perishable', 'true', 'bool'),
    ('product:bananas-bunch', 'unit_weight_grams', '1000', 'int'),
    ('product:bananas-bunch', 'unit_price', '2.49', 'float'),

    ('product:apples-gala', 'product_name', 'Gala Apples (6 pack)', 'string'),
    ('product:apples-gala', 'category', 'Produce', 'string'),
    ('product:apples-gala', 'perishable', 'true', 'bool'),
    ('product:apples-gala', 'unit_weight_grams', '900', 'int'),
    ('product:apples-gala', 'unit_price', '4.99', 'float'),

    ('product:spinach-bag', 'product_name', 'Baby Spinach 5oz', 'string'),
    ('product:spinach-bag', 'category', 'Produce', 'string'),
    ('product:spinach-bag', 'perishable', 'true', 'bool'),
    ('product:spinach-bag', 'unit_weight_grams', '142', 'int'),
    ('product:spinach-bag', 'unit_price', '3.99', 'float'),

    -- Bakery
    ('product:bread-sourdough', 'product_name', 'Artisan Sourdough Loaf', 'string'),
    ('product:bread-sourdough', 'category', 'Bakery', 'string'),
    ('product:bread-sourdough', 'perishable', 'true', 'bool'),
    ('product:bread-sourdough', 'unit_weight_grams', '680', 'int'),
    ('product:bread-sourdough', 'unit_price', '5.49', 'float'),

    ('product:croissants-4', 'product_name', 'Butter Croissants (4 pack)', 'string'),
    ('product:croissants-4', 'category', 'Bakery', 'string'),
    ('product:croissants-4', 'perishable', 'true', 'bool'),
    ('product:croissants-4', 'unit_weight_grams', '280', 'int'),
    ('product:croissants-4', 'unit_price', '6.99', 'float'),

    -- Pantry
    ('product:pasta-penne', 'product_name', 'Penne Pasta 500g', 'string'),
    ('product:pasta-penne', 'category', 'Pantry', 'string'),
    ('product:pasta-penne', 'perishable', 'false', 'bool'),
    ('product:pasta-penne', 'unit_weight_grams', '500', 'int'),
    ('product:pasta-penne', 'unit_price', '2.99', 'float'),

    ('product:olive-oil', 'product_name', 'Extra Virgin Olive Oil 500ml', 'string'),
    ('product:olive-oil', 'category', 'Pantry', 'string'),
    ('product:olive-oil', 'perishable', 'false', 'bool'),
    ('product:olive-oil', 'unit_weight_grams', '460', 'int'),
    ('product:olive-oil', 'unit_price', '12.99', 'float'),

    ('product:rice-jasmine', 'product_name', 'Jasmine Rice 2lb', 'string'),
    ('product:rice-jasmine', 'category', 'Pantry', 'string'),
    ('product:rice-jasmine', 'perishable', 'false', 'bool'),
    ('product:rice-jasmine', 'unit_weight_grams', '907', 'int'),
    ('product:rice-jasmine', 'unit_price', '4.49', 'float'),

    -- Meat
    ('product:chicken-breast', 'product_name', 'Chicken Breast 1lb', 'string'),
    ('product:chicken-breast', 'category', 'Meat', 'string'),
    ('product:chicken-breast', 'perishable', 'true', 'bool'),
    ('product:chicken-breast', 'unit_weight_grams', '454', 'int'),
    ('product:chicken-breast', 'unit_price', '8.99', 'float'),

    ('product:ground-beef', 'product_name', 'Ground Beef 80/20 1lb', 'string'),
    ('product:ground-beef', 'category', 'Meat', 'string'),
    ('product:ground-beef', 'perishable', 'true', 'bool'),
    ('product:ground-beef', 'unit_weight_grams', '454', 'int'),
    ('product:ground-beef', 'unit_price', '7.99', 'float'),

    -- Beverages
    ('product:coffee-beans', 'product_name', 'Medium Roast Coffee Beans 12oz', 'string'),
    ('product:coffee-beans', 'category', 'Beverages', 'string'),
    ('product:coffee-beans', 'perishable', 'false', 'bool'),
    ('product:coffee-beans', 'unit_weight_grams', '340', 'int'),
    ('product:coffee-beans', 'unit_price', '11.99', 'float'),

    ('product:orange-juice', 'product_name', 'Fresh Squeezed OJ 64oz', 'string'),
    ('product:orange-juice', 'category', 'Beverages', 'string'),
    ('product:orange-juice', 'perishable', 'true', 'bool'),
    ('product:orange-juice', 'unit_weight_grams', '1893', 'int'),
    ('product:orange-juice', 'unit_price', '7.49', 'float')
ON CONFLICT (subject_id, predicate, object_value) DO NOTHING;

-- =============================================================================
-- Customers (15 customers)
-- =============================================================================
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
    ('customer:101', 'customer_name', 'Alex Thompson', 'string'),
    ('customer:101', 'customer_email', 'alex.thompson@email.com', 'string'),
    ('customer:101', 'customer_address', '234 Park Slope Ave, Brooklyn, NY 11215', 'string'),
    ('customer:101', 'home_store', 'store:BK-01', 'entity_ref'),

    ('customer:102', 'customer_name', 'Maria Garcia', 'string'),
    ('customer:102', 'customer_email', 'maria.g@email.com', 'string'),
    ('customer:102', 'customer_address', '567 Clinton St, Brooklyn, NY 11231', 'string'),
    ('customer:102', 'home_store', 'store:BK-02', 'entity_ref'),

    ('customer:103', 'customer_name', 'James Wilson', 'string'),
    ('customer:103', 'customer_email', 'jwilson@email.com', 'string'),
    ('customer:103', 'customer_address', '890 Greenwich St, New York, NY 10014', 'string'),
    ('customer:103', 'home_store', 'store:MAN-01', 'entity_ref'),

    ('customer:104', 'customer_name', 'Sarah Chen', 'string'),
    ('customer:104', 'customer_email', 'sarah.chen@email.com', 'string'),
    ('customer:104', 'customer_address', '123 E 45th St, New York, NY 10017', 'string'),
    ('customer:104', 'home_store', 'store:MAN-02', 'entity_ref'),

    ('customer:105', 'customer_name', 'Michael Brown', 'string'),
    ('customer:105', 'customer_email', 'mbrown@email.com', 'string'),
    ('customer:105', 'customer_address', '456 Ditmars Blvd, Astoria, NY 11105', 'string'),
    ('customer:105', 'home_store', 'store:QNS-01', 'entity_ref'),

    ('customer:106', 'customer_name', 'Emily Davis', 'string'),
    ('customer:106', 'customer_email', 'emily.d@email.com', 'string'),
    ('customer:106', 'customer_address', '789 Flatbush Ave, Brooklyn, NY 11226', 'string'),
    ('customer:106', 'home_store', 'store:BK-01', 'entity_ref'),

    ('customer:107', 'customer_name', 'David Kim', 'string'),
    ('customer:107', 'customer_email', 'dkim@email.com', 'string'),
    ('customer:107', 'customer_address', '321 Henry St, Brooklyn, NY 11201', 'string'),
    ('customer:107', 'home_store', 'store:BK-02', 'entity_ref'),

    ('customer:108', 'customer_name', 'Jennifer Martinez', 'string'),
    ('customer:108', 'customer_email', 'jmartinez@email.com', 'string'),
    ('customer:108', 'customer_address', '654 W 23rd St, New York, NY 10011', 'string'),
    ('customer:108', 'home_store', 'store:MAN-01', 'entity_ref'),

    ('customer:109', 'customer_name', 'Robert Taylor', 'string'),
    ('customer:109', 'customer_email', 'rtaylor@email.com', 'string'),
    ('customer:109', 'customer_address', '987 Lexington Ave, New York, NY 10021', 'string'),
    ('customer:109', 'home_store', 'store:MAN-02', 'entity_ref'),

    ('customer:110', 'customer_name', 'Lisa Anderson', 'string'),
    ('customer:110', 'customer_email', 'landerson@email.com', 'string'),
    ('customer:110', 'customer_address', '147 30th Ave, Astoria, NY 11102', 'string'),
    ('customer:110', 'home_store', 'store:QNS-01', 'entity_ref'),

    ('customer:111', 'customer_name', 'Christopher Lee', 'string'),
    ('customer:111', 'customer_email', 'clee@email.com', 'string'),
    ('customer:111', 'customer_address', '258 Bergen St, Brooklyn, NY 11217', 'string'),
    ('customer:111', 'home_store', 'store:BK-01', 'entity_ref'),

    ('customer:112', 'customer_name', 'Amanda White', 'string'),
    ('customer:112', 'customer_email', 'awhite@email.com', 'string'),
    ('customer:112', 'customer_address', '369 Smith St, Brooklyn, NY 11231', 'string'),
    ('customer:112', 'home_store', 'store:BK-02', 'entity_ref'),

    ('customer:113', 'customer_name', 'Daniel Harris', 'string'),
    ('customer:113', 'customer_email', 'dharris@email.com', 'string'),
    ('customer:113', 'customer_address', '741 Houston St, New York, NY 10014', 'string'),
    ('customer:113', 'home_store', 'store:MAN-01', 'entity_ref'),

    ('customer:114', 'customer_name', 'Michelle Clark', 'string'),
    ('customer:114', 'customer_email', 'mclark@email.com', 'string'),
    ('customer:114', 'customer_address', '852 Park Ave, New York, NY 10021', 'string'),
    ('customer:114', 'home_store', 'store:MAN-02', 'entity_ref'),

    ('customer:115', 'customer_name', 'Kevin Johnson', 'string'),
    ('customer:115', 'customer_email', 'kjohnson@email.com', 'string'),
    ('customer:115', 'customer_address', '963 Broadway, Astoria, NY 11106', 'string'),
    ('customer:115', 'home_store', 'store:QNS-01', 'entity_ref')
ON CONFLICT (subject_id, predicate, object_value) DO NOTHING;

-- =============================================================================
-- Inventory (sample inventory for stores)
-- =============================================================================
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
    -- Store BK-01 inventory
    ('inventory:BK01-milk', 'inventory_store', 'store:BK-01', 'entity_ref'),
    ('inventory:BK01-milk', 'inventory_product', 'product:milk-1L', 'entity_ref'),
    ('inventory:BK01-milk', 'stock_level', '45', 'int'),

    ('inventory:BK01-eggs', 'inventory_store', 'store:BK-01', 'entity_ref'),
    ('inventory:BK01-eggs', 'inventory_product', 'product:eggs-12', 'entity_ref'),
    ('inventory:BK01-eggs', 'stock_level', '30', 'int'),

    ('inventory:BK01-bread', 'inventory_store', 'store:BK-01', 'entity_ref'),
    ('inventory:BK01-bread', 'inventory_product', 'product:bread-sourdough', 'entity_ref'),
    ('inventory:BK01-bread', 'stock_level', '15', 'int'),

    ('inventory:BK01-chicken', 'inventory_store', 'store:BK-01', 'entity_ref'),
    ('inventory:BK01-chicken', 'inventory_product', 'product:chicken-breast', 'entity_ref'),
    ('inventory:BK01-chicken', 'stock_level', '25', 'int'),

    -- Store MAN-01 inventory
    ('inventory:MAN01-milk', 'inventory_store', 'store:MAN-01', 'entity_ref'),
    ('inventory:MAN01-milk', 'inventory_product', 'product:milk-1L', 'entity_ref'),
    ('inventory:MAN01-milk', 'stock_level', '60', 'int'),

    ('inventory:MAN01-coffee', 'inventory_store', 'store:MAN-01', 'entity_ref'),
    ('inventory:MAN01-coffee', 'inventory_product', 'product:coffee-beans', 'entity_ref'),
    ('inventory:MAN01-coffee', 'stock_level', '40', 'int'),

    ('inventory:MAN01-croissants', 'inventory_store', 'store:MAN-01', 'entity_ref'),
    ('inventory:MAN01-croissants', 'inventory_product', 'product:croissants-4', 'entity_ref'),
    ('inventory:MAN01-croissants', 'stock_level', '20', 'int'),

    -- Low stock example
    ('inventory:BK02-spinach', 'inventory_store', 'store:BK-02', 'entity_ref'),
    ('inventory:BK02-spinach', 'inventory_product', 'product:spinach-bag', 'entity_ref'),
    ('inventory:BK02-spinach', 'stock_level', '3', 'int'),
    ('inventory:BK02-spinach', 'replenishment_eta', '2025-11-22T14:00:00Z', 'timestamp')
ON CONFLICT (subject_id, predicate, object_value) DO NOTHING;

-- =============================================================================
-- Couriers (8 couriers)
-- =============================================================================
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
    ('courier:C01', 'courier_name', 'Tony Rivera', 'string'),
    ('courier:C01', 'courier_home_store', 'store:BK-01', 'entity_ref'),
    ('courier:C01', 'vehicle_type', 'BIKE', 'string'),
    ('courier:C01', 'courier_status', 'ON_DELIVERY', 'string'),

    ('courier:C02', 'courier_name', 'Linda Park', 'string'),
    ('courier:C02', 'courier_home_store', 'store:BK-01', 'entity_ref'),
    ('courier:C02', 'vehicle_type', 'CAR', 'string'),
    ('courier:C02', 'courier_status', 'AVAILABLE', 'string'),

    ('courier:C03', 'courier_name', 'Marcus Johnson', 'string'),
    ('courier:C03', 'courier_home_store', 'store:BK-02', 'entity_ref'),
    ('courier:C03', 'vehicle_type', 'BIKE', 'string'),
    ('courier:C03', 'courier_status', 'AVAILABLE', 'string'),

    ('courier:C04', 'courier_name', 'Sofia Reyes', 'string'),
    ('courier:C04', 'courier_home_store', 'store:MAN-01', 'entity_ref'),
    ('courier:C04', 'vehicle_type', 'BIKE', 'string'),
    ('courier:C04', 'courier_status', 'ON_DELIVERY', 'string'),

    ('courier:C05', 'courier_name', 'Jason Wu', 'string'),
    ('courier:C05', 'courier_home_store', 'store:MAN-01', 'entity_ref'),
    ('courier:C05', 'vehicle_type', 'CAR', 'string'),
    ('courier:C05', 'courier_status', 'AVAILABLE', 'string'),

    ('courier:C06', 'courier_name', 'Rachel Green', 'string'),
    ('courier:C06', 'courier_home_store', 'store:MAN-02', 'entity_ref'),
    ('courier:C06', 'vehicle_type', 'BIKE', 'string'),
    ('courier:C06', 'courier_status', 'OFF_SHIFT', 'string'),

    ('courier:C07', 'courier_name', 'Omar Hassan', 'string'),
    ('courier:C07', 'courier_home_store', 'store:QNS-01', 'entity_ref'),
    ('courier:C07', 'vehicle_type', 'VAN', 'string'),
    ('courier:C07', 'courier_status', 'ON_DELIVERY', 'string'),

    ('courier:C08', 'courier_name', 'Nina Patel', 'string'),
    ('courier:C08', 'courier_home_store', 'store:QNS-01', 'entity_ref'),
    ('courier:C08', 'vehicle_type', 'BIKE', 'string'),
    ('courier:C08', 'courier_status', 'AVAILABLE', 'string')
ON CONFLICT (subject_id, predicate, object_value) DO NOTHING;

-- =============================================================================
-- Orders (20 orders with various statuses)
-- =============================================================================
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
    -- Order FM-1001: Delivered
    ('order:FM-1001', 'order_number', 'FM-1001', 'string'),
    ('order:FM-1001', 'placed_by', 'customer:101', 'entity_ref'),
    ('order:FM-1001', 'order_store', 'store:BK-01', 'entity_ref'),
    ('order:FM-1001', 'order_status', 'DELIVERED', 'string'),
    ('order:FM-1001', 'delivery_window_start', '2025-11-22T09:00:00Z', 'timestamp'),
    ('order:FM-1001', 'delivery_window_end', '2025-11-22T11:00:00Z', 'timestamp'),
    ('order:FM-1001', 'order_total_amount', '24.47', 'float'),

    -- Order FM-1002: Out for delivery
    ('order:FM-1002', 'order_number', 'FM-1002', 'string'),
    ('order:FM-1002', 'placed_by', 'customer:102', 'entity_ref'),
    ('order:FM-1002', 'order_store', 'store:BK-02', 'entity_ref'),
    ('order:FM-1002', 'order_status', 'OUT_FOR_DELIVERY', 'string'),
    ('order:FM-1002', 'delivery_window_start', '2025-11-22T12:00:00Z', 'timestamp'),
    ('order:FM-1002', 'delivery_window_end', '2025-11-22T14:00:00Z', 'timestamp'),
    ('order:FM-1002', 'order_total_amount', '35.96', 'float'),

    -- Order FM-1003: Picking
    ('order:FM-1003', 'order_number', 'FM-1003', 'string'),
    ('order:FM-1003', 'placed_by', 'customer:103', 'entity_ref'),
    ('order:FM-1003', 'order_store', 'store:MAN-01', 'entity_ref'),
    ('order:FM-1003', 'order_status', 'PICKING', 'string'),
    ('order:FM-1003', 'delivery_window_start', '2025-11-22T14:00:00Z', 'timestamp'),
    ('order:FM-1003', 'delivery_window_end', '2025-11-22T16:00:00Z', 'timestamp'),
    ('order:FM-1003', 'order_total_amount', '52.45', 'float'),

    -- Order FM-1004: Created (new order)
    ('order:FM-1004', 'order_number', 'FM-1004', 'string'),
    ('order:FM-1004', 'placed_by', 'customer:104', 'entity_ref'),
    ('order:FM-1004', 'order_store', 'store:MAN-02', 'entity_ref'),
    ('order:FM-1004', 'order_status', 'CREATED', 'string'),
    ('order:FM-1004', 'delivery_window_start', '2025-11-22T17:00:00Z', 'timestamp'),
    ('order:FM-1004', 'delivery_window_end', '2025-11-22T19:00:00Z', 'timestamp'),
    ('order:FM-1004', 'order_total_amount', '28.97', 'float'),

    -- Order FM-1005: Out for delivery
    ('order:FM-1005', 'order_number', 'FM-1005', 'string'),
    ('order:FM-1005', 'placed_by', 'customer:105', 'entity_ref'),
    ('order:FM-1005', 'order_store', 'store:QNS-01', 'entity_ref'),
    ('order:FM-1005', 'order_status', 'OUT_FOR_DELIVERY', 'string'),
    ('order:FM-1005', 'delivery_window_start', '2025-11-22T11:00:00Z', 'timestamp'),
    ('order:FM-1005', 'delivery_window_end', '2025-11-22T13:00:00Z', 'timestamp'),
    ('order:FM-1005', 'order_total_amount', '41.94', 'float'),

    -- Order FM-1006: Cancelled
    ('order:FM-1006', 'order_number', 'FM-1006', 'string'),
    ('order:FM-1006', 'placed_by', 'customer:106', 'entity_ref'),
    ('order:FM-1006', 'order_store', 'store:BK-01', 'entity_ref'),
    ('order:FM-1006', 'order_status', 'CANCELLED', 'string'),
    ('order:FM-1006', 'delivery_window_start', '2025-11-22T10:00:00Z', 'timestamp'),
    ('order:FM-1006', 'delivery_window_end', '2025-11-22T12:00:00Z', 'timestamp'),
    ('order:FM-1006', 'order_total_amount', '15.48', 'float'),

    -- Order FM-1007: Picking
    ('order:FM-1007', 'order_number', 'FM-1007', 'string'),
    ('order:FM-1007', 'placed_by', 'customer:107', 'entity_ref'),
    ('order:FM-1007', 'order_store', 'store:BK-02', 'entity_ref'),
    ('order:FM-1007', 'order_status', 'PICKING', 'string'),
    ('order:FM-1007', 'delivery_window_start', '2025-11-22T15:00:00Z', 'timestamp'),
    ('order:FM-1007', 'delivery_window_end', '2025-11-22T17:00:00Z', 'timestamp'),
    ('order:FM-1007', 'order_total_amount', '67.43', 'float'),

    -- Order FM-1008: Created
    ('order:FM-1008', 'order_number', 'FM-1008', 'string'),
    ('order:FM-1008', 'placed_by', 'customer:108', 'entity_ref'),
    ('order:FM-1008', 'order_store', 'store:MAN-01', 'entity_ref'),
    ('order:FM-1008', 'order_status', 'CREATED', 'string'),
    ('order:FM-1008', 'delivery_window_start', '2025-11-22T18:00:00Z', 'timestamp'),
    ('order:FM-1008', 'delivery_window_end', '2025-11-22T20:00:00Z', 'timestamp'),
    ('order:FM-1008', 'order_total_amount', '33.96', 'float'),

    -- Order FM-1009: Delivered
    ('order:FM-1009', 'order_number', 'FM-1009', 'string'),
    ('order:FM-1009', 'placed_by', 'customer:109', 'entity_ref'),
    ('order:FM-1009', 'order_store', 'store:MAN-02', 'entity_ref'),
    ('order:FM-1009', 'order_status', 'DELIVERED', 'string'),
    ('order:FM-1009', 'delivery_window_start', '2025-11-22T08:00:00Z', 'timestamp'),
    ('order:FM-1009', 'delivery_window_end', '2025-11-22T10:00:00Z', 'timestamp'),
    ('order:FM-1009', 'order_total_amount', '19.97', 'float'),

    -- Order FM-1010: Out for delivery (at risk - window ending soon)
    ('order:FM-1010', 'order_number', 'FM-1010', 'string'),
    ('order:FM-1010', 'placed_by', 'customer:110', 'entity_ref'),
    ('order:FM-1010', 'order_store', 'store:QNS-01', 'entity_ref'),
    ('order:FM-1010', 'order_status', 'OUT_FOR_DELIVERY', 'string'),
    ('order:FM-1010', 'delivery_window_start', '2025-11-22T10:00:00Z', 'timestamp'),
    ('order:FM-1010', 'delivery_window_end', '2025-11-22T12:00:00Z', 'timestamp'),
    ('order:FM-1010', 'order_total_amount', '45.94', 'float'),

    -- Additional orders for volume
    ('order:FM-1011', 'order_number', 'FM-1011', 'string'),
    ('order:FM-1011', 'placed_by', 'customer:111', 'entity_ref'),
    ('order:FM-1011', 'order_store', 'store:BK-01', 'entity_ref'),
    ('order:FM-1011', 'order_status', 'PICKING', 'string'),
    ('order:FM-1011', 'delivery_window_start', '2025-11-22T16:00:00Z', 'timestamp'),
    ('order:FM-1011', 'delivery_window_end', '2025-11-22T18:00:00Z', 'timestamp'),
    ('order:FM-1011', 'order_total_amount', '38.45', 'float'),

    ('order:FM-1012', 'order_number', 'FM-1012', 'string'),
    ('order:FM-1012', 'placed_by', 'customer:112', 'entity_ref'),
    ('order:FM-1012', 'order_store', 'store:BK-02', 'entity_ref'),
    ('order:FM-1012', 'order_status', 'CREATED', 'string'),
    ('order:FM-1012', 'delivery_window_start', '2025-11-22T19:00:00Z', 'timestamp'),
    ('order:FM-1012', 'delivery_window_end', '2025-11-22T21:00:00Z', 'timestamp'),
    ('order:FM-1012', 'order_total_amount', '22.47', 'float'),

    ('order:FM-1013', 'order_number', 'FM-1013', 'string'),
    ('order:FM-1013', 'placed_by', 'customer:113', 'entity_ref'),
    ('order:FM-1013', 'order_store', 'store:MAN-01', 'entity_ref'),
    ('order:FM-1013', 'order_status', 'OUT_FOR_DELIVERY', 'string'),
    ('order:FM-1013', 'delivery_window_start', '2025-11-22T13:00:00Z', 'timestamp'),
    ('order:FM-1013', 'delivery_window_end', '2025-11-22T15:00:00Z', 'timestamp'),
    ('order:FM-1013', 'order_total_amount', '56.92', 'float'),

    ('order:FM-1014', 'order_number', 'FM-1014', 'string'),
    ('order:FM-1014', 'placed_by', 'customer:114', 'entity_ref'),
    ('order:FM-1014', 'order_store', 'store:MAN-02', 'entity_ref'),
    ('order:FM-1014', 'order_status', 'PICKING', 'string'),
    ('order:FM-1014', 'delivery_window_start', '2025-11-22T14:00:00Z', 'timestamp'),
    ('order:FM-1014', 'delivery_window_end', '2025-11-22T16:00:00Z', 'timestamp'),
    ('order:FM-1014', 'order_total_amount', '31.46', 'float'),

    ('order:FM-1015', 'order_number', 'FM-1015', 'string'),
    ('order:FM-1015', 'placed_by', 'customer:115', 'entity_ref'),
    ('order:FM-1015', 'order_store', 'store:QNS-01', 'entity_ref'),
    ('order:FM-1015', 'order_status', 'CREATED', 'string'),
    ('order:FM-1015', 'delivery_window_start', '2025-11-22T17:00:00Z', 'timestamp'),
    ('order:FM-1015', 'delivery_window_end', '2025-11-22T19:00:00Z', 'timestamp'),
    ('order:FM-1015', 'order_total_amount', '48.93', 'float')
ON CONFLICT (subject_id, predicate, object_value) DO NOTHING;

-- =============================================================================
-- Order Lines (sample lines for orders)
-- =============================================================================
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
    -- Order FM-1001 lines
    ('orderline:FM1001-1', 'line_of_order', 'order:FM-1001', 'entity_ref'),
    ('orderline:FM1001-1', 'line_product', 'product:milk-1L', 'entity_ref'),
    ('orderline:FM1001-1', 'quantity', '2', 'int'),
    ('orderline:FM1001-1', 'line_amount', '9.98', 'float'),

    ('orderline:FM1001-2', 'line_of_order', 'order:FM-1001', 'entity_ref'),
    ('orderline:FM1001-2', 'line_product', 'product:bread-sourdough', 'entity_ref'),
    ('orderline:FM1001-2', 'quantity', '1', 'int'),
    ('orderline:FM1001-2', 'line_amount', '5.49', 'float'),

    ('orderline:FM1001-3', 'line_of_order', 'order:FM-1001', 'entity_ref'),
    ('orderline:FM1001-3', 'line_product', 'product:bananas-bunch', 'entity_ref'),
    ('orderline:FM1001-3', 'quantity', '2', 'int'),
    ('orderline:FM1001-3', 'line_amount', '4.98', 'float'),

    -- Order FM-1002 lines
    ('orderline:FM1002-1', 'line_of_order', 'order:FM-1002', 'entity_ref'),
    ('orderline:FM1002-1', 'line_product', 'product:chicken-breast', 'entity_ref'),
    ('orderline:FM1002-1', 'quantity', '2', 'int'),
    ('orderline:FM1002-1', 'line_amount', '17.98', 'float'),

    ('orderline:FM1002-2', 'line_of_order', 'order:FM-1002', 'entity_ref'),
    ('orderline:FM1002-2', 'line_product', 'product:spinach-bag', 'entity_ref'),
    ('orderline:FM1002-2', 'quantity', '3', 'int'),
    ('orderline:FM1002-2', 'line_amount', '11.97', 'float'),

    -- Order FM-1003 lines
    ('orderline:FM1003-1', 'line_of_order', 'order:FM-1003', 'entity_ref'),
    ('orderline:FM1003-1', 'line_product', 'product:coffee-beans', 'entity_ref'),
    ('orderline:FM1003-1', 'quantity', '2', 'int'),
    ('orderline:FM1003-1', 'line_amount', '23.98', 'float'),

    ('orderline:FM1003-2', 'line_of_order', 'order:FM-1003', 'entity_ref'),
    ('orderline:FM1003-2', 'line_product', 'product:croissants-4', 'entity_ref'),
    ('orderline:FM1003-2', 'quantity', '2', 'int'),
    ('orderline:FM1003-2', 'line_amount', '13.98', 'float'),

    ('orderline:FM1003-3', 'line_of_order', 'order:FM-1003', 'entity_ref'),
    ('orderline:FM1003-3', 'line_product', 'product:orange-juice', 'entity_ref'),
    ('orderline:FM1003-3', 'quantity', '1', 'int'),
    ('orderline:FM1003-3', 'line_amount', '7.49', 'float'),

    -- Order FM-1005 lines
    ('orderline:FM1005-1', 'line_of_order', 'order:FM-1005', 'entity_ref'),
    ('orderline:FM1005-1', 'line_product', 'product:ground-beef', 'entity_ref'),
    ('orderline:FM1005-1', 'quantity', '2', 'int'),
    ('orderline:FM1005-1', 'line_amount', '15.98', 'float'),

    ('orderline:FM1005-2', 'line_of_order', 'order:FM-1005', 'entity_ref'),
    ('orderline:FM1005-2', 'line_product', 'product:pasta-penne', 'entity_ref'),
    ('orderline:FM1005-2', 'quantity', '2', 'int'),
    ('orderline:FM1005-2', 'line_amount', '5.98', 'float'),

    ('orderline:FM1005-3', 'line_of_order', 'order:FM-1005', 'entity_ref'),
    ('orderline:FM1005-3', 'line_product', 'product:olive-oil', 'entity_ref'),
    ('orderline:FM1005-3', 'quantity', '1', 'int'),
    ('orderline:FM1005-3', 'line_amount', '12.99', 'float')
ON CONFLICT (subject_id, predicate, object_value) DO NOTHING;

-- =============================================================================
-- Delivery Tasks
-- =============================================================================
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
    -- Task for FM-1002 (out for delivery)
    ('task:T1002', 'task_of_order', 'order:FM-1002', 'entity_ref'),
    ('task:T1002', 'assigned_to', 'courier:C03', 'entity_ref'),
    ('task:T1002', 'task_status', 'IN_PROGRESS', 'string'),
    ('task:T1002', 'eta', '2025-11-22T13:30:00Z', 'timestamp'),
    ('task:T1002', 'route_sequence', '1', 'int'),

    -- Task for FM-1005 (out for delivery)
    ('task:T1005', 'task_of_order', 'order:FM-1005', 'entity_ref'),
    ('task:T1005', 'assigned_to', 'courier:C07', 'entity_ref'),
    ('task:T1005', 'task_status', 'IN_PROGRESS', 'string'),
    ('task:T1005', 'eta', '2025-11-22T12:15:00Z', 'timestamp'),
    ('task:T1005', 'route_sequence', '1', 'int'),

    -- Task for FM-1010 (out for delivery - at risk)
    ('task:T1010', 'task_of_order', 'order:FM-1010', 'entity_ref'),
    ('task:T1010', 'assigned_to', 'courier:C07', 'entity_ref'),
    ('task:T1010', 'task_status', 'IN_PROGRESS', 'string'),
    ('task:T1010', 'eta', '2025-11-22T11:45:00Z', 'timestamp'),
    ('task:T1010', 'route_sequence', '2', 'int'),

    -- Task for FM-1013 (out for delivery)
    ('task:T1013', 'task_of_order', 'order:FM-1013', 'entity_ref'),
    ('task:T1013', 'assigned_to', 'courier:C04', 'entity_ref'),
    ('task:T1013', 'task_status', 'IN_PROGRESS', 'string'),
    ('task:T1013', 'eta', '2025-11-22T14:20:00Z', 'timestamp'),
    ('task:T1013', 'route_sequence', '1', 'int'),

    -- Task for FM-1001 (completed)
    ('task:T1001', 'task_of_order', 'order:FM-1001', 'entity_ref'),
    ('task:T1001', 'assigned_to', 'courier:C01', 'entity_ref'),
    ('task:T1001', 'task_status', 'COMPLETED', 'string'),
    ('task:T1001', 'eta', '2025-11-22T10:30:00Z', 'timestamp'),
    ('task:T1001', 'route_sequence', '1', 'int'),

    -- Pending tasks for picking orders
    ('task:T1003', 'task_of_order', 'order:FM-1003', 'entity_ref'),
    ('task:T1003', 'task_status', 'PENDING', 'string'),

    ('task:T1007', 'task_of_order', 'order:FM-1007', 'entity_ref'),
    ('task:T1007', 'task_status', 'PENDING', 'string'),

    ('task:T1011', 'task_of_order', 'order:FM-1011', 'entity_ref'),
    ('task:T1011', 'task_status', 'PENDING', 'string'),

    ('task:T1014', 'task_of_order', 'order:FM-1014', 'entity_ref'),
    ('task:T1014', 'task_status', 'PENDING', 'string')
ON CONFLICT (subject_id, predicate, object_value) DO NOTHING;
