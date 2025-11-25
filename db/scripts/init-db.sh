#!/bin/bash
# Database initialization script
# This runs automatically when the PostgreSQL container starts

set -e

echo "Initializing FreshMart database..."

# Create Zero databases for CVR and Change tracking
echo "Creating Zero databases..."
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE zero_cvr;" || echo "zero_cvr database already exists"
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE zero_change;" || echo "zero_change database already exists"

# Run migrations in order
for migration in /docker-entrypoint-initdb.d/migrations/*.sql; do
    if [ -f "$migration" ]; then
        echo "Running migration: $(basename $migration)"
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$migration"
    fi
done

# Check if we should seed demo data
if [ "${SEED_DEMO_DATA:-true}" = "true" ]; then
    echo "Seeding demo data..."
    for seed in /docker-entrypoint-initdb.d/seed/*.sql; do
        if [ -f "$seed" ]; then
            echo "Running seed: $(basename $seed)"
            psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$seed"
        fi
    done
fi

echo "Database initialization complete!"
