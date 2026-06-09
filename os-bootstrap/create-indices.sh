#!/usr/bin/env sh
# Creates the OpenSearch indices with explicit mappings BEFORE the Kafka Connect
# sink starts writing. This is required because:
#   - the orders vector field (embedding_text_embedding) must be a knn_vector,
#     which OpenSearch will never infer from a dynamic float[] mapping; and
#   - inventory needs its custom ingredient_synonyms analyzer.
# The sink connectors run with schema.ignore=true so they will NOT override
# these mappings.
#
# Idempotent: a 400 "resource_already_exists_exception" is treated as success.
set -eu

OS_URL="${OS_URL:-http://opensearch:9200}"
DIR="${INDEX_DIR:-/indices}"

echo "Waiting for OpenSearch at ${OS_URL} ..."
until curl -sf "${OS_URL}/_cluster/health" >/dev/null 2>&1; do
  sleep 3
done
echo "OpenSearch is up."

create_index() {
  name="$1"
  file="$2"
  code=$(curl -s -o /tmp/resp.json -w "%{http_code}" \
    -X PUT -H "Content-Type: application/json" \
    --data @"${file}" \
    "${OS_URL}/${name}")
  if [ "${code}" = "200" ]; then
    echo "Created index '${name}'."
  elif grep -q "resource_already_exists_exception" /tmp/resp.json 2>/dev/null; then
    echo "Index '${name}' already exists, leaving as-is."
  else
    echo "Failed to create index '${name}' (HTTP ${code}):"
    cat /tmp/resp.json; echo
    exit 1
  fi
}

create_index "orders" "${DIR}/orders-index.json"
create_index "inventory" "${DIR}/inventory-index.json"

echo "Index bootstrap complete."
