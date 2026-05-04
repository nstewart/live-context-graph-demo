FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Pre-download the fastembed model into the image so the first vector search
# doesn't stall waiting on a HuggingFace download at runtime.
# FASTEMBED_CACHE_PATH is set here and inherited by the running container.
# HF_TOKEN is optional — pass it via `HF_TOKEN=hf_xxx make up-agent` to avoid
# HuggingFace rate limits on slow/shared connections.
ARG HF_TOKEN
ENV FASTEMBED_CACHE_PATH=/app/.fastembed_cache
RUN HF_TOKEN=${HF_TOKEN} python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

EXPOSE 8080

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
