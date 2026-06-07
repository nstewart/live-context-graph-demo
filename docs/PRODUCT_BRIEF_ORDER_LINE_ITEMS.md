# Product Brief: Order Line Items Feature

**Product Manager**: FreshMart Live Ontology Demo
**Feature**: Orders Dashboard Line Items Enhancement
**Date**: November 24, 2025
**Framework**: Marty Cagan Inspired Approach

---

## 1. Problem Statement

### User Pain Points
Operations staff currently face significant limitations when managing orders in the FreshMart system:

- **Blind Order Creation**: When creating orders, staff cannot see what products are actually available at the selected store, leading to orders that cannot be fulfilled
- **Opaque Order Contents**: Orders are just abstract entities with a total amount - there's no visibility into what products customers actually ordered
- **Manual Reconciliation**: Staff must use external systems to understand order composition when handling customer inquiries or fulfillment issues
- **Inefficient Search**: The current denormalized search views don't include product details, making it impossible to find orders by product content
- **Stock-Order Mismatch**: No real-time connection between inventory levels and order creation, causing fulfillment failures

### Business Impact
- Increased order cancellations due to stock unavailability (estimated 8-12% of orders)
- Longer customer service resolution times (average 5+ minutes per inquiry)
- Higher operational costs from manual order verification processes
- Reduced customer satisfaction from orders containing out-of-stock items

## 2. Target Outcomes

### Primary Success Metrics (Leading Indicators)
- **Order Accuracy Rate**: Increase from 88% to 97% (orders created with all items in stock)
- **Order Creation Time**: Reduce from average 3 minutes to 90 seconds
- **Search Query Success Rate**: Improve from 65% to 85% for product-related order searches

### Secondary Success Metrics (Lagging Indicators)
- **Order Cancellation Rate**: Reduce stock-related cancellations by 75%
- **Customer Service Resolution Time**: Reduce average handling time by 40%
- **Operational Efficiency**: Reduce manual order verification tasks by 60%

### User Experience Outcomes
- Operations staff can confidently create orders knowing product availability
- Customer service can instantly see order contents during inquiries
- Warehouse staff can efficiently pick orders with detailed line item views
- Management can analyze product performance through order composition data

## 3. User Stories

### Operations Staff (Primary Persona)
1. **As an operations coordinator**, I want to see available products when creating an order, so that I only add items that can be fulfilled
2. **As an operations coordinator**, I want to dynamically filter products by store selection, so that I see accurate inventory for the fulfillment location
3. **As an operations coordinator**, I want a shopping cart interface with running totals, so that I can manage order value while building it
4. **As an operations coordinator**, I want to see product metadata (perishable status, weight), so that I can make informed decisions about delivery requirements

### Customer Service (Secondary Persona)
5. **As a customer service agent**, I want to expand any order to see its line items, so that I can quickly answer customer questions about their order contents
6. **As a customer service agent**, I want to search orders by product name, so that I can find all orders affected by a product recall or stock issue

### Warehouse Staff (Tertiary Persona)
7. **As a warehouse picker**, I want to see all line items with quantities in the order view, so that I can efficiently collect products for fulfillment
8. **As a warehouse manager**, I want to see aggregated product demand from orders, so that I can optimize inventory placement

## 4. Scope & Acceptance Criteria

### MVP Scope (v1)

#### Data Model Requirements
✅ **Order Line Item Entity**
- Create new `OrderLine` class in ontology with prefix `orderline`
- Properties: `line_of_order` (Order ref), `line_product` (Product ref), `quantity` (int), `line_amount` (float)
- Maintain referential integrity with Order and Product entities

✅ **Materialized View Updates**
- Extend `orders_search_source_mv` to include denormalized line items as JSONB array
- Create new `order_lines_flat_mv` for dedicated line item queries
- Ensure sub-2 second materialization latency for new line items

#### UI/UX Requirements
✅ **Order Creation Flow**
- Store selection dropdown that triggers product filtering
- Product selector with real-time inventory levels from selected store
- Shopping cart component showing:
  - Product name, quantity selector, unit price, line total
  - Perishable indicator for products requiring cold chain
  - Running order total with automatic calculation
- Validation preventing addition of out-of-stock items

✅ **Order Display Enhancement**
- Expandable row pattern in orders table (chevron icon to expand/collapse)
- Expanded view shows line items in nested table format
- Line item columns: Product, Quantity, Unit Price, Line Total, Stock Status
- Visual indicators for low stock or out-of-stock items

✅ **Search Integration**
- Update OpenSearch mapping to include line_items nested field
- Enable product name search across all orders
- Maintain existing search performance (<500ms p95 latency)

### Future Iterations (v2+)
- Bulk order import from CSV with line items
- Product substitution suggestions for out-of-stock items
- Order templates for frequent product combinations
- Analytics dashboard for product velocity by store
- Inventory reservation during order creation

### Non-Goals (Explicitly Out of Scope)
- Product catalog management (exists separately)
- Pricing engine modifications
- Inventory forecasting
- Product recommendations
- Order splitting across multiple stores
- Backorder management

## 5. Technical Approach Recommendations

### Data Modeling Strategy

#### Foundational Entity Design
**OrderLine as First-Class Entity**
- Model as subject-predicate-object triples following existing pattern
- ID format: `orderline:{order_number}-{line_number}` (e.g., `orderline:FM-1001-001`)
- Enables reuse across features: returns, refunds, analytics
- Maintains ontology consistency and validation

#### Materialization Architecture
```sql
-- New materialized view for line items
CREATE MATERIALIZED VIEW order_lines_flat_mv AS
SELECT
    subject_id AS line_id,
    MAX(CASE WHEN predicate = 'line_of_order' THEN object_value END) AS order_id,
    MAX(CASE WHEN predicate = 'line_product' THEN object_value END) AS product_id,
    MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT AS quantity,
    MAX(CASE WHEN predicate = 'line_amount' THEN object_value END)::DECIMAL AS line_amount
FROM triples
WHERE subject_id LIKE 'orderline:%'
GROUP BY subject_id;

-- Enhanced orders view with line items
CREATE MATERIALIZED VIEW orders_with_lines_mv AS
SELECT
    o.*,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'line_id', ol.line_id,
                'product_id', ol.product_id,
                'product_name', p.product_name,
                'quantity', ol.quantity,
                'line_amount', ol.line_amount,
                'perishable', p.perishable
            ) ORDER BY ol.line_id
        ) FILTER (WHERE ol.line_id IS NOT NULL),
        '[]'::jsonb
    ) AS line_items
FROM orders_flat_mv o
LEFT JOIN order_lines_flat_mv ol ON ol.order_id = o.order_id
LEFT JOIN products_flat_mv p ON p.product_id = ol.product_id
GROUP BY o.order_id;
```

#### Real-time Sync Strategy
- Leverage existing SUBSCRIBE streaming for line items
- Batch line item creates with order creation in single transaction
- Use Zero WebSocket for immediate UI updates
- Maintain consistency through triple-store ACID guarantees

### Performance Considerations
- **Query Performance**: Create composite indexes on (order_id, line_id) for fast expansion
- **Write Performance**: Batch insert line items as triple array (single API call)
- **Storage**: Estimate 5-10 line items per order average (acceptable overhead)
- **Cache Strategy**: Leverage Materialize's incremental computation for aggregations

### Integration Points
- **Zero Server**: Extend schema to include OrderLine collection
- **OpenSearch**: Update mapping for nested line_items field with product search
- **Materialize**: Add new views to existing cluster topology
- **API**: New endpoints for line item CRUD operations

## 6. Open Questions & Required Decisions

### Technical Architecture
1. **Inventory Reservation**: Should we implement optimistic locking for inventory during order creation to prevent overselling? Or handle this through eventual consistency with compensation?

2. **Line Item Limits**: Should we enforce a maximum number of line items per order for performance? Initial suggestion: 100 items per order.

3. **Price History**: Do we snapshot the product price at order time in the line item, or always reference current price? Recommendation: Snapshot for audit trail.

### Product Decisions
4. **Partial Fulfillment**: If some products become unavailable after order creation, do we allow partial fulfillment or require full cancellation?

5. **Product Bundles**: Should line items support product bundles/kits as a single line item, or expand them into components?

6. **Stock Visibility**: Should operators see exact stock numbers or just availability indicators (In Stock/Low Stock/Out)?

### Data Migration
7. **Historical Orders**: Do we backfill line items for existing orders from external systems, or start fresh from implementation date?

8. **Search Index**: Full reindex required for OpenSearch - schedule during maintenance window or rolling update?

### User Experience
9. **Mobile Responsiveness**: Is the expanded line items view required on mobile devices used by warehouse staff?

10. **Bulk Operations**: Do we need bulk edit capabilities for line items (e.g., update quantities for multiple items)?

## 7. Risk Assessment & Mitigation

### Technical Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Materialization lag increases with line items volume | Medium | High | Pre-aggregate common queries, monitor cluster capacity |
| WebSocket connection drops during order creation | Low | High | Implement optimistic UI updates with retry logic |
| Search performance degradation | Medium | Medium | Use nested fields efficiently, consider dedicated line items index |

### Operational Risks
| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Training gap for new UI complexity | High | Medium | Phased rollout with training materials |
| Data quality issues during migration | Medium | High | Validation scripts and reconciliation reports |
| Inventory sync delays causing overselling | Low | High | Real-time inventory checks with circuit breakers |

## 8. Dependencies

### Technical Dependencies
- Materialize cluster has capacity for additional views (ops to verify)
- OpenSearch cluster can handle nested field queries at scale
- Zero server supports complex collection relationships

### Organizational Dependencies
- Product team to provide inventory threshold rules
- Operations team to validate workflow changes
- Data team to assist with migration scripts
- QA team for comprehensive testing of order creation flow

### External Dependencies
- No third-party service dependencies identified
- No vendor API changes required

## 9. Success Criteria Validation

### Acceptance Tests (Functional)
1. Create order with 10 line items, verify all items persist correctly
2. Edit order to add/remove line items, verify totals recalculate
3. Expand order in table view, verify all line items display with correct data
4. Search for orders by product name, verify accurate results
5. Create order with out-of-stock item, verify validation prevents addition

### Performance Tests (Non-Functional)
1. Order creation with 50 line items completes in <3 seconds
2. Order expansion in UI renders in <500ms for 20 line items
3. Product search across 100k orders returns in <1 second
4. Materialized view refresh completes in <2 seconds for 1000 new line items

### Data Quality Tests
1. Line item quantities match inventory decrements
2. Order totals equal sum of line items
3. No orphaned line items after order deletion
4. Historical order data remains unchanged

## 10. Implementation Recommendations

### Phase 1: Foundation (Week 1-2)
1. Create OrderLine ontology class and properties
2. Implement triple-store CRUD for line items
3. Create materialized views and indexes
4. Update Zero schema and WebSocket handlers

### Phase 2: UI Development (Week 3-4)
1. Build product selector with store filtering
2. Implement shopping cart component
3. Add expandable rows to orders table
4. Integrate with real-time updates

### Phase 3: Search & Analytics (Week 5)
1. Update OpenSearch mappings
2. Implement product search functionality
3. Add line items to sync worker
4. Create operational reports

### Phase 4: Testing & Rollout (Week 6)
1. End-to-end testing with production-like data
2. Performance testing and optimization
3. User acceptance testing with operations team
4. Gradual rollout with feature flags

## Appendix: Technical Context

### Current State Architecture
- **Data Store**: PostgreSQL with triple-store pattern
- **Real-time Processing**: Materialize CDC from PostgreSQL
- **Search**: OpenSearch with denormalized views
- **API**: FastAPI with SQLAlchemy
- **UI**: React/TypeScript with TanStack Query
- **WebSocket**: Zero for real-time updates

### Reference Documentation
- [ONTOLOGY.md](./ONTOLOGY.md) - Ontology structure and validation
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview
- [DATA_MODEL.md](./DATA_MODEL.md) - Triple-store implementation details
- [OPENSEARCH_SINK_IMPLEMENTATION.md](../OPENSEARCH_SINK_IMPLEMENTATION.md) - Search ingest architecture

---

*This brief follows the Inspired product management framework, focusing on outcomes over outputs, validated learning, and empowered team collaboration.*