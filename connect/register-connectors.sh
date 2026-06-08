#!/usr/bin/env sh
# Registers the OpenSearch sink connectors with the Kafka Connect REST API.
# Run as a one-shot once Kafka Connect is up (see the connect-bootstrap service).
#
# Each file under /connectors is the full {name, config} body for
# POST /connectors. 409 (already exists) is treated as success so the
# bootstrap is safe to re-run; to change a connector's config, delete it first:
#   curl -X DELETE http://localhost:8083/connectors/orders-opensearch-sink
set -eu

CONNECT_URL="${CONNECT_URL:-http://connect:8083}"
CONNECTOR_DIR="${CONNECTOR_DIR:-/connectors}"

echo "Waiting for Kafka Connect at ${CONNECT_URL} ..."
until curl -sf "${CONNECT_URL}/connectors" >/dev/null 2>&1; do
  sleep 3
done
echo "Kafka Connect is up."

for cfg in "${CONNECTOR_DIR}"/*.json; do
  echo "Registering connector from ${cfg}"
  code=$(curl -s -o /tmp/resp.json -w "%{http_code}" \
    -X POST -H "Content-Type: application/json" \
    --data @"${cfg}" \
    "${CONNECT_URL}/connectors")
  echo "  -> HTTP ${code}"
  case "${code}" in
    200|201|409) ;;
    *) cat /tmp/resp.json; echo; exit 1 ;;
  esac
done

echo "All connectors registered."
