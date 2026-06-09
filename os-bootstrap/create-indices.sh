#!/usr/bin/env sh
# Bootstraps OpenSearch for the search pipeline:
#   1. Installs a composable index template per index, so the knn_vector /
#      synonym-analyzer mappings are applied whenever that index is (re)created.
#   2. Pre-creates the index so it materializes the template mapping. This is
#      required because the Aiven OpenSearch connector's own auto-create bypasses
#      composable templates (it would land a dynamic mapping — a plain float
#      array instead of knn_vector, wrong date types), so we must create the
#      index explicitly BEFORE the connector writes to it.
#   3. Sanity-checks that the orders embedding field is a knn_vector and warns
#      loudly if a stale/mis-mapped index is in the way.
set -eu

OS_URL="${OS_URL:-http://opensearch:9200}"
TEMPLATE_DIR="${INDEX_DIR:-/indices}/templates"

echo "Waiting for OpenSearch at ${OS_URL} ..."
until curl -sf "${OS_URL}/_cluster/health" >/dev/null 2>&1; do
  sleep 3
done
echo "OpenSearch is up."

for f in "${TEMPLATE_DIR}"/*.json; do
  name="$(basename "$f" .json)"

  # 1. Install/update the composable index template.
  code=$(curl -s -o /tmp/resp.json -w "%{http_code}" \
    -X PUT -H "Content-Type: application/json" \
    --data @"$f" \
    "${OS_URL}/_index_template/${name}_template")
  if [ "${code}" -ge 400 ]; then
    echo "Failed to install template '${name}_template' (HTTP ${code}):"; cat /tmp/resp.json; echo; exit 1
  fi
  echo "Installed index template '${name}_template'."

  # 2. Pre-create the index so it picks up the template mapping.
  #    200 = created; 400 = already exists (resource_already_exists) — both fine.
  code=$(curl -s -o /tmp/resp.json -w "%{http_code}" -X PUT "${OS_URL}/${name}")
  if [ "${code}" = "200" ]; then
    echo "Created index '${name}'."
  elif grep -q "resource_already_exists_exception" /tmp/resp.json 2>/dev/null; then
    echo "Index '${name}' already exists, leaving as-is."
  else
    echo "Failed to create index '${name}' (HTTP ${code}):"; cat /tmp/resp.json; echo; exit 1
  fi
done

# 3. Sanity check: the orders embedding field must be a knn_vector. A pre-existing
#    index with a dynamic mapping (e.g. from a prior deploy on a persistent volume)
#    would make kNN search fail with "Field ... is not knn_vector type". Templates
#    only apply at index creation, so a stale wrong index must be deleted once.
emb_type=$(curl -s "${OS_URL}/orders/_mapping?filter_path=orders.mappings.properties.embedding_text_embedding.type" 2>/dev/null || true)
case "$emb_type" in
  *knn_vector*) echo "orders.embedding_text_embedding is knn_vector — OK." ;;
  *) echo "WARNING: orders.embedding_text_embedding is NOT knn_vector (got: ${emb_type:-missing})."
     echo "         A stale/mis-mapped 'orders' index is in the way; kNN search will 502."
     echo "         Delete it so the template applies, then let the sink re-index:"
     echo "           curl -X DELETE ${OS_URL}/orders"
     echo "           # then reset the sink connector to re-consume (see OPS notes)"
     exit 1 ;;
esac

echo "Index bootstrap complete."
