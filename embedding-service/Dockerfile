FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so it's baked into the image (no
# network/cold-start cost on first request). ~130MB ONNX weights.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8085

# Hypercorn handles both HTTP/1.1 and HTTP/2 cleartext (h2c) upgrades, which the
# Kafka Connect SMT's java.net.http client negotiates by default.
CMD ["hypercorn", "src.main:app", "--bind", "0.0.0.0:8085"]
