FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the ONNX weights into the image so the first request doesn't pay a
# cold-start download: the embedding model (~130MB) and the cross-encoder
# reranker (~90MB) used by /rerank.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"
RUN python -c "from fastembed.rerank.cross_encoder import TextCrossEncoder; TextCrossEncoder(model_name='Xenova/ms-marco-MiniLM-L-6-v2')"

COPY app.py .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080
# --bind with HTTP/2 cleartext (h2c) support so the SMT's HTTP/2 client works.
CMD ["hypercorn", "app:app", "--bind", "0.0.0.0:8080"]
