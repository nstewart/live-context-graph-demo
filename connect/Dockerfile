# Kafka Connect worker for the embedding pipeline.
#
# Bundles two plugins on the Connect plugin.path:
#   1. The Aiven OpenSearch sink connector (writes Kafka -> OpenSearch).
#      NOTE: this demo targets OpenSearch 2.x, so we use the Aiven connector
#      (io.aiven.kafka.connect.opensearch.OpensearchSinkConnector) rather than
#      Confluent's Elasticsearch connector that perfect-embedding's own e2e uses.
#   2. The perfect-embeddings SMT (EmbeddingDiffTransform), which re-embeds only
#      changed text columns by diffing the Materialize Debezium before/after image.
#
# We install the SMT from the prebuilt GitHub release zip to avoid a Maven build
# stage. To build from source instead, see the multi-stage Dockerfile in
# perfect-embedding/e2e/connect/Dockerfile.
FROM confluentinc/cp-kafka-connect:7.9.7

USER root

# 1. OpenSearch sink connector (Aiven). Version pinned for reproducibility.
RUN confluent-hub install --no-prompt aiven/opensearch-connector-for-apache-kafka:3.1.1

# 2. perfect-embeddings SMT, from the GitHub release.
ARG PERFECT_EMBEDDINGS_VERSION=0.1.0
RUN mkdir -p /usr/share/local-connect-plugins/perfect-embeddings-smt \
    && curl -fsSL -o /tmp/pe.zip \
       "https://github.com/MaterializeInc/perfect-embedding/releases/download/v${PERFECT_EMBEDDINGS_VERSION}/perfect-embeddings-smt-${PERFECT_EMBEDDINGS_VERSION}.zip" \
    && unzip -o /tmp/pe.zip -d /usr/share/local-connect-plugins/perfect-embeddings-smt \
    && rm /tmp/pe.zip

USER appuser
