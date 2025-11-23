#!/bin/bash
# Generate load test data for FreshMart
#
# Usage:
#   ./generate_data.sh              # Full dataset (~700K triples)
#   ./generate_data.sh --scale 0.1  # Small dataset (~70K triples)
#   ./generate_data.sh --clear      # Clear existing data first
#   ./generate_data.sh --dry-run    # Preview without inserting
#
# Environment:
#   Set PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE
#   Or use defaults (localhost, 5432, postgres, postgres, freshmart)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default database connection (can be overridden by environment)
export PG_HOST=${PG_HOST:-localhost}
export PG_PORT=${PG_PORT:-5432}
export PG_USER=${PG_USER:-postgres}
export PG_PASSWORD=${PG_PASSWORD:-postgres}
export PG_DATABASE=${PG_DATABASE:-freshmart}

echo "Database: ${PG_HOST}:${PG_PORT}/${PG_DATABASE}"
echo ""

# Check for Python dependencies
if ! python3 -c "import psycopg2, faker" 2>/dev/null; then
    echo "Installing required Python packages..."
    pip3 install -q psycopg2-binary faker
fi

# Run the generator
python3 "${SCRIPT_DIR}/generate_load_test_data.py" "$@"
