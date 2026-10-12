import os
import sys
import json
import argparse

from src.logging_utils import setup_logging, logger
from src.migrator import run_migration


def find_config_file(config_path: str) -> str:
    """Find configuration file at path or under config/ directory."""
    if os.path.isfile(config_path):
        return config_path
    # Check under config/ directory
    alt_path = os.path.join("config", config_path)
    if os.path.isfile(alt_path):
        return alt_path
    # Check relative to project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root_alt = os.path.join(project_root, "config", config_path)
    if os.path.isfile(root_alt):
        return root_alt
    return config_path


def main():
    parser = argparse.ArgumentParser(description="Migrate PostgreSQL/Oracle database to MonetDB.")
    parser.add_argument(
        "--source-type",
        choices=["postgres", "oracle"],
        required=True,
        help="Source database type",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to JSON configuration file containing credentials",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10000,
        help="Row chunk size for streaming data",
    )
    parser.add_argument("--log-file", help="Path to write the migration log file")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel table migrations")

    args = parser.parse_args()

    setup_logging(args.log_file)

    config_file = find_config_file(args.config)
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read config file {args.config} (resolved as {config_file}): {e}")
        sys.exit(1)

    if "source" not in config or "target" not in config:
        logger.error("Configuration file must contain both 'source' and 'target' connection details.")
        sys.exit(1)

    exclude_tables = config.get("exclude_tables", [])
    exclude_columns = config.get("exclude_columns", {})
    run_migration(
        source_type=args.source_type,
        source_config=config["source"],
        target_config=config["target"],
        batch_size=args.batch_size,
        exclude_tables=exclude_tables,
        exclude_columns=exclude_columns,
        max_workers=args.workers,
    )


if __name__ == "__main__":
    main()
