#!/usr/bin/env python3
"""Initialize LangGraph checkpointer tables in PostgreSQL.

WARNING: This script drops all existing checkpoint tables and recreates them.
This will delete ALL conversation history and agent state.

This is intended for development and testing environments. For production use,
consider using a migration strategy that preserves existing data or add a
confirmation flag to prevent accidental data loss.

Environment Variables:
    SKIP_CHECKPOINT_DROP: Set to 'true' to skip dropping existing tables
                         (useful in production to preserve conversation history)
"""

import os
import sys

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from src.config import get_settings


def init_checkpointer():
    """Initialize checkpointer tables in PostgreSQL.

    WARNING: By default, this will DROP all existing checkpoint tables,
    deleting all conversation history. Set SKIP_CHECKPOINT_DROP=true
    to preserve existing data.
    """
    settings = get_settings()

    print(f"Initializing LangGraph checkpointer tables...")
    print(f"  Database: {settings.pg_host}:{settings.pg_port}/{settings.pg_database}")

    skip_drop = os.getenv("SKIP_CHECKPOINT_DROP", "").lower() == "true"

    try:
        if skip_drop:
            print("  Skipping table drop (SKIP_CHECKPOINT_DROP=true)")
        else:
            # WARNING: This drops all existing checkpoint tables and deletes conversation history
            print("  WARNING: Dropping existing checkpoint tables (this deletes all conversation history)...")
            print("  To preserve data, set SKIP_CHECKPOINT_DROP=true")
            with psycopg.connect(settings.pg_dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute("DROP TABLE IF EXISTS checkpoint_blobs CASCADE")
                    cur.execute("DROP TABLE IF EXISTS checkpoint_writes CASCADE")
                    cur.execute("DROP TABLE IF EXISTS checkpoints CASCADE")
                    cur.execute("DROP TABLE IF EXISTS checkpoint_migrations CASCADE")
                conn.commit()
            print("  ✓ Existing tables dropped")

        # Create checkpointer and setup tables with correct schema
        print("  Creating fresh checkpoint tables...")
        with PostgresSaver.from_conn_string(settings.pg_dsn) as checkpointer:
            checkpointer.setup()

        print("✓ Checkpointer tables created successfully!")
        return 0

    except Exception as e:
        print(f"✗ Error initializing checkpointer: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(init_checkpointer())
