# Kafka Connect worker for the embedding pipeline.
#
# Bundles two plugins on the Connect plugin.path:
#   1. The Aiven OpenSearch sink connector (writes Kafka -> OpenSearch).
#      NOTE: this demo targets OpenSearch 2.x, so we use the Aiven connector
#      (io.aiven.kafka.connect.opensearch.OpensearchSinkConnector) rather than
#      Confluent's Elasticsearch connector that perfect-embedding's own e2e uses.
#      It is published on GitHub releases (NOT Confluent Hub), so we fetch the
#      release archive directly.
#   2. The perfect-embeddings SMT (EmbeddingDiffTransform), which re-embeds only
#      changed text columns by diffing the Materialize Debezium before/after image.
#
# A small Alpine stage fetches and unpacks both archives (the cp-kafka-connect
# image has tar but no unzip), then we COPY the plugin dirs into the worker.

FROM alpine:3.20 AS fetch
RUN apk add --no-cache curl unzip tar
WORKDIR /plugins

# 1. Aiven OpenSearch sink connector (.tar of jars). --strip-components=1 flattens
#    the versioned top dir into a clean plugin directory of jars.
#    Pinned to 3.1.x: 4.x is compiled for Java 21, but cp-kafka-connect 7.9.7
#    runs Java 17 (UnsupportedClassVersionError otherwise). 3.1.1 is a Java 11
#    build and uses the io.aiven...OpensearchSinkConnector class (lowercase s).
ARG AIVEN_OS_CONNECTOR_VERSION=3.1.1
RUN curl -fsSL -o os.tar \
      "https://github.com/Aiven-Open/opensearch-connector-for-apache-kafka/releases/download/v${AIVEN_OS_CONNECTOR_VERSION}/opensearch-connector-for-apache-kafka-${AIVEN_OS_CONNECTOR_VERSION}.tar" \
    && mkdir -p opensearch-connector \
    && tar -xf os.tar -C opensearch-connector --strip-components=1 \
    && rm os.tar

# 2. perfect-embeddings SMT (.zip -> perfect-embeddings-smt/lib/*.jar).
ARG PERFECT_EMBEDDINGS_VERSION=0.1.0
RUN curl -fsSL -o pe.zip \
      "https://github.com/MaterializeInc/perfect-embedding/releases/download/v${PERFECT_EMBEDDINGS_VERSION}/perfect-embeddings-smt-${PERFECT_EMBEDDINGS_VERSION}.zip" \
    && unzip -q pe.zip \
    && rm pe.zip

FROM confluentinc/cp-kafka-connect:7.9.7
COPY --from=fetch /plugins/opensearch-connector /usr/share/local-connect-plugins/opensearch-connector
COPY --from=fetch /plugins/perfect-embeddings-smt /usr/share/local-connect-plugins/perfect-embeddings-smt
