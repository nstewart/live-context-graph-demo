#!/usr/bin/env python3
"""Initialize LangGraph checkpointer tables in PostgreSQL."""

import sys

from langgraph.checkpoint.postgres import PostgresSaver

from src.config import get_settings


def init_checkpointer():
    """Initialize checkpointer tables in PostgreSQL."""
    settings = get_settings()

    print(f"Initializing LangGraph checkpointer tables...")
    print(f"  Database: {settings.pg_host}:{settings.pg_port}/{settings.pg_database}")

    try:
        # Create checkpointer and setup tables
        with PostgresSaver.from_conn_string(settings.pg_dsn) as checkpointer:
            checkpointer.setup()

        print("✓ Checkpointer tables created successfully!")
        return 0

    except Exception as e:
        print(f"✗ Error initializing checkpointer: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(init_checkpointer())
