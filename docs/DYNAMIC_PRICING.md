# Dynamic Pricing Feature

Complete guide to FreshMart's real-time dynamic pricing system.

## Table of Contents

- [Overview](#overview)
- [Pricing Factors](#pricing-factors)
- [Implementation](#implementation)
- [Data Safety](#data-safety)
- [Usage Examples](#usage-examples)
- [Monitoring](#monitoring)

## Overview

FreshMart implements **real-time dynamic pricing** that adjusts product prices based on multiple factors including location, inventory levels, demand, and product characteristics.

**Key Benefits**:
- Maximize revenue through intelligent pricing
- Move perishable inventory faster with discounts
- Reflect supply and demand in real-time
- Account for regional cost differences
- Reward customers in underserved areas

**Real-Time Updates**:
- Prices computed in Materialize materialized view
- Updates propagate via CDC within milliseconds
- UI displays live prices instantly via WebSocket
- Orders created with current prices automatically
- No stale pricing or manual updates needed

## Pricing Factors

Dynamic pricing adjusts the base price using multiple multipliers and adjustments:

### 1. Zone-Based Pricing

Reflects regional cost and demand differences:

| Zone | Adjustment | Reason |
|------|-----------|--------|
| Manhattan | +15% | High rent, high demand |
| Brooklyn | +5% | Moderate premium |
| Queens | 0% (baseline) | Standard pricing |
| Bronx | -2% | Slight discount |
| Staten Island | -5% | Lower demand, incentivize |

**Example**:
- Base price: $10.00
- Manhattan store: $11.50 ($10.00 × 1.15)
- Staten Island store: $9.50 ($10.00 × 0.95)

### 2. Perishable Discounts

Move inventory faster to reduce waste:

- **Perishable items**: -5% discount
- Encourages quicker turnover
- Applies to dairy, produce, meat, etc.

**Example**:
- Milk (perishable) base price: $5.00
- With discount: $4.75 ($5.00 × 0.95)

### 3. Local Stock Adjustments

Premium pricing for low stock at specific stores:

| Stock Level | Adjustment | Reason |
|------------|-----------|--------|
| ≤ 5 units | +10% | Scarcity premium |
| ≤ 15 units | +3% | Moderate scarcity |
| > 15 units | 0% | Normal pricing |

**Example**:
- Product with 3 units in stock: +10% premium
- Base price $8.00 → $8.80

### 4. Popularity Rankings

Reward popular products with premium, discount less popular:

| Popularity Rank | Adjustment | Reason |
|----------------|-----------|--------|
| Top products | +20% | High demand premium |
| Mid-tier | +10% | Moderate demand |
| Less popular | -10% | Incentivize purchase |

**Calculation**:
- Top 20% of products by total sales → +20%
- Next 30% → +10%
- Bottom 50% → -10%

**Example**:
- Best-selling milk: +20% premium
- Base price $5.00 → $6.00

### 5. Scarcity Adjustments

Premium for products with low total stock across all stores:

| Total Stock Rank | Adjustment | Reason |
|-----------------|-----------|--------|
| Top 3 scarcest | +15% | High scarcity |
| Ranks 4-10 | +8% | Moderate scarcity |
| Others | 0% | Normal availability |

**Example**:
- Product with only 10 total units across all stores: +15%
- Base price $12.00 → $13.80

### 6. Demand Multipliers

Based on recent sales velocity and pricing trends:

- **High demand**: Increased multiplier (calculated from recent orders)
- **Declining demand**: Reduced multiplier
- **Stable demand**: Neutral multiplier

**Calculation**:
- Analyzes recent sales data
- Applies logarithmic scaling to prevent extreme adjustments
- Updates continuously as orders are placed

## Implementation

### Materialize View

The `inventory_items_with_dynamic_pricing` view computes live prices:

```sql
CREATE MATERIALIZED VIEW inventory_items_with_dynamic_pricing IN CLUSTER compute AS
SELECT
    inv.inventory_id,
    inv.store_id,
    inv.product_id,
    inv.stock_level,
    prod.base_price,

    -- Zone multiplier
    CASE stores.store_zone
        WHEN 'Manhattan' THEN 1.15
        WHEN 'Brooklyn' THEN 1.05
        WHEN 'Queens' THEN 1.0
        WHEN 'Bronx' THEN 0.98
        WHEN 'Staten Island' THEN 0.95
        ELSE 1.0
    END AS zone_multiplier,

    -- Perishable discount
    CASE WHEN prod.is_perishable THEN 0.95 ELSE 1.0 END AS perishable_multiplier,

    -- Local stock adjustment
    CASE
        WHEN inv.stock_level <= 5 THEN 1.10
        WHEN inv.stock_level <= 15 THEN 1.03
        ELSE 1.0
    END AS stock_multiplier,

    -- Popularity ranking
    COALESCE(popularity.rank_multiplier, 1.0) AS popularity_multiplier,

    -- Scarcity adjustment
    COALESCE(scarcity.scarcity_multiplier, 1.0) AS scarcity_multiplier,

    -- Demand multiplier
    COALESCE(demand.demand_multiplier, 1.0) AS demand_multiplier,

    -- Final price calculation
    COALESCE(
        prod.base_price *
        zone_multiplier *
        perishable_multiplier *
        stock_multiplier *
        popularity_multiplier *
        scarcity_multiplier *
        demand_multiplier,
        prod.base_price
    ) AS live_price

FROM inventory_flat inv
JOIN products_flat prod ON prod.product_id = inv.product_id
JOIN stores_flat stores ON stores.store_id = inv.store_id
LEFT JOIN popularity_rankings popularity ON popularity.product_id = prod.product_id
LEFT JOIN scarcity_adjustments scarcity ON scarcity.product_id = prod.product_id
LEFT JOIN demand_multipliers demand ON demand.product_id = prod.product_id
WHERE prod.base_price IS NOT NULL;
```

### Index for Fast Queries

```sql
CREATE INDEX inventory_items_with_dynamic_pricing_idx
IN CLUSTER serving
ON inventory_items_with_dynamic_pricing (inventory_id);
```

### Real-Time Updates

Changes propagate automatically:

```
Product price update → PostgreSQL → CDC → Materialize → View recalculates → Zero WebSocket → UI
                                                          (< 1 second)
```

## Data Safety

### NULL Handling

Robust NULL price handling prevents calculation failures:

```sql
-- COALESCE ensures NULL doesn't break calculations
COALESCE(
    prod.base_price * multipliers,
    prod.base_price  -- Fallback to base price if calculation fails
) AS live_price

-- Filter out items with NULL base prices entirely
WHERE prod.base_price IS NOT NULL
```

### Validation

- Items without base prices excluded from pricing view
- NULL multipliers default to 1.0 (no adjustment)
- All calculations include COALESCE for safety
- Division by zero prevented with NULLIF

### Agent Tool Integration

The `create_order` agent tool uses live prices automatically:

```python
# Fetch inventory with live dynamic pricing
inventory = await api.get(f"/freshmart/stores/inventory?store_id={store_id}")

# Use live_price from view (not base_price)
for item in line_items:
    inv_item = next(i for i in inventory if i["product_id"] == item["product_id"])
    unit_price = inv_item["live_price"]  # Dynamic price!
    line_amount = unit_price * quantity
```

## Usage Examples

### Order Creation with Dynamic Pricing

**UI Flow**:
1. User selects store (e.g., Manhattan)
2. Product dropdown shows inventory with live prices
3. User adds "Whole Milk" to cart
4. Cart displays: $5.75 (base $5.00 + 15% zone premium)
5. Order created with live price automatically

**API Flow**:
```bash
# Create order - prices are calculated from live_price
POST /freshmart/orders
{
  "customer_id": "customer:123",
  "store_id": "store:MN-01",  # Manhattan
  "line_items": [
    {
      "product_id": "product:MILK-WH",
      "quantity": 2
      # Price fetched from inventory_items_with_dynamic_pricing
      # Automatically uses $5.75 (not $5.00 base)
    }
  ]
}
```

### Agent-Based Order Creation

```bash
# Agent automatically uses live prices
docker compose exec agents python -m src.main chat \
  "Create an order for John at Manhattan store with 2 gallons of milk"

# Agent response:
# "I've created order FM-1234 for John Smith at FreshMart Manhattan 1
#  with 2 Whole Milk Gallons at $5.75 each (live price), total: $11.50"
```

### Price Comparison Across Stores

```bash
# Query inventory for same product at different stores
GET /freshmart/stores/inventory?product_id=product:MILK-WH

# Response shows different prices by zone:
[
  {
    "store_id": "store:MN-01",
    "store_zone": "Manhattan",
    "product_id": "product:MILK-WH",
    "base_price": 5.00,
    "live_price": 5.75  # +15% zone premium
  },
  {
    "store_id": "store:SI-01",
    "store_zone": "Staten Island",
    "product_id": "product:MILK-WH",
    "base_price": 5.00,
    "live_price": 4.75  # -5% zone discount
  }
]
```

## Monitoring

### View Live Prices

```bash
# Connect to Materialize
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -d materialize

# Query live prices
SET CLUSTER = serving;
SELECT
    product_id,
    store_id,
    base_price,
    live_price,
    ROUND((live_price / base_price - 1) * 100, 2) AS price_change_pct
FROM inventory_items_with_dynamic_pricing
WHERE product_id = 'product:MILK-WH'
ORDER BY live_price DESC;
```

**Example Output**:
```
product_id      | store_id    | base_price | live_price | price_change_pct
----------------|-------------|------------|------------|------------------
product:MILK-WH | store:MN-01 | 5.00       | 5.75       | 15.00
product:MILK-WH | store:BK-01 | 5.00       | 5.25       | 5.00
product:MILK-WH | store:QN-01 | 5.00       | 5.00       | 0.00
product:MILK-WH | store:BX-01 | 5.00       | 4.90       | -2.00
product:MILK-WH | store:SI-01 | 5.00       | 4.75       | -5.00
```

### Price Analytics

```sql
-- Average price adjustment by zone
SELECT
    s.store_zone,
    COUNT(*) AS item_count,
    AVG(inv.live_price / prod.base_price - 1) * 100 AS avg_adjustment_pct,
    MIN(inv.live_price) AS min_price,
    MAX(inv.live_price) AS max_price
FROM inventory_items_with_dynamic_pricing inv
JOIN stores_flat s ON s.store_id = inv.store_id
JOIN products_flat prod ON prod.product_id = inv.product_id
GROUP BY s.store_zone
ORDER BY avg_adjustment_pct DESC;
```

### Price Change Events

```bash
# Watch inventory docs flow through the Kafka Connect sink to OpenSearch
docker compose logs -f kafka-connect | grep -i inventory

# Inventory docs land in the OpenSearch `inventory` index via the inventory sink connector.
# Check the indexed doc count:
curl localhost:9200/inventory/_count

# Or monitor Materialize view updates
docker compose logs -f zero-server | grep "inventory"
```

### Troubleshooting

**NULL Prices**:
```sql
-- Find items with NULL prices
SELECT inventory_id, product_id, store_id, base_price
FROM inventory_flat inv
JOIN products_flat prod ON prod.product_id = inv.product_id
WHERE prod.base_price IS NULL;
```

**Unexpected Prices**:
```sql
-- Debug pricing calculation for specific item
SELECT
    inv.inventory_id,
    prod.base_price,
    zone_multiplier,
    perishable_multiplier,
    stock_multiplier,
    popularity_multiplier,
    scarcity_multiplier,
    demand_multiplier,
    live_price,
    -- Show calculation breakdown
    ROUND(prod.base_price * zone_multiplier, 2) AS after_zone,
    ROUND(prod.base_price * zone_multiplier * perishable_multiplier, 2) AS after_perishable,
    ROUND(prod.base_price * zone_multiplier * perishable_multiplier * stock_multiplier, 2) AS after_stock
FROM inventory_items_with_dynamic_pricing inv
JOIN products_flat prod ON prod.product_id = inv.product_id
WHERE inv.inventory_id = 'inventory:specific-id';
```

## Future Enhancements

Potential improvements to dynamic pricing:

1. **Time-Based Pricing**
   - Peak hours premium
   - Off-peak discounts
   - Weekend/holiday adjustments

2. **Customer-Specific Pricing**
   - Loyalty discounts
   - First-time customer promotions
   - Volume discounts

3. **Competitive Pricing**
   - Market price monitoring
   - Automatic competitive adjustments

4. **Machine Learning**
   - Predictive demand modeling
   - Optimal price point calculation
   - Churn prevention pricing

5. **A/B Testing**
   - Test different pricing strategies
   - Measure impact on conversion
   - Optimize revenue per customer

## See Also

- [Architecture Guide](ARCHITECTURE.md) - Real-time data flow
- [Ontology Guide](ONTOLOGY_GUIDE.md) - Adding pricing factors
- [UI Guide](UI_GUIDE.md) - Live price display in UI
- [API Reference](API_REFERENCE.md) - Inventory and order endpoints
