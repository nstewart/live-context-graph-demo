# Kafka Connect runtime for the search pipeline.
#
# Bundles three things on top of the Confluent base image (which already
# ships the Avro converter used to decode Materialize's Avro/Debezium records):
#   1. Aiven OpenSearch sink connector  -> writes docs to OpenSearch (UPSERT)
#   2. The embedding SMT                -> calls our OpenAI-compatible service
#   3. Debezium core (for io.debezium.transforms.HeaderToValue) -> copies the
#      mz_timestamp Kafka header into the document value
FROM confluentinc/cp-kafka-connect:7.6.1

USER root

# Versions are build args so they're easy to bump if an artifact moves.
ARG SMT_VERSION=0.1.0
ARG AIVEN_OS_VERSION=3.1.0
ARG DEBEZIUM_VERSION=2.7.0.Final

ENV PLUGINS_DIR=/usr/local/share/kafka/plugins

RUN mkdir -p ${PLUGINS_DIR} \
    && microdnf install -y unzip || yum install -y unzip || true

# 1. Aiven OpenSearch sink connector (GitHub release zip).
RUN curl -fsSL -o /tmp/aiven-os.zip \
      "https://github.com/Aiven-Open/opensearch-connector-for-apache-kafka/releases/download/v${AIVEN_OS_VERSION}/opensearch-connector-for-apache-kafka-${AIVEN_OS_VERSION}.zip" \
    && unzip -q /tmp/aiven-os.zip -d ${PLUGINS_DIR}/ \
    && rm /tmp/aiven-os.zip

# 2. Embedding SMT (perfect-embeddings-smt) — diffs Debezium before/after and
#    calls an OpenAI-compatible /v1/embeddings endpoint.
RUN curl -fsSL -o /tmp/embedding-smt.zip \
      "https://github.com/MaterializeInc/perfect-embedding/releases/download/v${SMT_VERSION}/perfect-embeddings-smt-${SMT_VERSION}.zip" \
    && unzip -q /tmp/embedding-smt.zip -d ${PLUGINS_DIR}/ \
    && rm /tmp/embedding-smt.zip

# 3. Debezium core + api jars provide io.debezium.transforms.HeaderToValue.
RUN mkdir -p ${PLUGINS_DIR}/debezium-transforms \
    && curl -fsSL -o ${PLUGINS_DIR}/debezium-transforms/debezium-core.jar \
      "https://repo1.maven.org/maven2/io/debezium/debezium-core/${DEBEZIUM_VERSION}/debezium-core-${DEBEZIUM_VERSION}.jar" \
    && curl -fsSL -o ${PLUGINS_DIR}/debezium-transforms/debezium-api.jar \
      "https://repo1.maven.org/maven2/io/debezium/debezium-api/${DEBEZIUM_VERSION}/debezium-api-${DEBEZIUM_VERSION}.jar"

USER appuser
