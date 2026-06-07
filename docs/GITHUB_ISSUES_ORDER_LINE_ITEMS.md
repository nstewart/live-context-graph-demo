# GitHub Issues: Order Line Items Implementation

## Phase 1: Foundation (Week 1-2)

### Issue #1: Add OrderLine Entity to Ontology
**Labels**: `backend`, `ontology`, `phase-1`
**Assignee**: Backend Developer
**Story Points**: 3

**Description**:
Add the OrderLine entity class to the ontology schema with all required properties.

**Acceptance Criteria**:
- [ ] OrderLine class added to ontology with prefix `orderline`
- [ ] Properties defined: `line_of_order`, `line_product`, `quantity`, `unit_price`, `line_amount`, `line_sequence`, `perishable_flag`
- [ ] Property types validated: entity_ref, entity_ref, int, float, float, int, bool
- [ ] Migration script created for ontology update
- [ ] Documentation updated in ONTOLOGY.md

**Technical Notes**:
- ID format: `orderline:{order_number}-{sequence}` (e.g., `orderline:FM-1001-001`)
- `unit_price` snapshots product price at order time
- `perishable_flag` denormalized from product for performance

---

### Issue #2: Implement OrderLine Triple CRUD Operations
**Labels**: `backend`, `api`, `phase-1`
**Story Points**: 5

**Description**:
Create API endpoints for creating, reading, updating, and deleting order line items using the triple-store pattern.

**Acceptance Criteria**:
- [ ] Batch create endpoint accepts array of line items for an order
- [ ] Single transaction support for order + line items
- [ ] Line sequence auto-increments within order
- [ ] Validation prevents duplicate line sequences
- [ ] Cascade delete removes line items when order is deleted
- [ ] Unit tests cover all CRUD operations

**API Endpoints**:
```
POST   /api/orders/{order_id}/line-items/batch  - Create multiple line items
GET    /api/orders/{order_id}/line-items        - List all line items for order
PUT    /api/orders/{order_id}/line-items/{id}   - Update single line item
DELETE /api/orders/{order_id}/line-items/{id}   - Delete single line item
```

---

### Issue #3: Create Materialized Views for Order Lines
**Labels**: `backend`, `materialize`, `phase-1`
**Story Points**: 8

**Description**:
Create three-tier materialized view hierarchy for efficient order line item queries.

**Acceptance Criteria**:
- [ ] `order_lines_base` view created (non-materialized)
- [ ] `order_lines_flat_mv` materialized view created
- [ ] `orders_with_lines_mv` created with JSONB aggregation
- [ ] Composite indexes on (order_id, line_sequence)
- [ ] Materialization latency < 2 seconds verified
- [ ] Views handle null/missing properties gracefully
- [ ] Migration script with rollback capability

**SQL Views**:
See Architecture Guidance doc section 2.1 for complete SQL

---

### Issue #4: Update Zero Schema for OrderLines
**Labels**: `backend`, `zero`, `phase-1`
**Story Points**: 5

**Description**:
Extend Zero WebSocket schema to include order_lines collection with real-time updates.

**Acceptance Criteria**:
- [ ] `order_lines` table added to Zero schema
- [ ] Relationships defined: order_lines → orders, order_lines → products
- [ ] SUBSCRIBE query includes line items in Zero sync
- [ ] Event consolidation for DELETE+INSERT pairs implemented
- [ ] Batch updates for multiple line items in single order
- [ ] Zero client can query line items by order_id

---

## Phase 2: UI Development (Week 3-4)

### Issue #5: Create Product Selector Component with Store Filtering
**Labels**: `frontend`, `ui`, `phase-2`
**Story Points**: 8

**Description**:
Build a product selector dropdown that dynamically filters products based on selected store's inventory.

**Acceptance Criteria**:
- [ ] Dropdown shows only products with stock > 0 at selected store
- [ ] Real-time inventory levels displayed next to product names
- [ ] Search/filter functionality for products
- [ ] Perishable indicator (❄️ icon) for cold chain items
- [ ] Loading states during inventory fetch
- [ ] Empty state when no products available
- [ ] Disabled state when store not selected

**Component**: `web/src/components/ProductSelector.tsx`

---

### Issue #6: Implement Shopping Cart State Management
**Labels**: `frontend`, `state`, `phase-2`
**Story Points**: 5

**Description**:
Create Zustand store for shopping cart with persistence and validation.

**Acceptance Criteria**:
- [ ] Zustand store created: `useShoppingCartStore`
- [ ] Actions: addItem, removeItem, updateQuantity, clearCart, setStore
- [ ] Local storage persistence for unsaved carts
- [ ] Validation prevents adding out-of-stock items
- [ ] Running total calculated automatically
- [ ] Store change clears cart with confirmation
- [ ] Unit tests for all store actions

**Store**: `web/src/stores/shoppingCartStore.ts`

---

### Issue #7: Build Shopping Cart UI Component
**Labels**: `frontend`, `ui`, `phase-2`
**Story Points**: 8

**Description**:
Create shopping cart component showing line items during order creation/editing.

**Acceptance Criteria**:
- [ ] Table showing: Product Name, Quantity, Unit Price, Line Total, Perishable
- [ ] Quantity input with +/- buttons
- [ ] Remove item button per line
- [ ] Running order total at bottom
- [ ] Empty cart state with helpful message
- [ ] Responsive design (mobile-friendly)
- [ ] Visual feedback for item addition

**Component**: `web/src/components/ShoppingCart.tsx`

---

### Issue #8: Integrate Shopping Cart into Order Creation Flow
**Labels**: `frontend`, `ui`, `phase-2`
**Story Points**: 5

**Description**:
Update OrderFormModal to include product selection and shopping cart.

**Acceptance Criteria**:
- [ ] Store selection triggers product filtering
- [ ] Product selector integrated below store dropdown
- [ ] Shopping cart displayed with selected items
- [ ] Order total synced with cart total
- [ ] Validation prevents submission with empty cart
- [ ] Edit mode loads existing line items into cart
- [ ] Save creates order + line items in single transaction

**File**: `web/src/pages/OrdersDashboardPage.tsx`

---

### Issue #9: Add Expandable Rows to Orders Table
**Labels**: `frontend`, `ui`, `phase-2`
**Story Points**: 5

**Description**:
Implement expandable row pattern to show order line items in the orders table.

**Acceptance Criteria**:
- [ ] Chevron icon (>) in leftmost column for each order
- [ ] Click chevron expands row to show nested line items table
- [ ] Line items table columns: Product, Quantity, Unit Price, Line Total
- [ ] Perishable indicator for applicable products
- [ ] Collapse animation on second click
- [ ] Loading state during line items fetch (if not cached)
- [ ] Empty state if order has no line items

**File**: `web/src/pages/OrdersDashboardPage.tsx`

---

## Phase 3: Search Integration (Week 5)

### Issue #10: Update OpenSearch Mapping for Nested Line Items
**Labels**: `backend`, `opensearch`, `phase-3`
**Story Points**: 5

**Description**:
Update OpenSearch index mapping to include nested line_items field.

**Acceptance Criteria**:
- [ ] Index mapping includes nested line_items field
- [ ] Field properties: product_id, product_name, quantity, line_amount, perishable
- [ ] Product_name field uses text analyzer for search
- [ ] Migration script for index recreation
- [ ] Zero downtime deployment strategy (alias swap)
- [ ] Reindex script for existing orders

**Mapping**:
See Implementation Review doc for complete mapping JSON

---

### Issue #11: Pipe Line Items Through the Kafka Sink → OpenSearch Pipeline
**Labels**: `backend`, `materialize`, `phase-3`

**Story Points**: 5

**Description**:
Ensure denormalized line items flow into order documents via the Kafka sink and Kafka Connect OpenSearch sink connector. OpenSearch indexing is handled by the Kafka Connect sink connectors, not a Python sync worker.

**Acceptance Criteria**:
- [ ] The view feeding the orders sink (`orders_with_lines_mv`) emits line items as a nested array in the order document
- [ ] `CREATE SINK` (Avro, Debezium envelope) publishes the view to the `orders` Kafka topic
- [ ] OpenSearch sink connector handles line item updates (INSERT/UPDATE/DELETE) via the Debezium envelope
- [ ] OpenSearch index template mapping updated for nested line items (see Issue #10)
- [ ] Error handling / DLQ configured for malformed line item data
- [ ] Monitoring for connector lag and task health

**Files**:
- `kafka-connect/connectors/orders-opensearch-sink.json` (connector config)
- `kafka-connect/opensearch-templates/orders.json` (index template)

---

### Issue #12: Implement Product Search Functionality
**Labels**: `frontend`, `backend`, `phase-3`
**Story Points**: 5

**Description**:
Add ability to search orders by product name in the UI.

**Acceptance Criteria**:
- [ ] Search input above orders table
- [ ] Debounced search (300ms delay)
- [ ] Query searches nested line_items.product_name field
- [ ] Results highlight matching products in expanded view
- [ ] Loading states during search
- [ ] Clear search button
- [ ] Search maintains <500ms p95 latency

**Files**:
- Backend: `api/src/search/routes.py`
- Frontend: `web/src/pages/OrdersDashboardPage.tsx`

---

## Phase 4: Testing & Rollout (Week 6)

### Issue #13: Write Integration Tests
**Labels**: `testing`, `phase-4`
**Story Points**: 8

**Description**:
Comprehensive integration tests covering order creation with line items.

**Acceptance Criteria**:
- [ ] Test: Create order with 10 line items, verify all persist
- [ ] Test: Edit order to add/remove line items, verify totals
- [ ] Test: Delete order cascades to line items
- [ ] Test: Expand order shows correct line items
- [ ] Test: Search by product name returns correct orders
- [ ] Test: Concurrent order creation doesn't corrupt data
- [ ] Test: Materialization lag handling

**Files**:
- `api/tests/integration/test_order_line_items.py`
- `web/src/pages/OrdersDashboardPage.test.tsx`

---

### Issue #14: Performance Testing
**Labels**: `testing`, `performance`, `phase-4`
**Story Points**: 5

**Description**:
Validate performance benchmarks meet acceptance criteria.

**Acceptance Criteria**:
- [ ] Order creation with 50 line items completes in <3 seconds
- [ ] Order expansion renders in <500ms for 20 line items
- [ ] Product search across 100k orders returns in <1 second
- [ ] Materialized view refresh <2 seconds for 1000 line items
- [ ] WebSocket updates <100ms latency for line item changes
- [ ] Load test: 50 concurrent users creating orders

**Tools**: Locust, k6, or similar

---

### Issue #15: Update Documentation
**Labels**: `documentation`, `phase-4`
**Story Points**: 3

**Description**:
Update all documentation to reflect order line items functionality.

**Acceptance Criteria**:
- [ ] ONTOLOGY.md includes OrderLine entity
- [ ] API_REFERENCE.md includes new endpoints
- [ ] USER_GUIDE.md explains shopping cart workflow
- [ ] ARCHITECTURE.md updated with materialized views
- [ ] OPENSEARCH_SINK_IMPLEMENTATION.md includes line items
- [ ] README.md mentions line items feature

---

### Issue #16: Feature Flag & Gradual Rollout
**Labels**: `deployment`, `phase-4`
**Story Points**: 3

**Description**:
Implement feature flag for gradual rollout of order line items.

**Acceptance Criteria**:
- [ ] Feature flag `order_line_items_enabled` added to config
- [ ] UI conditionally shows line items based on flag
- [ ] Old order creation flow still works when flag=false
- [ ] Monitoring dashboard for feature flag impact
- [ ] Rollback plan documented
- [ ] 25% → 50% → 100% rollout strategy

---

## Summary

**Total Story Points**: 86
**Estimated Duration**: 6 weeks
**Team**: 2 developers (1 backend, 1 frontend)

**Phase Breakdown**:
- Phase 1: 21 points (2 weeks)
- Phase 2: 31 points (2 weeks)
- Phase 3: 15 points (1 week)
- Phase 4: 19 points (1 week)

**Dependencies**:
- Issues #5-9 depend on #1-4 (UI needs backend foundation)
- Issues #10-12 depend on #3 (search needs materialized views)
- Issues #13-16 depend on all previous (testing needs complete feature)
