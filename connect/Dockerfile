# Kafka Connect worker for the embedding pipeline.
#
# Bundles on the Connect plugin.path:
#   1. The Aiven OpenSearch sink connector (writes Kafka -> OpenSearch).
#      NOTE: this demo targets OpenSearch 2.x, so we use the Aiven connector
#      (io.aiven.kafka.connect.opensearch.OpensearchSinkConnector) rather than
#      Confluent's Elasticsearch connector that perfect-embedding's own e2e uses.
#      It is published on GitHub releases (NOT Confluent Hub), so we fetch the
#      release archive directly.
#   2. The perfect-embeddings SMT (EmbeddingDiffTransform), which re-embeds only
#      changed text columns by diffing the Materialize Debezium before/after image.
#   3. Debezium core+api jars, for io.debezium.transforms.HeaderToValue — copies
#      Materialize's `materialize-timestamp` Kafka header (the change's LOGICAL
#      timestamp) into the doc's mz_timestamp field, used by /api/search/impact.
# Plus the Jolokia JVM agent (loaded via KAFKA_OPTS in compose), which exposes
# the embedding SMT's JMX MBean over HTTP for /api/search/embedding-metrics.
#
# A small Alpine stage fetches and unpacks everything (the cp-kafka-connect
# image has tar but no unzip), then we COPY it into the worker.

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

# 3. Debezium core + api jars provide io.debezium.transforms.HeaderToValue.
ARG DEBEZIUM_VERSION=2.7.0.Final
RUN mkdir -p debezium-transforms \
    && curl -fsSL -o debezium-transforms/debezium-core.jar \
      "https://repo1.maven.org/maven2/io/debezium/debezium-core/${DEBEZIUM_VERSION}/debezium-core-${DEBEZIUM_VERSION}.jar" \
    && curl -fsSL -o debezium-transforms/debezium-api.jar \
      "https://repo1.maven.org/maven2/io/debezium/debezium-api/${DEBEZIUM_VERSION}/debezium-api-${DEBEZIUM_VERSION}.jar"

# 4. Jolokia JVM agent — exposes JMX (the embedding SMT's diff counters) over
#    HTTP/JSON so the API can read them without a JMX/RMI client.
ARG JOLOKIA_VERSION=2.2.9
RUN curl -fsSL -o jolokia-agent.jar \
      "https://repo1.maven.org/maven2/org/jolokia/jolokia-agent-jvm/${JOLOKIA_VERSION}/jolokia-agent-jvm-${JOLOKIA_VERSION}-javaagent.jar"

FROM confluentinc/cp-kafka-connect:7.9.7
COPY --from=fetch /plugins/opensearch-connector /usr/share/local-connect-plugins/opensearch-connector
COPY --from=fetch /plugins/perfect-embeddings-smt /usr/share/local-connect-plugins/perfect-embeddings-smt
COPY --from=fetch /plugins/debezium-transforms /usr/share/local-connect-plugins/debezium-transforms
COPY --from=fetch /plugins/jolokia-agent.jar /usr/local/share/kafka/jolokia-agent.jar
