-- 060_orderline_ontology.sql
-- Migration: Add OrderLine entity with all required properties
-- Phase 1, Issue #1: Add OrderLine Entity to Ontology

-- =============================================================================
-- Update OrderLine class prefix
-- =============================================================================
-- The OrderLine class should use 'orderline' prefix (not 'order_line')
-- for consistency with ID format: orderline:{order_number}-{sequence}
UPDATE ontology_classes
SET prefix = 'orderline'
WHERE class_name = 'OrderLine' AND prefix = 'order_line';

-- =============================================================================
-- Add missing OrderLine properties
-- =============================================================================

-- order_line_unit_price property (price snapshot at order time)
-- Note: Using unique property name since prop_name has UNIQUE constraint
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'order_line_unit_price', id, 'float', NULL, FALSE, TRUE, 'Unit price at order time (price snapshot)'
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

-- line_sequence property (display order)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'line_sequence', id, 'int', NULL, FALSE, TRUE, 'Display sequence within order'
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

-- perishable_flag property (denormalized from product)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_multi_valued, is_required, description)
SELECT 'perishable_flag', id, 'bool', NULL, FALSE, TRUE, 'Denormalized perishable flag from product for performance'
FROM ontology_classes WHERE class_name = 'OrderLine'
ON CONFLICT (prop_name) DO NOTHING;

-- Update line_amount description for clarity
UPDATE ontology_properties
SET description = 'Line total amount (quantity * unit_price)'
WHERE prop_name = 'line_amount'
  AND domain_class_id = (SELECT id FROM ontology_classes WHERE class_name = 'OrderLine');

-- Insert migration record
INSERT INTO schema_migrations (version) VALUES ('060_orderline_ontology')
ON CONFLICT (version) DO NOTHING;
