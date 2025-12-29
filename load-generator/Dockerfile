FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY loadgen/ loadgen/

# Install dependencies
RUN uv pip install --system -e .

# Expose control server port
EXPOSE 8084

# Run the control server
CMD ["python", "-m", "loadgen.server"]
