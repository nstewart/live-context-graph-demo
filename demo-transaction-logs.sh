#!/bin/bash
# Demo script to show transactional consistency through the search pipeline.
# All tuples from a single transaction share the same Materialize timestamp,
# which is carried through Redpanda (header `materialize-timestamp`) and lands
# on each OpenSearch doc as `mz_timestamp`.
#
# Pipeline: Materialize CREATE SINK -> Redpanda (orders/inventory)
#           -> Kafka Connect (kafka-connect, :8083) -> OpenSearch.
# The orders connector embeds via embedding-service (:8085).

set -e

# Detect docker compose command (prefer "docker compose" over "docker-compose")
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

echo "🎬 Demo: Transactional Consistency through the Search Pipeline"
echo "=============================================================="
echo ""
echo "This demo shows:"
echo "  1. All tuples from a transaction share the SAME Materialize timestamp"
echo "  2. The Kafka Connect sink propagates them into OpenSearch"
echo "  3. Updates are upserts on the same OpenSearch doc (key = order_id)"
echo "  4. Everything propagates atomically - no partial states"
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check the pipeline services are running
if ! $DOCKER_COMPOSE ps | grep -q "kafka-connect.*Up"; then
    echo "❌ kafka-connect service is not running"
    echo "   Run: docker compose up -d"
    exit 1
fi
if ! $DOCKER_COMPOSE ps | grep -q "embedding-service.*Up"; then
    echo "❌ embedding-service is not running"
    echo "   Run: docker compose up -d"
    exit 1
fi

echo "${BLUE}📋 Step 1: Watch the complete flow (PostgreSQL → Materialize → Redpanda → OpenSearch)${NC}"
echo "   This terminal will show:"
echo "     - Incoming write requests (api service)"
echo "     - Sink task / bulk-write activity (kafka-connect service)"
echo "     - Embedding requests for orders (embedding-service)"
echo ""
echo "   Filter: real pipeline signals (writes, sink tasks, bulk writes, embeddings, errors)"
echo ""
echo "Press Enter to start tailing logs..."
read

# Start log tail in background (api + the pipeline services)
echo "${GREEN}Starting log tail for api, kafka-connect, and embedding-service...${NC}"
echo ""

$DOCKER_COMPOSE logs -f --tail=0 api kafka-connect embedding-service \
  | grep --line-buffered -iE "POST /triples|WorkerSinkTask|BulkProcessor|POST /v1/embeddings|ERROR|FAILED|RUNNING" &
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
$DOCKER_COMPOSE exec -T api curl -s -X POST http://localhost:8080/triples/batch \
  -H "Content-Type: application/json" \
  -d @/tmp/demo_order.json > /dev/null

echo "✅ Order created with 3 line items"
echo ""
echo "${YELLOW}👀 Watch the logs above! You should see:${NC}"
echo "   API SERVICE:    the incoming POST /triples write"
echo "   KAFKA-CONNECT:  WorkerSinkTask polling and a BulkProcessor write to OpenSearch"
echo "   EMBEDDING:      a 'POST /v1/embeddings' call as the order's text is embedded"
echo ""
sleep 3

echo "${GREEN}Confirming propagation via probes (not log scraping)...${NC}"
echo "  orders index count:"
$DOCKER_COMPOSE exec -T opensearch curl -s "http://localhost:9200/orders/_count" || true
echo ""
echo "  orders sink consumer lag (LAG should drain to 0):"
$DOCKER_COMPOSE exec -T redpanda rpk group describe connect-orders-opensearch-sink 2>/dev/null || true
echo ""
sleep 2

echo ""
echo "${BLUE}📋 Step 3: Update the order status${NC}"
echo "   Materialize re-emits the order at a new timestamp; the sink upserts it"
echo ""
echo "Press Enter to update order status to PICKING..."
read

echo "${GREEN}Updating order status...${NC}"

$DOCKER_COMPOSE exec -T db psql -U postgres -d freshmart -c \
  "UPDATE triples SET object_value='PICKING', updated_at=NOW() WHERE subject_id='${ORDER_ID}' AND predicate='order_status';" \
  > /dev/null

echo "✅ Order status updated"
echo ""
echo "${YELLOW}👀 Watch the logs above! You should see:${NC}"
echo "   KAFKA-CONNECT:  another WorkerSinkTask poll + BulkProcessor write"
echo "                   (an UPSERT on the same doc, key = order_id)"
echo "   The doc's mz_timestamp advances to the new transaction's timestamp."
echo ""
sleep 3

echo ""
echo "${BLUE}📋 Step 4: Verify in OpenSearch${NC}"
echo "   Query OpenSearch to confirm the order was updated"
echo ""
echo "Press Enter to query OpenSearch..."
read

echo "${GREEN}Querying OpenSearch...${NC}"
$DOCKER_COMPOSE exec -T opensearch curl -s "http://localhost:9200/orders/_doc/${ORDER_ID}?pretty" | \
  grep -E '"order_id"|"order_status"|"mz_timestamp"|"line_items"' | head -10

echo ""
echo "✅ Demo complete!"
echo ""
echo "${YELLOW}Key Takeaways:${NC}"
echo "  ✓ PostgreSQL transaction writes all tuples atomically (28 triples)"
echo "  ✓ Materialize groups them by timestamp (all share the same mz_timestamp)"
echo "  ✓ The CREATE SINK emits them to Redpanda with a materialize-timestamp header"
echo "  ✓ Kafka Connect upserts them into OpenSearch (1 order + 3 lines = 1 orders doc)"
echo "  ✓ The orders connector embeds the doc text via embedding-service"
echo "  ✓ Sub-second propagation from PostgreSQL → OpenSearch"
echo ""

# Cleanup
kill $LOG_PID 2>/dev/null || true
rm -f /tmp/demo_order.json

echo "To watch / probe the pipeline manually:"
echo ""
echo "  # Write side + sink + embedding calls"
echo "  $DOCKER_COMPOSE logs -f api kafka-connect embedding-service | grep -iE 'POST /triples|WorkerSinkTask|BulkProcessor|POST /v1/embeddings|ERROR'"
echo ""
echo "  # Connector / task state"
echo "  curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq"
echo ""
echo "  # Consumer lag (caught-up check)"
echo "  $DOCKER_COMPOSE exec redpanda rpk group describe connect-orders-opensearch-sink"
echo ""
echo "  # Indexed doc counts"
echo "  curl -s localhost:9200/orders/_count ; curl -s localhost:9200/inventory/_count"
