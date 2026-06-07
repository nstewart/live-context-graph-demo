#!/usr/bin/env sh
# Bootstraps the search pipeline's OpenSearch + Kafka Connect state:
#   1. Applies the OpenSearch index templates (so the connector's float array
#      becomes a knn_vector, etc. — schema.ignore=true means the connector
#      won't create these mappings itself).
#   2. Registers/updates the sink connectors (idempotent PUT of each config).
set -e

OS_URL="${OS_URL:-http://opensearch:9200}"
CONNECT_URL="${CONNECT_URL:-http://kafka-connect:8083}"

echo "Applying OpenSearch index templates..."
for f in /templates/*.json; do
  name="$(basename "$f" .json)"
  until curl -fsS -X PUT "$OS_URL/_index_template/${name}_template" \
        -H 'Content-Type: application/json' --data-binary @"$f" >/dev/null; do
    echo "  OpenSearch not ready for template '$name', retrying in 3s..."
    sleep 3
  done
  echo "  applied template: $name"
  # Pre-create the index so it gets the template mapping. The Aiven OpenSearch
  # connector's own auto-create bypasses composable index templates (it would
  # land a default/dynamic mapping — e.g. the wrong date format and a plain
  # float array instead of knn_vector), so we create it explicitly here.
  # 200 = created, 400 = already exists (resource_already_exists) — both fine.
  curl -fsS -o /dev/null -X PUT "$OS_URL/${name}" >/dev/null 2>&1 || true
  echo "  ensured index: $name"
done

echo "Waiting for Kafka Connect REST API at $CONNECT_URL ..."
until curl -fsS "$CONNECT_URL/connectors" >/dev/null 2>&1; do
  echo "  Kafka Connect not ready, retrying in 3s..."
  sleep 3
done

echo "Registering sink connectors..."
for f in /connectors/*.json; do
  name="$(basename "$f" .json)"
  echo "  -> $name"
  curl -fsS -X PUT "$CONNECT_URL/connectors/${name}/config" \
    -H 'Content-Type: application/json' --data-binary @"$f"
  echo ""
done

echo "Pipeline bootstrap complete."
