#!/bin/bash
# Seed demo data

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# Default values
PG_HOST=${PG_HOST:-localhost}
PG_PORT=${PG_PORT:-5432}
PG_USER=${PG_USER:-postgres}
PG_PASSWORD=${PG_PASSWORD:-postgres}
PG_DATABASE=${PG_DATABASE:-freshmart}

export PGPASSWORD=$PG_PASSWORD

echo "Seeding demo data into $PG_HOST:$PG_PORT/$PG_DATABASE..."

# Check and install Python dependencies first
MISSING_DEPS=false
if ! python3 -c "import psycopg2" 2>/dev/null; then
    MISSING_DEPS=true
fi
if ! python3 -c "import faker" 2>/dev/null; then
    MISSING_DEPS=true
fi

if [ "$MISSING_DEPS" = true ]; then
    echo "Installing Python dependencies..."
    if ! python3 -m pip --version &>/dev/null; then
        echo "Error: pip is not available. Please install pip3 first."
        exit 1
    fi
    python3 -m pip install -q -r "$SCRIPT_DIR/requirements.txt" || {
        echo "Error: Failed to install dependencies. Please run:"
        echo "  python3 -m pip install -r db/scripts/requirements.txt"
        exit 1
    }
fi

# Run ontology seed files first
for seed in "$SCRIPT_DIR/../seed"/*.sql; do
    if [ -f "$seed" ]; then
        filename=$(basename "$seed")
        echo "Running seed: $filename"
        psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -f "$seed"
    fi
done

# Install dependencies if needed
if ! python3 -c "import psycopg2; import faker" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -q -r "$SCRIPT_DIR/requirements.txt" || {
        echo "Error: Failed to install dependencies. Please run:"
        echo "  pip3 install -r db/scripts/requirements.txt"
        exit 1
    }
fi

# Generate representative operational data with scale factor 0.01
echo "Generating demo operational data (scale=0.01)..."
python3 "$SCRIPT_DIR/generate_load_test_data.py" --scale 0.01

echo "Seed complete!"
