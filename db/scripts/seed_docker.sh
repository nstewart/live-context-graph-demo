#!/bin/bash
# Seed demo data (Docker version)
# Runs inside the db-seed container

set -e

# These are set by docker-compose environment
PG_HOST=${PG_HOST:-db}
PG_PORT=${PG_PORT:-5432}
PG_USER=${PG_USER:-postgres}
PG_PASSWORD=${PG_PASSWORD:-postgres}
PG_DATABASE=${PG_DATABASE:-freshmart}

export PGPASSWORD=$PG_PASSWORD

echo "Seeding demo data into $PG_HOST:$PG_PORT/$PG_DATABASE..."

# Wait for database to be fully ready (belt and suspenders with healthcheck)
until psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -c '\q' 2>/dev/null; do
    echo "Waiting for database..."
    sleep 2
done

# Run ontology seed files (excludes bundleable orders which need entity data)
for seed in /seed/*.sql; do
    if [ -f "$seed" ]; then
        filename=$(basename "$seed")
        # Skip bundleable orders - must run after Python generator creates entities
        if [[ "$filename" == "demo_bundleable_orders.sql" ]]; then
            continue
        fi
        echo "Running seed: $filename"
        psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -f "$seed"
    fi
done

# Generate representative operational data with scale factor 0.01
# Scale 0.01 = ~10 stores, 500 orders, ~70K triples
# Use --clear to remove existing triples first (idempotent seeding)
echo "Generating demo operational data (scale=0.01)..."
python3 /app/generate_load_test_data.py --scale 0.01 --clear

# Run bundleable orders seed AFTER Python generator creates stores/customers/products
if [ -f "/seed/demo_bundleable_orders.sql" ]; then
    echo "Running seed: demo_bundleable_orders.sql (bundleable order demo data)"
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -f "/seed/demo_bundleable_orders.sql"
fi

echo "Seed complete!"
