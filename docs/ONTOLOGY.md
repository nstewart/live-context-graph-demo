# Ontology Guide

This document describes the FreshMart ontology - the schema that defines entity types and their relationships.

## Ontology Overview

The ontology provides semantic structure for the knowledge graph:

- **Classes** define entity types (Customer, Order, Store, etc.)
- **Properties** define allowed attributes and relationships
- **Validation** ensures data integrity

## Classes

### Customer

Represents a FreshMart customer who places orders.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| customer_name | string | Yes | Full name |
| customer_email | string | No | Email address |
| customer_address | string | Yes | Delivery address |
| home_store | Store (ref) | No | Preferred store |

**Example**:
```json
{
  "subject_id": "customer:123",
  "triples": [
    {"predicate": "customer_name", "object_value": "Alex Thompson", "object_type": "string"},
    {"predicate": "customer_email", "object_value": "alex@email.com", "object_type": "string"},
    {"predicate": "customer_address", "object_value": "234 Park Slope Ave, Brooklyn", "object_type": "string"},
    {"predicate": "home_store", "object_value": "store:BK-01", "object_type": "entity_ref"}
  ]
}
```

### Store

A FreshMart store location that fulfills orders.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| store_name | string | Yes | Display name |
| store_address | string | Yes | Physical address |
| store_zone | string | Yes | Delivery zone code |
| store_status | string | Yes | OPEN, CLOSED, LIMITED |
| store_capacity_orders_per_hour | int | No | Maximum orders/hour |

### Product

An item available for sale.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| product_name | string | Yes | Display name |
| category | string | Yes | Product category |
| perishable | bool | Yes | Is perishable |
| unit_weight_grams | int | No | Weight in grams |
| unit_price | float | Yes | Price in dollars |

### InventoryItem

Links a product to a store with stock level.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| inventory_store | Store (ref) | Yes | Store holding inventory |
| inventory_product | Product (ref) | Yes | Product |
| stock_level | int | Yes | Current quantity |
| replenishment_eta | timestamp | No | Expected restock time |

### Order

A customer order for delivery.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| order_number | string | Yes | Human-readable ID (FM-XXXX) |
| placed_by | Customer (ref) | Yes | Customer who ordered |
| order_store | Store (ref) | Yes | Fulfilling store |
| order_status | string | Yes | Current status |
| delivery_window_start | timestamp | Yes | Window start |
| delivery_window_end | timestamp | Yes | Window end |
| order_total_amount | float | Yes | Total in dollars |

**Order Statuses**:
- `CREATED` - New order
- `PICKING` - Being picked in store
- `OUT_FOR_DELIVERY` - With courier
- `DELIVERED` - Completed
- `CANCELLED` - Cancelled

### OrderLine

A line item within an order.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| line_of_order | Order (ref) | Yes | Parent order |
| line_product | Product (ref) | Yes | Product |
| quantity | int | Yes | Quantity ordered |
| line_amount | float | Yes | Line total |

### Courier

A delivery person.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| courier_name | string | Yes | Full name |
| courier_home_store | Store (ref) | No | Home store |
| vehicle_type | string | Yes | BIKE, CAR, VAN |
| courier_status | string | Yes | OFF_SHIFT, AVAILABLE, ON_DELIVERY |

### DeliveryTask

A delivery task assigned to a courier.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| task_of_order | Order (ref) | Yes | Order being delivered |
| assigned_to | Courier (ref) | No | Assigned courier |
| task_status | string | Yes | PENDING, ASSIGNED, IN_PROGRESS, COMPLETED, FAILED |
| eta | timestamp | No | Estimated arrival |
| route_sequence | int | No | Position in route |

## Managing the Ontology

### Via Admin UI

The web Admin UI provides a visual interface for managing classes and properties:

1. **Ontology Classes** (`/ontology-classes`)
   - View all classes with their prefixes
   - Create new classes
   - Edit existing classes
   - Delete classes (if no properties depend on them)

2. **Ontology Properties** (`/ontology-properties`)
   - View all properties with domain/range information
   - Create new properties with dropdown selectors for:
     - **Domain Class**: Select from existing classes
     - **Range Kind**: string, integer, decimal, boolean, datetime, entity_ref
     - **Range Class**: (when range_kind is entity_ref) Select target class
   - Edit property details
   - Delete properties with confirmation

### Via API

```bash
# 1. Create the class
POST /ontology/classes
{
  "class_name": "Zone",
  "prefix": "zone",
  "description": "A delivery zone"
}

# 2. Add properties
POST /ontology/properties
{
  "prop_name": "zone_name",
  "domain_class_id": 9,  # ID of Zone class
  "range_kind": "string",
  "is_required": true,
  "description": "Zone display name"
}

POST /ontology/properties
{
  "prop_name": "zone_polygon",
  "domain_class_id": 9,
  "range_kind": "string",  # GeoJSON string
  "is_required": false,
  "description": "Zone boundary as GeoJSON"
}

# 3. Update a property
PATCH /ontology/properties/{id}
{
  "description": "Updated description"
}

# 4. Delete a property
DELETE /ontology/properties/{id}
```

### Via Seed SQL

```sql
-- Add class
INSERT INTO ontology_classes (class_name, prefix, description)
VALUES ('Zone', 'zone', 'A delivery zone');

-- Add properties
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'zone_name', id, 'string', TRUE, 'Zone display name'
FROM ontology_classes WHERE class_name = 'Zone';
```

## Property Types

| Type | Description | Example |
|------|-------------|---------|
| string | Text value | "John Doe" |
| int | Integer number | "42" |
| float | Decimal number | "19.99" |
| bool | Boolean | "true" or "false" |
| timestamp | ISO 8601 datetime | "2025-11-22T14:00:00Z" |
| date | ISO 8601 date | "2025-11-22" |
| entity_ref | Reference to another entity | "store:BK-01" |

## Validation Rules

The validation layer enforces:

1. **Subject prefix** must match a class prefix
2. **Predicate** must exist in ontology_properties
3. **Domain** - predicate must apply to subject's class
4. **Range** - object type must match property's range_kind
5. **Entity refs** - referenced entity's prefix must match range class

### Example Validation Errors

```json
{
  "is_valid": false,
  "errors": [
    {
      "error_type": "domain_violation",
      "message": "Predicate 'customer_name' domain is 'Customer', but subject is 'Order'",
      "predicate": "customer_name",
      "expected": "Customer",
      "actual": "Order"
    }
  ]
}
```

## Class Hierarchy

Classes can have parent classes for inheritance (optional):

```sql
-- Create a subclass
INSERT INTO ontology_classes (class_name, prefix, description, parent_class_id)
SELECT 'PremiumCustomer', 'premium_customer', 'Premium tier customer', id
FROM ontology_classes WHERE class_name = 'Customer';
```

Subclasses inherit validation rules from parent classes.
