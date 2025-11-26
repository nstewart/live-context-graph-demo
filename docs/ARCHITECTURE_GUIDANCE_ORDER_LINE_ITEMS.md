# Architecture Guidance: Order Line Items Implementation

**Architecture Expert**: FreshMart Live Ontology Demo
**Feature**: Order Line Items
**Date**: November 24, 2025
**Author**: Architecture Team

---

## Executive Summary

This document provides comprehensive architectural guidance for implementing order line items in the FreshMart live ontology demo. The implementation follows the established triple-store pattern while introducing optimizations for nested data handling, real-time performance, and transaction consistency.

## 1. Data Modeling Architecture

### 1.1 Triple Store Entity Design

**Decision**: Implement `OrderLine` as a first-class entity in the triple store

```python
# Ontology Class Definition
class OrderLine:
    prefix = "orderline"
    properties = [
        "line_of_order",      # entity_ref -> Order
        "line_product",       # entity_ref -> Product
        "quantity",           # int
        "unit_price",        # float (snapshot at order time)
        "line_amount",       # float (computed: quantity * unit_price)
        "line_sequence",     # int (display order)
        "perishable_flag"    # bool (denormalized for performance)
    ]
```

**ID Format Pattern**: `orderline:{order_number}-{sequence}`
- Example: `orderline:FM-1001-001`, `orderline:FM-1001-002`
- Ensures natural sorting and parent-child relationship encoding

### 1.2 Triple Insertion Strategy

**Pattern**: Batch transaction with ordered inserts

```sql
-- Transaction boundary for order creation with line items
BEGIN;

-- 1. Insert order triples
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
  ('order:FM-1001', 'order_number', 'FM-1001', 'string'),
  ('order:FM-1001', 'order_status', 'CREATED', 'string'),
  ('order:FM-1001', 'order_store', 'store:001', 'entity_ref'),
  ('order:FM-1001', 'placed_by', 'customer:123', 'entity_ref'),
  ('order:FM-1001', 'order_total_amount', '157.50', 'float');

-- 2. Insert line item triples (bulk insert)
INSERT INTO triples (subject_id, predicate, object_value, object_type) VALUES
  -- Line item 1
  ('orderline:FM-1001-001', 'line_of_order', 'order:FM-1001', 'entity_ref'),
  ('orderline:FM-1001-001', 'line_product', 'product:PROD-001', 'entity_ref'),
  ('orderline:FM-1001-001', 'quantity', '2', 'int'),
  ('orderline:FM-1001-001', 'unit_price', '12.50', 'float'),
  ('orderline:FM-1001-001', 'line_amount', '25.00', 'float'),
  ('orderline:FM-1001-001', 'line_sequence', '1', 'int'),
  -- Line item 2
  ('orderline:FM-1001-002', 'line_of_order', 'order:FM-1001', 'entity_ref'),
  ('orderline:FM-1001-002', 'line_product', 'product:PROD-002', 'entity_ref'),
  ('orderline:FM-1001-002', 'quantity', '5', 'int'),
  ('orderline:FM-1001-002', 'unit_price', '26.50', 'float'),
  ('orderline:FM-1001-002', 'line_amount', '132.50', 'float'),
  ('orderline:FM-1001-002', 'line_sequence', '2', 'int');

COMMIT;
```

## 2. Materialization Architecture

### 2.1 Materialized View Design

**Three-tier view hierarchy for optimal performance**:

```sql
-- Tier 1: Base flattening view (non-materialized for flexibility)
CREATE VIEW order_lines_base AS
SELECT
    subject_id AS line_id,
    MAX(CASE WHEN predicate = 'line_of_order' THEN object_value END) AS order_id,
    MAX(CASE WHEN predicate = 'line_product' THEN object_value END) AS product_id,
    MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT AS quantity,
    MAX(CASE WHEN predicate = 'unit_price' THEN object_value END)::DECIMAL(10,2) AS unit_price,
    MAX(CASE WHEN predicate = 'line_amount' THEN object_value END)::DECIMAL(10,2) AS line_amount,
    MAX(CASE WHEN predicate = 'line_sequence' THEN object_value END)::INT AS line_sequence,
    MAX(CASE WHEN predicate = 'perishable_flag' THEN object_value END)::BOOL AS perishable_flag,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'orderline:%'
GROUP BY subject_id;

-- Tier 2: Dedicated line items materialized view for queries
CREATE MATERIALIZED VIEW order_lines_flat_mv IN CLUSTER compute AS
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
    p.weight_kg,
    ol.effective_updated_at
FROM order_lines_base ol
LEFT JOIN products_flat_mv p ON p.product_id = ol.product_id;

-- Tier 3: Orders with aggregated line items for UI display
CREATE MATERIALIZED VIEW orders_with_lines_mv IN CLUSTER compute AS
SELECT
    o.*,
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
                'perishable_flag', ol.perishable_flag,
                'weight_kg', ol.weight_kg
            ) ORDER BY ol.line_sequence
        ) FILTER (WHERE ol.line_id IS NOT NULL),
        '[]'::jsonb
    ) AS line_items,
    COUNT(ol.line_id) AS line_item_count,
    SUM(ol.line_amount) AS computed_total,
    BOOL_OR(ol.perishable_flag) AS has_perishable_items,
    SUM(ol.quantity * ol.weight_kg) AS total_weight_kg
FROM orders_flat_mv o
LEFT JOIN order_lines_flat_mv ol ON ol.order_id = o.order_id
GROUP BY o.order_id, o.order_number, o.order_status, o.store_id,
         o.customer_id, o.delivery_window_start, o.delivery_window_end,
         o.order_total_amount, o.effective_updated_at;
```

### 2.2 Index Strategy

```sql
-- Primary access patterns
CREATE INDEX idx_order_lines_order_id ON order_lines_flat_mv IN CLUSTER serving (order_id);
CREATE INDEX idx_order_lines_product_id ON order_lines_flat_mv IN CLUSTER serving (product_id);

-- Composite for efficient joins
CREATE INDEX idx_order_lines_composite ON order_lines_flat_mv IN CLUSTER serving
    (order_id, line_sequence);

-- Search optimization
CREATE INDEX idx_orders_with_lines_status ON orders_with_lines_mv IN CLUSTER serving
    (order_status, effective_updated_at DESC);
```

## 3. OpenSearch Integration Architecture

### 3.1 Index Mapping Design

```json
{
  "mappings": {
    "properties": {
      "order_id": { "type": "keyword" },
      "order_number": { "type": "keyword" },
      "order_status": { "type": "keyword" },
      "customer_name": {
        "type": "text",
        "fields": { "keyword": { "type": "keyword" } }
      },
      "store_name": {
        "type": "text",
        "fields": { "keyword": { "type": "keyword" } }
      },
      "order_total_amount": { "type": "float" },
      "line_item_count": { "type": "integer" },
      "has_perishable_items": { "type": "boolean" },

      "line_items": {
        "type": "nested",
        "properties": {
          "line_id": { "type": "keyword" },
          "product_id": { "type": "keyword" },
          "product_name": {
            "type": "text",
            "fields": { "keyword": { "type": "keyword" } }
          },
          "category": { "type": "keyword" },
          "quantity": { "type": "integer" },
          "unit_price": { "type": "float" },
          "line_amount": { "type": "float" },
          "perishable_flag": { "type": "boolean" }
        }
      },

      "delivery_window_start": { "type": "date" },
      "delivery_window_end": { "type": "date" },
      "effective_updated_at": { "type": "date" }
    }
  }
}
```

### 3.2 Search Query Patterns

```python
# Search orders by product name (nested query)
def search_orders_by_product(product_name: str):
    return {
        "query": {
            "nested": {
                "path": "line_items",
                "query": {
                    "match": {
                        "line_items.product_name": product_name
                    }
                }
            }
        },
        "aggs": {
            "line_items": {
                "nested": { "path": "line_items" },
                "aggs": {
                    "product_stats": {
                        "terms": { "field": "line_items.product_id" }
                    }
                }
            }
        }
    }
```

## 4. Zero WebSocket Architecture

### 4.1 Schema Extension

```typescript
// Extend Zero schema for line items
export interface Schema {
  version: 1;
  tables: {
    // ... existing tables ...

    order_lines: {
      tableName: "order_lines";
      columns: {
        id: { type: "string" };  // line_id
        order_id: { type: "string" };
        product_id: { type: "string" };
        product_name: { type: "string" };
        quantity: { type: "number" };
        unit_price: { type: "number" };
        line_amount: { type: "number" };
        line_sequence: { type: "number" };
        perishable_flag: { type: "boolean" };
      };
      primaryKey: ["id"];
      relationships: {
        order: {
          sourceField: "order_id";
          destTable: "orders";
          destField: "id";
        };
      };
    };

    // Enhanced orders table with computed fields
    orders_enhanced: {
      tableName: "orders_enhanced";
      columns: {
        // ... existing order fields ...
        line_item_count: { type: "number" };
        computed_total: { type: "number" };
        has_perishable_items: { type: "boolean" };
        total_weight_kg: { type: "number | null" };
      };
      primaryKey: ["id"];
    };
  };
}
```

### 4.2 SUBSCRIBE Handler Optimization

```typescript
// Optimized batch handling for line items
class MaterializeBackend {
  private pendingLineItemUpdates: Map<string, LineItemBatch> = new Map();

  async handleLineItemStream(stream: AsyncIterable<SubscribeEvent>) {
    for await (const event of stream) {
      // Consolidate line item updates by order
      const orderId = this.extractOrderId(event.row.line_id);

      if (!this.pendingLineItemUpdates.has(orderId)) {
        this.pendingLineItemUpdates.set(orderId, {
          orderId,
          updates: [],
          timestamp: event.timestamp
        });
      }

      const batch = this.pendingLineItemUpdates.get(orderId)!;
      batch.updates.push(event);

      // Flush when timestamp advances
      if (event.timestamp > batch.timestamp) {
        await this.flushLineItemBatch(batch);
        this.pendingLineItemUpdates.delete(orderId);
      }
    }
  }

  private async flushLineItemBatch(batch: LineItemBatch) {
    // Consolidate DELETEs and INSERTs at same timestamp
    const consolidated = this.consolidateEvents(batch.updates);

    // Broadcast single update per order
    await this.zero.mutate({
      type: "update",
      table: "order_lines",
      rows: consolidated
    });
  }
}
```

## 5. API Layer Architecture

### 5.1 Service Layer Design

```python
# api/src/freshmart/order_service.py
from typing import List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session
from fastapi import HTTPException

class OrderLineService:
    """Service for managing order line items with transactional integrity."""

    async def create_order_with_lines(
        self,
        db: Session,
        order_data: OrderCreateRequest,
        line_items: List[LineItemRequest]
    ) -> OrderResponse:
        """Create order with line items in a single transaction."""

        try:
            # Begin transaction
            with db.begin():
                # 1. Validate inventory availability
                availability = await self._check_inventory(
                    db,
                    order_data.store_id,
                    line_items
                )

                if not availability.all_available:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient stock: {availability.unavailable_items}"
                    )

                # 2. Generate order ID
                order_id = f"order:{self._generate_order_number()}"

                # 3. Calculate totals
                total_amount = sum(
                    item.quantity * item.unit_price
                    for item in line_items
                )

                # 4. Insert order triples
                order_triples = self._create_order_triples(
                    order_id,
                    order_data,
                    total_amount
                )
                db.bulk_insert_mappings(Triple, order_triples)

                # 5. Insert line item triples
                line_triples = self._create_line_item_triples(
                    order_id,
                    line_items
                )
                db.bulk_insert_mappings(Triple, line_triples)

                # 6. Update inventory (soft reserve)
                await self._reserve_inventory(
                    db,
                    order_data.store_id,
                    line_items
                )

                db.commit()

            return OrderResponse(
                order_id=order_id,
                status="CREATED",
                line_item_count=len(line_items),
                total_amount=total_amount
            )

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))

    def _create_line_item_triples(
        self,
        order_id: str,
        line_items: List[LineItemRequest]
    ) -> List[dict]:
        """Generate triple records for line items."""

        triples = []
        for idx, item in enumerate(line_items, 1):
            line_id = f"orderline:{order_id.split(':')[1]}-{idx:03d}"

            # Core properties
            triples.extend([
                {
                    'subject_id': line_id,
                    'predicate': 'line_of_order',
                    'object_value': order_id,
                    'object_type': 'entity_ref'
                },
                {
                    'subject_id': line_id,
                    'predicate': 'line_product',
                    'object_value': item.product_id,
                    'object_type': 'entity_ref'
                },
                {
                    'subject_id': line_id,
                    'predicate': 'quantity',
                    'object_value': str(item.quantity),
                    'object_type': 'int'
                },
                {
                    'subject_id': line_id,
                    'predicate': 'unit_price',
                    'object_value': str(item.unit_price),
                    'object_type': 'float'
                },
                {
                    'subject_id': line_id,
                    'predicate': 'line_amount',
                    'object_value': str(item.quantity * item.unit_price),
                    'object_type': 'float'
                },
                {
                    'subject_id': line_id,
                    'predicate': 'line_sequence',
                    'object_value': str(idx),
                    'object_type': 'int'
                }
            ])

        return triples
```

### 5.2 API Endpoints

```python
# api/src/routes/orders.py
from fastapi import APIRouter, Depends, Query
from typing import List, Optional

router = APIRouter()

@router.post("/api/orders/with-lines")
async def create_order_with_lines(
    request: OrderWithLinesRequest,
    db: Session = Depends(get_db),
    service: OrderLineService = Depends()
) -> OrderResponse:
    """Create order with line items atomically."""
    return await service.create_order_with_lines(
        db,
        request.order,
        request.line_items
    )

@router.get("/api/orders/{order_id}/lines")
async def get_order_lines(
    order_id: str,
    db: Session = Depends(get_db)
) -> List[OrderLineResponse]:
    """Get line items for an order."""
    return await service.get_order_lines(db, order_id)

@router.patch("/api/orders/{order_id}/lines/{line_id}")
async def update_line_quantity(
    order_id: str,
    line_id: str,
    quantity: int,
    db: Session = Depends(get_db)
) -> OrderLineResponse:
    """Update line item quantity (recalculates totals)."""
    return await service.update_line_quantity(
        db, order_id, line_id, quantity
    )

@router.get("/api/products/available")
async def get_available_products(
    store_id: str,
    category: Optional[str] = None,
    perishable_only: bool = False,
    db: Session = Depends(get_db)
) -> List[ProductWithStockResponse]:
    """Get products with current stock levels for a store."""
    return await service.get_products_with_stock(
        db, store_id, category, perishable_only
    )
```

## 6. UI State Management Architecture

### 6.1 Shopping Cart State Pattern

```typescript
// web/src/hooks/useShoppingCart.ts
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface CartItem {
  productId: string;
  productName: string;
  quantity: number;
  unitPrice: number;
  perishable: boolean;
  stockLevel: number;
}

interface ShoppingCartStore {
  items: CartItem[];
  selectedStoreId: string | null;

  // Actions
  addItem: (item: CartItem) => void;
  updateQuantity: (productId: string, quantity: number) => void;
  removeItem: (productId: string) => void;
  clearCart: () => void;
  setStore: (storeId: string) => void;

  // Computed
  getTotalAmount: () => number;
  getItemCount: () => number;
  hasPerishableItems: () => boolean;
}

export const useShoppingCart = create<ShoppingCartStore>()(
  persist(
    (set, get) => ({
      items: [],
      selectedStoreId: null,

      addItem: (item) => set((state) => {
        // Prevent adding if exceeds stock
        const existing = state.items.find(i => i.productId === item.productId);
        if (existing) {
          const newQuantity = existing.quantity + item.quantity;
          if (newQuantity > item.stockLevel) {
            throw new Error('Exceeds available stock');
          }
          return {
            items: state.items.map(i =>
              i.productId === item.productId
                ? { ...i, quantity: newQuantity }
                : i
            )
          };
        }
        return { items: [...state.items, item] };
      }),

      updateQuantity: (productId, quantity) => set((state) => ({
        items: state.items.map(item =>
          item.productId === productId
            ? { ...item, quantity }
            : item
        )
      })),

      removeItem: (productId) => set((state) => ({
        items: state.items.filter(i => i.productId !== productId)
      })),

      clearCart: () => set({ items: [], selectedStoreId: null }),

      setStore: (storeId) => set({
        selectedStoreId: storeId,
        items: [] // Clear cart when store changes
      }),

      getTotalAmount: () => {
        const { items } = get();
        return items.reduce((sum, item) =>
          sum + (item.quantity * item.unitPrice), 0
        );
      },

      getItemCount: () => {
        const { items } = get();
        return items.reduce((sum, item) => sum + item.quantity, 0);
      },

      hasPerishableItems: () => {
        const { items } = get();
        return items.some(item => item.perishable);
      }
    }),
    {
      name: 'shopping-cart',
      partialize: (state) => ({
        items: state.items,
        selectedStoreId: state.selectedStoreId
      })
    }
  )
);
```

### 6.2 Expandable Order Table Component

```typescript
// web/src/components/OrdersTable.tsx
import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface OrderWithLines extends OrderFlat {
  line_items: OrderLine[];
  line_item_count: number;
  has_perishable_items: boolean;
}

export function OrdersTable({ orders }: { orders: OrderWithLines[] }) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = (orderId: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(orderId)) {
      newExpanded.delete(orderId);
    } else {
      newExpanded.add(orderId);
    }
    setExpandedRows(newExpanded);
  };

  return (
    <table className="min-w-full divide-y divide-gray-200">
      <thead>
        <tr>
          <th className="w-10"></th>
          <th>Order Number</th>
          <th>Customer</th>
          <th>Items</th>
          <th>Total</th>
          <th>Status</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {orders.map((order) => (
          <>
            <tr key={order.order_id} className="hover:bg-gray-50">
              <td>
                <button
                  onClick={() => toggleRow(order.order_id)}
                  className="p-1 hover:bg-gray-200 rounded"
                  disabled={order.line_item_count === 0}
                >
                  {expandedRows.has(order.order_id) ?
                    <ChevronUp className="h-4 w-4" /> :
                    <ChevronDown className="h-4 w-4" />
                  }
                </button>
              </td>
              <td>{order.order_number}</td>
              <td>{order.customer_name}</td>
              <td>
                <span className="inline-flex items-center gap-2">
                  <span className="badge">{order.line_item_count} items</span>
                  {order.has_perishable_items && (
                    <span className="text-blue-600" title="Contains perishable items">
                      ❄️
                    </span>
                  )}
                </span>
              </td>
              <td>${order.order_total_amount}</td>
              <td><StatusBadge status={order.order_status} /></td>
              <td>
                <button className="text-blue-600 hover:text-blue-800">
                  Edit
                </button>
              </td>
            </tr>

            {expandedRows.has(order.order_id) && (
              <tr>
                <td colSpan={7} className="bg-gray-50 p-4">
                  <LineItemsTable
                    lineItems={order.line_items}
                    orderId={order.order_id}
                  />
                </td>
              </tr>
            )}
          </>
        ))}
      </tbody>
    </table>
  );
}

function LineItemsTable({
  lineItems,
  orderId
}: {
  lineItems: OrderLine[];
  orderId: string;
}) {
  return (
    <div className="pl-8">
      <h4 className="text-sm font-semibold mb-2">Order Line Items</h4>
      <table className="min-w-full text-sm">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left p-2">Product</th>
            <th className="text-center p-2">Quantity</th>
            <th className="text-right p-2">Unit Price</th>
            <th className="text-right p-2">Line Total</th>
            <th className="text-center p-2">Perishable</th>
          </tr>
        </thead>
        <tbody>
          {lineItems.map((item) => (
            <tr key={item.line_id} className="border-t">
              <td className="p-2">{item.product_name}</td>
              <td className="text-center p-2">{item.quantity}</td>
              <td className="text-right p-2">${item.unit_price}</td>
              <td className="text-right p-2">${item.line_amount}</td>
              <td className="text-center p-2">
                {item.perishable_flag ? '❄️' : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

## 7. Transaction and Consistency Architecture

### 7.1 Transaction Boundaries

```python
# Transaction boundary patterns for consistency

class TransactionPatterns:
    """Define clear transaction boundaries for different operations."""

    # Pattern 1: Order Creation with Inventory Check
    async def create_order_with_inventory_check(self, db, order, lines):
        """Single transaction for order + lines + inventory."""
        with db.begin():
            # 1. Check inventory (SELECT FOR UPDATE)
            inventory = db.query(Inventory).filter(
                Inventory.store_id == order.store_id
            ).with_for_update().all()

            # 2. Validate availability
            for line in lines:
                stock = next(
                    (i for i in inventory if i.product_id == line.product_id),
                    None
                )
                if not stock or stock.level < line.quantity:
                    raise InsufficientStockError(line.product_id)

            # 3. Create order and lines
            order_triples = self.create_order_triples(order)
            line_triples = self.create_line_triples(order.id, lines)

            db.bulk_insert_mappings(Triple, order_triples + line_triples)

            # 4. Update inventory
            for line in lines:
                db.execute(
                    update(Inventory)
                    .where(
                        Inventory.store_id == order.store_id,
                        Inventory.product_id == line.product_id
                    )
                    .values(level=Inventory.level - line.quantity)
                )

    # Pattern 2: Order Update with Compensation
    async def update_order_with_compensation(self, db, order_id, updates):
        """Update with compensation for failures."""

        # Record original state for rollback
        original = await self.get_order_snapshot(db, order_id)

        try:
            with db.begin():
                # Apply updates
                await self.apply_order_updates(db, order_id, updates)

                # Validate business rules
                if not await self.validate_order_state(db, order_id):
                    raise BusinessRuleViolation()

        except Exception as e:
            # Compensate with original state
            await self.restore_order_state(db, order_id, original)
            raise
```

### 7.2 Consistency Guarantees

```sql
-- Consistency rules enforced at database level

-- Rule 1: Order total must equal sum of line items
CREATE OR REPLACE FUNCTION check_order_total_consistency()
RETURNS trigger AS $$
DECLARE
    computed_total DECIMAL;
    stored_total DECIMAL;
BEGIN
    -- Calculate sum of line items
    SELECT SUM(CAST(object_value AS DECIMAL))
    INTO computed_total
    FROM triples
    WHERE subject_id LIKE 'orderline:' ||
          SUBSTRING(NEW.subject_id FROM 'order:(.*)') || '-%'
      AND predicate = 'line_amount';

    -- Get stored total
    SELECT CAST(object_value AS DECIMAL)
    INTO stored_total
    FROM triples
    WHERE subject_id = NEW.subject_id
      AND predicate = 'order_total_amount';

    -- Validate consistency
    IF ABS(computed_total - stored_total) > 0.01 THEN
        RAISE EXCEPTION 'Order total inconsistency: computed=%, stored=%',
                        computed_total, stored_total;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Rule 2: Line items must reference valid products
ALTER TABLE triples
ADD CONSTRAINT chk_line_product_ref
CHECK (
    NOT (subject_id LIKE 'orderline:%' AND
         predicate = 'line_product' AND
         object_value NOT LIKE 'product:%')
);
```

## 8. Performance Optimization Strategies

### 8.1 Query Optimization

```sql
-- Optimized query patterns for common operations

-- Pattern 1: Get orders with line items (single query)
WITH order_lines_agg AS (
    SELECT
        ol.order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_id', ol.line_id,
                'product_name', ol.product_name,
                'quantity', ol.quantity,
                'line_amount', ol.line_amount
            ) ORDER BY ol.line_sequence
        ) AS line_items,
        COUNT(*) AS line_count,
        SUM(ol.line_amount) AS total
    FROM order_lines_flat_mv ol
    WHERE ol.order_id = ANY($1::text[])  -- Batch multiple orders
    GROUP BY ol.order_id
)
SELECT
    o.*,
    COALESCE(ola.line_items, '[]'::jsonb) AS line_items,
    COALESCE(ola.line_count, 0) AS line_count,
    COALESCE(ola.total, 0) AS computed_total
FROM orders_flat_mv o
LEFT JOIN order_lines_agg ola ON ola.order_id = o.order_id
WHERE o.order_id = ANY($1::text[]);

-- Pattern 2: Product availability across stores
CREATE MATERIALIZED VIEW product_availability_mv IN CLUSTER compute AS
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.unit_price,
    p.perishable,
    jsonb_agg(
        jsonb_build_object(
            'store_id', i.store_id,
            'store_name', s.store_name,
            'stock_level', i.stock_level,
            'available', i.stock_level > 0
        )
    ) AS store_availability
FROM products_flat_mv p
LEFT JOIN store_inventory_mv i ON i.product_id = p.product_id
LEFT JOIN stores_flat s ON s.store_id = i.store_id
GROUP BY p.product_id, p.product_name, p.category, p.unit_price, p.perishable;
```

### 8.2 Caching Strategy

```typescript
// Implement strategic caching for line items
class LineItemCache {
  private cache: Map<string, CachedLineItems> = new Map();
  private readonly TTL = 5 * 60 * 1000; // 5 minutes

  async getOrderLines(orderId: string): Promise<OrderLine[]> {
    const cached = this.cache.get(orderId);

    if (cached && Date.now() - cached.timestamp < this.TTL) {
      return cached.items;
    }

    // Fetch from Materialize
    const items = await this.fetchFromMaterialize(orderId);

    this.cache.set(orderId, {
      items,
      timestamp: Date.now()
    });

    return items;
  }

  invalidateOrder(orderId: string) {
    this.cache.delete(orderId);
  }

  // Batch invalidation for efficiency
  invalidateOrders(orderIds: string[]) {
    orderIds.forEach(id => this.cache.delete(id));
  }
}
```

## 9. Migration Strategy

### 9.1 Database Migration

```sql
-- Migration script for adding line items support

-- Step 1: Add new ontology classes and properties
INSERT INTO ontology_classes (class_name, prefix, description) VALUES
('OrderLine', 'orderline', 'Line item within an order');

INSERT INTO ontology_properties (
    prop_name, domain_class_id, range_kind, range_class_id,
    is_multi_valued, is_required, description
) VALUES
('line_of_order',
 (SELECT id FROM ontology_classes WHERE prefix = 'orderline'),
 'entity_ref',
 (SELECT id FROM ontology_classes WHERE prefix = 'order'),
 false, true, 'Order this line belongs to'),
('line_product',
 (SELECT id FROM ontology_classes WHERE prefix = 'orderline'),
 'entity_ref',
 (SELECT id FROM ontology_classes WHERE prefix = 'product'),
 false, true, 'Product in this line item');

-- Step 2: Create materialized views
-- (Views defined in Section 2.1)

-- Step 3: Backfill historical data (if needed)
-- This would be a custom ETL process based on source system
```

### 9.2 Zero-Downtime Deployment

```yaml
# Deployment sequence for zero downtime

phases:
  - name: "Database Schema"
    steps:
      - Run migration to add ontology classes
      - Create new views (doesn't affect existing)
      - Deploy updated Materialize views
    rollback: Drop new views and classes

  - name: "API Layer"
    steps:
      - Deploy new API with feature flag OFF
      - Test new endpoints in production
      - Enable feature flag for beta users
    rollback: Disable feature flag

  - name: "UI Components"
    steps:
      - Deploy UI with feature flag
      - A/B test with small user group
      - Monitor performance metrics
    rollback: Revert to previous UI version

  - name: "Full Activation"
    steps:
      - Enable for all users
      - Update documentation
      - Remove feature flags
```

## 10. Risk Mitigation

### 10.1 Identified Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation Strategy |
|------|--------|------------|-------------------|
| **Materialization Lag** | High | Medium | Pre-aggregate common queries; implement circuit breaker at 3s lag |
| **Transaction Conflicts** | High | Low | Use optimistic locking with retry logic; max 3 retries |
| **Memory Pressure (JSONB)** | Medium | Medium | Limit line items to 100 per order; paginate large results |
| **Search Performance** | Medium | Low | Use nested field type; limit depth to 1 level |
| **WebSocket Overload** | High | Low | Batch updates by order; throttle to 10 updates/sec |
| **Data Inconsistency** | High | Low | Transaction boundaries; consistency checks in triggers |

### 10.2 Monitoring and Alerts

```python
# Key metrics to monitor
monitoring_config = {
    "materialization": {
        "max_lag_ms": 2000,
        "alert_threshold": 3000,
        "metric": "mz_compute_lag_ms"
    },
    "api_performance": {
        "p95_latency_ms": 500,
        "p99_latency_ms": 1000,
        "endpoints": [
            "/api/orders/with-lines",
            "/api/orders/{id}/lines"
        ]
    },
    "consistency": {
        "check_interval": 300,  # 5 minutes
        "queries": [
            "SELECT COUNT(*) FROM orders WHERE computed_total != order_total_amount",
            "SELECT COUNT(*) FROM order_lines WHERE order_id NOT IN (SELECT order_id FROM orders)"
        ]
    }
}
```

## 11. Testing Strategy

### 11.1 Unit Tests

```python
# Example unit test for line item service
import pytest
from decimal import Decimal

class TestOrderLineService:

    @pytest.fixture
    def service(self):
        return OrderLineService()

    def test_create_line_item_triples(self, service):
        """Test triple generation for line items."""

        line_items = [
            LineItemRequest(
                product_id="product:001",
                quantity=2,
                unit_price=Decimal("10.50")
            ),
            LineItemRequest(
                product_id="product:002",
                quantity=1,
                unit_price=Decimal("25.00")
            )
        ]

        triples = service._create_line_item_triples(
            "order:FM-1001",
            line_items
        )

        # Verify triple count (6 properties per line item)
        assert len(triples) == 12

        # Verify line IDs
        line_ids = {t['subject_id'] for t in triples}
        assert line_ids == {
            'orderline:FM-1001-001',
            'orderline:FM-1001-002'
        }

        # Verify line amounts
        amounts = [
            t for t in triples
            if t['predicate'] == 'line_amount'
        ]
        assert amounts[0]['object_value'] == '21.00'
        assert amounts[1]['object_value'] == '25.00'
```

### 11.2 Integration Tests

```typescript
// Integration test for order creation flow
describe('Order Creation with Line Items', () => {
  it('should create order with multiple line items', async () => {
    // Arrange
    const storeId = 'store:001';
    const products = await fetchAvailableProducts(storeId);

    const orderRequest = {
      order: {
        store_id: storeId,
        customer_id: 'customer:123',
        delivery_window_start: '2025-01-01T10:00:00Z',
        delivery_window_end: '2025-01-01T12:00:00Z'
      },
      line_items: [
        {
          product_id: products[0].product_id,
          quantity: 2,
          unit_price: products[0].unit_price
        },
        {
          product_id: products[1].product_id,
          quantity: 1,
          unit_price: products[1].unit_price
        }
      ]
    };

    // Act
    const response = await api.post('/api/orders/with-lines', orderRequest);

    // Assert
    expect(response.status).toBe(201);
    expect(response.data.line_item_count).toBe(2);
    expect(response.data.total_amount).toBe(
      2 * products[0].unit_price + products[1].unit_price
    );

    // Verify materialization
    await waitForMaterialization();
    const order = await api.get(`/api/orders/${response.data.order_id}`);
    expect(order.data.line_items).toHaveLength(2);
  });
});
```

## 12. Documentation Requirements

### 12.1 API Documentation

Document all new endpoints in OpenAPI format:

```yaml
paths:
  /api/orders/with-lines:
    post:
      summary: Create order with line items
      description: Atomically creates an order with associated line items
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [order, line_items]
              properties:
                order:
                  $ref: '#/components/schemas/OrderCreateRequest'
                line_items:
                  type: array
                  items:
                    $ref: '#/components/schemas/LineItemRequest'
                  minItems: 1
                  maxItems: 100
      responses:
        201:
          description: Order created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/OrderResponse'
        400:
          description: Validation error or insufficient stock
        500:
          description: Server error
```

### 12.2 Developer Guide

Create comprehensive guide covering:
- Triple store patterns for line items
- Transaction boundaries and consistency
- WebSocket subscription for real-time updates
- UI component usage and state management
- Performance considerations and limits

## Conclusion

This architecture provides a robust, scalable foundation for implementing order line items while maintaining consistency with the existing triple-store pattern. Key architectural decisions include:

1. **First-class entity modeling** for maximum flexibility
2. **Three-tier materialization** for optimal query performance
3. **Transactional consistency** with clear boundaries
4. **Real-time synchronization** through optimized SUBSCRIBE handling
5. **Comprehensive monitoring** for production reliability

The design balances performance, maintainability, and consistency while providing clear extension points for future enhancements such as inventory reservation, product bundles, and advanced analytics.

## Appendix: Quick Reference

### Key Files to Modify

```bash
# Backend
api/src/ontology/models.py          # Add OrderLine class
api/src/freshmart/order_service.py  # New service for line items
api/src/routes/orders.py            # New endpoints
db/materialize/init_materialize.sql # New materialized views

# Frontend
web/src/api/client.ts               # Add OrderLine types
web/src/hooks/useShoppingCart.ts    # Shopping cart state
web/src/components/OrdersTable.tsx  # Expandable rows
web/src/pages/OrdersDashboardPage.tsx # Order creation flow

# Infrastructure
web/src/schema.ts                   # Zero schema with order lines
search-sync/src/mappings.py         # Update OpenSearch mapping
```

### SQL Quick Reference

```sql
-- Check line items for an order
SELECT * FROM order_lines_flat_mv
WHERE order_id = 'order:FM-1001'
ORDER BY line_sequence;

-- Get orders with line item summary
SELECT
    order_id,
    order_number,
    line_item_count,
    computed_total,
    has_perishable_items
FROM orders_with_lines_mv
WHERE order_status = 'CREATED'
ORDER BY effective_updated_at DESC;

-- Product availability by store
SELECT
    product_name,
    store_availability
FROM product_availability_mv
WHERE product_id = 'product:PROD-001';
```

### API Quick Reference

```bash
# Create order with lines
curl -X POST http://localhost:8000/api/orders/with-lines \
  -H "Content-Type: application/json" \
  -d '{
    "order": {
      "store_id": "store:001",
      "customer_id": "customer:123"
    },
    "line_items": [
      {
        "product_id": "product:001",
        "quantity": 2,
        "unit_price": 10.50
      }
    ]
  }'

# Get order lines
curl http://localhost:8000/api/orders/order:FM-1001/lines

# Get available products for store
curl http://localhost:8000/api/products/available?store_id=store:001
```