#!/usr/bin/env python3
"""
Convenience entry point for the DB Migrator.
Delegates execution to src.cli.main() while maintaining full backward compatibility.
"""
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.logging_utils import setup_logging, logger
from src.adapters import (
    SourceAdapter,
    PostgresAdapter,
    OracleAdapter,
    MonetDBAdapter,
    get_postgres_connection,
    get_oracle_connection,
    get_monetdb_connection,
)
from src.migrator import migrate_single_table, run_migration
from src.cli import main

if __name__ == "__main__":
    main()
