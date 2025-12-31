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

# Run ontology seed files first (excludes bundleable orders which need entity data)
for seed in "$SCRIPT_DIR/../seed"/*.sql; do
    if [ -f "$seed" ]; then
        filename=$(basename "$seed")
        # Skip bundleable orders - must run after Python generator creates entities
        if [[ "$filename" == "demo_bundleable_orders.sql" ]]; then
            continue
        fi
        echo "Running seed: $filename"
        # Use psql from Docker container to avoid requiring local psql installation
        docker-compose exec -T db psql -U "$PG_USER" -d "$PG_DATABASE" -f "/docker-entrypoint-initdb.d/seed/$filename"
    fi
done

# Generate representative operational data with scale factor 0.01
# Scale 0.01 = ~10 stores, 500 orders, ~70K triples
# This is the default that works reliably with Zero sync
echo "Generating demo operational data (scale=0.01)..."
python3 "$SCRIPT_DIR/generate_load_test_data.py" --scale 0.01

# Run bundleable orders seed AFTER Python generator creates stores/customers/products
if [ -f "$SCRIPT_DIR/../seed/demo_bundleable_orders.sql" ]; then
    echo "Running seed: demo_bundleable_orders.sql (bundleable order demo data)"
    docker-compose exec -T db psql -U "$PG_USER" -d "$PG_DATABASE" -f "/docker-entrypoint-initdb.d/seed/demo_bundleable_orders.sql"
fi

echo "Seed complete!"
