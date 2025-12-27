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

# Run ontology seed files
for seed in /seed/*.sql; do
    if [ -f "$seed" ]; then
        filename=$(basename "$seed")
        echo "Running seed: $filename"
        psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DATABASE" -f "$seed"
    fi
done

# Generate representative operational data with scale factor 0.01
# Scale 0.01 = ~10 stores, 500 orders, ~70K triples
# Use --clear to remove existing triples first (idempotent seeding)
echo "Generating demo operational data (scale=0.01)..."
python3 /app/generate_load_test_data.py --scale 0.01 --clear

echo "Seed complete!"
