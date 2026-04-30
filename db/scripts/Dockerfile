FROM python:3.11-slim

WORKDIR /app

# Install postgresql-client for running SQL files. Retry apt to tolerate
# transient mirror flakiness during builds on metered networks. The explicit
# `exit 1` on the final attempt is load-bearing — without it, the loop body's
# last expression would exit 0 after the third failure and the image would
# ship without postgresql-client.
RUN set -e; \
    for i in 1 2 3; do \
        if apt-get update && apt-get install -y --no-install-recommends postgresql-client; then \
            break; \
        fi; \
        if [ "$i" -eq 3 ]; then \
            echo "apt failed after 3 attempts" >&2; \
            exit 1; \
        fi; \
        echo "apt attempt $i failed, retrying..."; \
        sleep 5; \
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
