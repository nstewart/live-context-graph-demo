FROM python:3.11-slim

WORKDIR /app

# Install postgresql-client for running SQL files
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy scripts
COPY generate_load_test_data.py .
COPY seed_docker.sh /seed.sh
RUN chmod +x /seed.sh

CMD ["/seed.sh"]
