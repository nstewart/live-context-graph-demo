FROM python:3.11-slim

WORKDIR /app

# Install postgresql-client for running SQL files. Retry apt to tolerate
# transient mirror flakiness during builds on metered networks.
RUN for i in 1 2 3; do \
        apt-get update && apt-get install -y --no-install-recommends postgresql-client && break || \
        (echo "apt attempt $i failed, retrying..." && sleep 5); \
    done && rm -rf /var/lib/apt/lists/*

# Install Python dependencies. Retries with extended timeouts handle the
# occasional pythonhosted.org DNS/connectivity hiccup observed during
# Docker Desktop builds on macOS.
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --retries 5 --timeout 60 \
    -r requirements.txt

# Copy scripts
COPY generate_load_test_data.py .
COPY seed_docker.sh /seed.sh
RUN chmod +x /seed.sh

CMD ["/seed.sh"]
