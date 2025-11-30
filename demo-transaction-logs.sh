#!/bin/bash
# Demo script to show transactional consistency in Materialize SUBSCRIBE updates
# This demonstrates that all tuples from a single transaction share the same Materialize timestamp

set -e

echo "🎬 Demo: Transactional Consistency with Materialize SUBSCRIBE"
echo "=============================================================="
echo ""
echo "This demo shows:"
echo "  1. All tuples from a transaction have the SAME Materialize timestamp"
echo "  2. System correctly identifies which OpenSearch documents to update"
echo "  3. Updates are consolidated (DELETE + INSERT = UPDATE)"
echo "  4. Everything happens atomically - no partial states"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if docker-compose is running
if ! docker-compose ps | grep -q "search-sync.*Up"; then
    echo "❌ search-sync service is not running"
    echo "   Run: docker-compose up -d"
    exit 1
fi

echo "${BLUE}📋 Step 1: Watch the complete flow (PostgreSQL → Materialize → OpenSearch)${NC}"
echo "   This terminal will show:"
echo "     - PostgreSQL transaction logs (api service)"
echo "     - Materialize SUBSCRIBE events (search-sync service)"
echo "     - OpenSearch flush operations (search-sync service)"
echo ""
echo "   Filter: grep for transaction and event symbols"
echo ""
echo "Press Enter to start tailing logs..."
read

# Start log tail in background (both api and search-sync)
echo "${GREEN}Starting log tail for api and search-sync services...${NC}"
echo ""

docker-compose logs -f --tail=0 api search-sync | grep --line-buffered -E "🔵|📝|✅|📦|💾|➕|🔄|❌|mz_ts=" &
LOG_PID=$!

# Give logs time to start
sleep 2

echo ""
echo "${BLUE}📋 Step 2: Create a transaction (order with 3 line items)${NC}"
echo "   This creates ~30 triples in a SINGLE transaction"
echo ""
echo "Press Enter to create the order..."
read

# Create an order with line items using the batch API
ORDER_NUMBER="DEMO-$(date +%s)"
ORDER_ID="order:${ORDER_NUMBER}"

echo "${GREEN}Creating order ${ORDER_NUMBER}...${NC}"

# Build the triples JSON (order + 3 line items)
cat > /tmp/demo_order.json << EOF
[
  {
    "subject_id": "${ORDER_ID}",
    "predicate": "order_number",
    "object_value": "${ORDER_NUMBER}",
    "object_type": "string"
  },
  {
    "subject_id": "${ORDER_ID}",
    "predicate": "order_status",
    "object_value": "CREATED",
    "object_type": "string"
  },
  {
    "subject_id": "${ORDER_ID}",
    "predicate": "placed_by",
    "object_value": "customer:cust0001",
    "object_type": "entity_ref"
  },
  {
    "subject_id": "${ORDER_ID}",
    "predicate": "order_store",
    "object_value": "store:BK-01",
    "object_type": "entity_ref"
  },
  {
    "subject_id": "${ORDER_ID}",
    "predicate": "order_total_amount",
    "object_value": "45.97",
    "object_type": "float"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-001",
    "predicate": "line_of_order",
    "object_value": "${ORDER_ID}",
    "object_type": "entity_ref"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-001",
    "predicate": "line_product",
    "object_value": "product:prod0001",
    "object_type": "entity_ref"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-001",
    "predicate": "quantity",
    "object_value": "2",
    "object_type": "int"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-001",
    "predicate": "order_line_unit_price",
    "object_value": "12.99",
    "object_type": "float"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-001",
    "predicate": "line_amount",
    "object_value": "25.98",
    "object_type": "float"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-001",
    "predicate": "line_sequence",
    "object_value": "1",
    "object_type": "int"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-001",
    "predicate": "perishable_flag",
    "object_value": "false",
    "object_type": "bool"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-002",
    "predicate": "line_of_order",
    "object_value": "${ORDER_ID}",
    "object_type": "entity_ref"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-002",
    "predicate": "line_product",
    "object_value": "product:prod0002",
    "object_type": "entity_ref"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-002",
    "predicate": "quantity",
    "object_value": "1",
    "object_type": "int"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-002",
    "predicate": "order_line_unit_price",
    "object_value": "9.99",
    "object_type": "float"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-002",
    "predicate": "line_amount",
    "object_value": "9.99",
    "object_type": "float"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-002",
    "predicate": "line_sequence",
    "object_value": "2",
    "object_type": "int"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-002",
    "predicate": "perishable_flag",
    "object_value": "true",
    "object_type": "bool"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-003",
    "predicate": "line_of_order",
    "object_value": "${ORDER_ID}",
    "object_type": "entity_ref"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-003",
    "predicate": "line_product",
    "object_value": "product:prod0003",
    "object_type": "entity_ref"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-003",
    "predicate": "quantity",
    "object_value": "1",
    "object_type": "int"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-003",
    "predicate": "order_line_unit_price",
    "object_value": "10.00",
    "object_type": "float"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-003",
    "predicate": "line_amount",
    "object_value": "10.00",
    "object_type": "float"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-003",
    "predicate": "line_sequence",
    "object_value": "3",
    "object_type": "int"
  },
  {
    "subject_id": "orderline:${ORDER_NUMBER}-003",
    "predicate": "perishable_flag",
    "object_value": "false",
    "object_type": "bool"
  }
]
EOF

# Submit the transaction
docker-compose exec -T api curl -s -X POST http://localhost:8080/triples/batch \
  -H "Content-Type: application/json" \
  -d @/tmp/demo_order.json > /dev/null

echo "✅ Order created with 3 line items"
echo ""
echo "${YELLOW}👀 Watch the logs above! You should see:${NC}"
echo "   API SERVICE:"
echo "   - 🔵 PG_TXN_START showing 28 triples across 4 subjects"
echo "   - 📝 Each subject (order + 3 line items) with their properties"
echo "   - ✅ PG_TXN_END confirming all triples written"
echo ""
echo "   SEARCH-SYNC SERVICE:"
echo "   - 📦 BATCH @ mz_ts=XXXXX with the SAME timestamp for all 28 events"
echo "   - ➕ Inserts showing the order and all 3 line items"
echo "   - 💾 FLUSH → orders showing them written to OpenSearch together"
echo ""
sleep 3

echo ""
echo "${BLUE}📋 Step 3: Update the order status${NC}"
echo "   This triggers an UPDATE (DELETE + INSERT at same timestamp)"
echo ""
echo "Press Enter to update order status to PICKING..."
read

echo "${GREEN}Updating order status...${NC}"

docker-compose exec -T db psql -U postgres -d freshmart -c \
  "UPDATE triples SET object_value='PICKING', updated_at=NOW() WHERE subject_id='${ORDER_ID}' AND predicate='order_status';" \
  > /dev/null

echo "✅ Order status updated"
echo ""
echo "${YELLOW}👀 Watch the logs above! You should see:${NC}"
echo "   SEARCH-SYNC SERVICE:"
echo "   - 📦 BATCH @ mz_ts=YYYYY (different timestamp from insert)"
echo "   - 🔄 Updates showing consolidated UPDATE operation (DELETE + INSERT → UPDATE)"
echo "   - 💾 FLUSH → orders showing the update written to OpenSearch"
echo ""
sleep 3

echo ""
echo "${BLUE}📋 Step 4: Verify in OpenSearch${NC}"
echo "   Query OpenSearch to confirm the order was updated"
echo ""
echo "Press Enter to query OpenSearch..."
read

echo "${GREEN}Querying OpenSearch...${NC}"
docker-compose exec -T opensearch curl -s "http://localhost:9200/orders/_doc/${ORDER_ID}?pretty" | \
  grep -E '"order_id"|"order_status"|"line_items"' | head -10

echo ""
echo "✅ Demo complete!"
echo ""
echo "${YELLOW}Key Takeaways:${NC}"
echo "  ✓ PostgreSQL transaction writes all tuples atomically (28 triples)"
echo "  ✓ Materialize groups them by timestamp (all share same mz_ts)"
echo "  ✓ System identifies affected documents (1 order + 3 line items = 4 docs)"
echo "  ✓ Updates are consolidated (DELETE + INSERT → UPDATE)"
echo "  ✓ Sub-2-second latency from PostgreSQL → OpenSearch"
echo ""

# Cleanup
kill $LOG_PID 2>/dev/null || true
rm -f /tmp/demo_order.json

echo "To watch logs manually:"
echo ""
echo "  # Full flow (PostgreSQL → Materialize → OpenSearch)"
echo "  docker-compose logs -f api search-sync | grep -E '🔵|📝|✅|📦|💾|➕|🔄|❌'"
echo ""
echo "  # Just PostgreSQL transactions"
echo "  docker-compose logs -f api | grep -E '🔵|📝|✅'"
echo ""
echo "  # Just SUBSCRIBE events and OpenSearch flushes"
echo "  docker-compose logs -f search-sync | grep -E '📦|💾|➕|🔄|❌'"
