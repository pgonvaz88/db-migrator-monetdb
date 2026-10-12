import threading
import concurrent.futures
from typing import Dict, List, Any
from graphlib import TopologicalSorter, CycleError

from src.adapters.base import SourceAdapter
from src.adapters.postgres import PostgresAdapter
from src.adapters.oracle import OracleAdapter
from src.adapters.monetdb import MonetDBAdapter
from src.logging_utils import logger


def migrate_single_table(
    table_name: str,
    source_type: str,
    source_config: Dict[str, Any],
    target_config: Dict[str, Any],
    table_columns: Dict[str, List[Dict[str, Any]]],
    table_pks: Dict[str, List[str]],
    batch_size: int,
):
    """Migrate structure and stream data for a single table in a dedicated thread."""
    if source_type == "postgres":
        source: SourceAdapter = PostgresAdapter(source_config)
    else:
        source = OracleAdapter(source_config)

    target = MonetDBAdapter(target_config)
    try:
        # Create Table Structure
        target.create_table(
            table_name=table_name,
            columns=table_columns[table_name],
            pks=table_pks[table_name],
            source_type=source_type,
        )

        # Stream Data
        orig_table_name = next(t for t in source.get_tables() if t.lower() == table_name)
        logger.info(f"Streaming data for table: {table_name}")

        cols = [col["name"] for col in table_columns[table_name]]
        total_rows = 0

        for batch in source.stream_rows(orig_table_name, columns=cols, batch_size=batch_size):
            target.insert_batch(table_name, cols, batch)
            total_rows += len(batch)
            logger.info(f"  Inserted {total_rows} rows into {table_name}...")

        logger.info(f"Finished migrating {total_rows} rows for table {table_name}.")
    finally:
        source.close()
        target.close()


def run_migration(
    source_type: str,
    source_config: Dict[str, Any],
    target_config: Dict[str, Any],
    batch_size: int = 10000,
    exclude_tables: List[str] = None,
    exclude_columns: Dict[str, List[str]] = None,
    max_workers: int = 1,
):
    """Orchestrate entire migration process including metadata extraction, dependency resolution, parallel loading, foreign keys, and views."""
    logger.info(f"Starting migration from {source_type.upper()} to MonetDB (Workers: {max_workers})")

    if source_type == "postgres":
        source_meta: SourceAdapter = PostgresAdapter(source_config)
    elif source_type == "oracle":
        source_meta = OracleAdapter(source_config)
    else:
        raise ValueError(f"Unsupported source database type: {source_type}")

    target_meta = MonetDBAdapter(target_config)

    try:
        # 1. Fetch Schema Metadata
        logger.info("Extracting tables and metadata...")
        tables = source_meta.get_tables()
        logger.info(f"Found {len(tables)} tables to migrate.")

        DEFAULT_IGNORE = {
            "spatial_ref_sys",
            "geometry_columns",
            "geography_columns",
            "raster_columns",
            "raster_overviews",
            "pg_buffercache",
            "pg_stat_statements",
        }

        filtered_tables = []
        for t in tables:
            t_lower = t.lower()
            if t_lower in DEFAULT_IGNORE:
                continue
            if source_type == "oracle" and ("$" in t_lower or t_lower.startswith("bin$")):
                continue
            filtered_tables.append(t)

        tables = filtered_tables

        if exclude_tables:
            exclude_set = {t.lower() for t in exclude_tables}
            tables = [t for t in tables if t.lower() not in exclude_set]
            logger.info(f"Excluded user-specified tables. {len(tables)} tables remaining to migrate.")

        table_columns: Dict[str, List[Dict[str, Any]]] = {}
        table_pks: Dict[str, List[str]] = {}
        table_fks: Dict[str, List[Dict[str, Any]]] = {}

        if exclude_columns is None:
            exclude_columns = {}

        for table in tables:
            table_lower = table.lower()
            cols = source_meta.get_columns(table)
            pks = source_meta.get_primary_keys(table)
            fks = source_meta.get_foreign_keys(table)

            # Columns exclusion
            excl_cols = set(c.lower() for c in (exclude_columns.get(table, []) or exclude_columns.get(table_lower, [])))
            if excl_cols:
                cols = [c for c in cols if c["name"].lower() not in excl_cols]
                pks = [pk for pk in pks if pk.lower() not in excl_cols]
                fks = [
                    fk
                    for fk in fks
                    if fk["column"].lower() not in excl_cols and fk["referred_column"].lower() not in excl_cols
                ]
                logger.info(f"Excluding columns {sorted(excl_cols)} from table {table}")

            table_columns[table_lower] = cols
            table_pks[table_lower] = pks
            table_fks[table_lower] = fks

        # 2. Dependency Resolution (Topological Sort)
        dependencies: Dict[str, set] = {}
        for table in tables:
            table_lower = table.lower()
            dependencies[table_lower] = set()
            for fk in table_fks[table_lower]:
                ref_table = fk["referred_table"].lower()
                if ref_table in table_columns and ref_table != table_lower:
                    dependencies[table_lower].add(ref_table)

        ts = TopologicalSorter(dependencies)
        try:
            ts.prepare()
            logger.info("Topological sorting completed successfully. Graph prepared for migration.")
        except CycleError as e:
            logger.warning(
                f"Circular dependency detected: {e}. Falling back to sequential order. Foreign Key constraints will be applied at the very end to avoid load errors."
            )
            max_workers = 1
            ordered_tables = sorted(tables, key=lambda t: len(table_fks[t.lower()]))
            ordered_tables = [t.lower() for t in ordered_tables]

        # 3 & 4. Create Tables and Migrate Data
        logger.info("Starting table creation and data streaming...")
        if max_workers > 1:
            lock = threading.Lock()
            condition = threading.Condition(lock)
            errors = []

            def worker_task(table_name):
                try:
                    migrate_single_table(
                        table_name=table_name,
                        source_type=source_type,
                        source_config=source_config,
                        target_config=target_config,
                        table_columns=table_columns,
                        table_pks=table_pks,
                        batch_size=batch_size,
                    )
                    with condition:
                        ts.done(table_name)
                        condition.notify_all()
                except Exception as e:
                    logger.error(f"Failed to migrate table {table_name}: {e}")
                    with condition:
                        errors.append(e)
                        ts.done(table_name)
                        condition.notify_all()

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                with condition:
                    while ts.is_active():
                        ready_nodes = ts.get_ready()
                        if ready_nodes:
                            for node in ready_nodes:
                                executor.submit(worker_task, node)
                        else:
                            condition.wait()
            if errors:
                raise RuntimeError("One or more tables failed to migrate during parallel execution.")
        else:
            # Sequential execution fallback
            if "ordered_tables" not in locals():
                ordered_tables = []
                while ts.is_active():
                    ready = ts.get_ready()
                    ordered_tables.extend(ready)
                    for node in ready:
                        ts.done(node)

            for table_name in ordered_tables:
                migrate_single_table(
                    table_name=table_name,
                    source_type=source_type,
                    source_config=source_config,
                    target_config=target_config,
                    table_columns=table_columns,
                    table_pks=table_pks,
                    batch_size=batch_size,
                )

        # 5. Apply Foreign Key Constraints
        logger.info("Applying Foreign Key constraints...")
        ordered_tables = list(table_columns.keys())
        for table_name in ordered_tables:
            for fk in table_fks[table_name]:
                target_meta.add_foreign_key(table_name, fk)

        # 6. Migrate Views
        logger.info("Migrating database views...")
        views = source_meta.get_views()
        if views:
            logger.info(f"Found {len(views)} views to migrate.")
            for view_name, definition in views.items():
                target_meta.create_view(view_name, definition)
        else:
            logger.info("No views found to migrate.")

        logger.info("Migration finished successfully!")

    finally:
        source_meta.close()
        target_meta.close()
