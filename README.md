# Database Migrator to MonetDB

This utility is a robust, dynamic Python program designed to migrate PostgreSQL and Oracle databases to MonetDB for analytical purposes. It dynamically extracts metadata, constructs a dependency graph to sort tables topologically, creates schemas, streams rows efficiently in batches, and deploys foreign key constraints and database views.

## Features

- **Dynamic Schema Inspection**: Automatic reading of tables, column types, sizes, nullable attributes, primary keys, and foreign keys.
- **Topological Dependency Resolution**: Analyzes foreign keys to determine the correct order to create and populate tables (handling Many-to-Many intermediate tables automatically).
- **Graceful Cycle Handling**: If circular dependencies exist, the script warns you, creates the tables without constraints, populates them, and applies the foreign keys at the end.
- **Efficient Chunked Streaming**: Streams data from the source database using cursors in configurable batch sizes to avoid high memory consumption.
- **Database View Migration**: Automatically attempts to extract and deploy views to MonetDB, reporting any dialect mismatches.
- **Multi-Database Support**: Handles PostgreSQL (`psycopg` / `psycopg2`) and Oracle (`oracledb` / `cx_Oracle`).
- **Flexible Logging**: Real-time progress visualization in the console and optional log persistence to a file.

---

## Installation & Requirements

Ensure you have Python 3.9+ (due to `graphlib`). Create and activate a virtual environment, then install the dependencies:

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate

# 3. Install required database drivers
pip install -r requirements.txt
```

---

## Project Structure

```text
db_migrations/
├── config/                     # Configuration files (credentials, exclusions)
│   ├── oracle_config.json
│   └── postgres_config.json
├── data/                       # Dumps and database exports
│   └── postgres_export_20250220.sql
├── docs/                       # Project guides, table audits, and documentation
│   ├── AGENTS.md
│   ├── DEMAT tables.md
│   ├── local_databases_guide.md
│   ├── monetdb_guide.md
│   ├── oracle_guide.md
│   └── ORACLE_NCLOB_COLUMNS.md
├── scripts/                    # Automation and orchestration batch scripts
│   ├── import_dump.bat
│   ├── run_full_migration.bat
│   └── start_databases.bat
├── src/                        # Modular migration engine package
│   ├── __init__.py
│   ├── cli.py                  # CLI argument parser and config resolver
│   ├── logging_utils.py        # Logging configuration
│   ├── migrator.py             # Migration coordinator and parallel worker
│   └── adapters/               # Database adapters
│       ├── __init__.py
│       ├── base.py             # SourceAdapter interface
│       ├── monetdb.py          # MonetDB target adapter
│       ├── oracle.py           # Oracle source adapter
│       └── postgres.py         # PostgreSQL source adapter
├── tests/                      # Unit tests
│   ├── __init__.py
│   └── test_migrator.py
├── docker-compose.yml          # Local test containers (PostgreSQL & MonetDB)
├── migrator.py                 # Root CLI entry point wrapper (backward compatible)
└── README.md
```

---

## Configuration File

The migrator expects a JSON configuration file specifying connection credentials for the source and target. Configuration files are stored in the `config/` directory.

### Example for PostgreSQL Source (`config/postgres_config.example.json`)

```json
{
  "source": {
    "host": "postgres-server.example.com",
    "port": 5432,
    "database": "source_db",
    "username": "source_user",
    "password": "source_password",
    "schema": "public"
  },
  "target": {
    "host": "localhost",
    "port": 50000,
    "database": "demo",
    "username": "monetdb",
    "password": "monetdb",
    "schema": "migrated_postgres"
  },
  "exclude_tables": [
    "django_session",
    "django_admin_log",
    "application_audit_logs",
    "spatial_ref_sys"
  ],
  "exclude_columns": {
    "customer_orders": ["internal_debug_info"],
    "attachments": ["raw_file_bytes"]
  }
}
```

### Example for Oracle Source (`config/oracle_config.example.json`)

```json
{
  "source": {
    "host": "oracle-server.example.com",
    "port": 1521,
    "service_name": "ORCLPDB1",
    "username": "source_user",
    "password": "source_password",
    "schema": "SOURCE_SCHEMA"
  },
  "target": {
    "host": "localhost",
    "port": 50000,
    "database": "demo",
    "username": "monetdb",
    "password": "monetdb",
    "schema": "migrated_oracle"
  },
  "exclude_tables": [
    "audit_logs",
    "system_event_logs",
    "django_session",
    "temp_staging_table"
  ],
  "exclude_columns": {
    "user_activity": ["raw_payload", "binary_session_data"],
    "documents": ["cached_thumbnail_blob"]
  }
}
```

---

## Usage

Run the migration using either the root wrapper script `migrator.py` or the module syntax `python -m src.cli`. If the config path is not found directly, it is automatically resolved inside the `config/` directory.

```bash
# Migrate PostgreSQL to MonetDB and log output to console and file with 4 parallel workers
python migrator.py --source-type postgres --config config/postgres_config.json --batch-size 10000 --log-file postgres_migration.log --workers 4

# Migrate Oracle to MonetDB (using package module syntax)
python -m src.cli --source-type oracle --config config/oracle_config.json --batch-size 50000 --log-file oracle_migration.log --workers 4
```

### CLI Arguments

- `--source-type`: Source engine, either `postgres` or `oracle`.
- `--config`: Path to the JSON configuration file containing credentials (e.g. `config/oracle_config.json`).
- `--batch-size` _(Optional)_: Number of rows per batch chunk for data streaming. Default is `10000`.
- `--log-file` _(Optional)_: File path to save execution logs in addition to printing them to the console.
- `--workers` _(Optional)_: Number of parallel table migrations to execute concurrently. Uses a thread pool. Default is `1`.

---

## Troubleshooting & Important Considerations

### 1. Database Views and Dialect Mismatches

The script extracts view SQL definitions exactly as they are defined in PostgreSQL/Oracle. Because SQL dialects differ:

- Postgres-specific operators (e.g., `::text` casting or JSON extractors) or Oracle-specific functions (e.g., `DECODE`, `NVL`, custom packages) might fail execution on MonetDB.
- When a view fails to build, the script prints a `[WARNING]` containing the view name and the error. You can manually re-create these views in MonetDB using standard SQL.

### 2. Many-to-Many (M2M) Django Tables

Django Many-to-Many relations automatically generate a join/junction table referencing two primary tables. The migrator automatically resolves this dependency and ensures both target tables are created and loaded with data before attempting to populate the junction table or apply its constraints.

### 3. Case Sensitivity

MonetDB defaults to lowercasing unquoted table/column names. To ensure cross-compatibility, the migrator automatically maps and downcases all table names, column names, keys, and constraints.

### 4. Oracle National Character Set Mismatch (DPY-3012 Error)

If the Oracle instance uses an older national character set (such as `ID 871` / `CESU-8` encoding), `python-oracledb` in its default **Thin mode** will crash with a `NotSupportedError`.

- **Symptoms**: `oracledb.exceptions.NotSupportedError: DPY-3012: national character set id 871 is not supported by python-oracledb in thin mode`.
- **Solution**: The migrator forces the driver into **Thick mode** to delegate character encoding to Oracle's binary libraries. You must download the **Oracle Instant Client** zip from Oracle's website, extract it locally, and reference its folder path inside the `migrator.py` initialization code via `oracledb.init_oracle_client(lib_dir=...)` before establishing connections.

### 5. Complex Django Fields (JSONField / CLOB / BLOB Serialization)

When migrating Django schemas containing `JSONField` or large `TextField` mappings from Oracle (`CLOB`), the `oracledb` engine automatically fetches and parses valid JSON into active Python structures (`list` or `dict`).

- **Symptoms**: `pymonetdb.exceptions.ProgrammingError: type <class 'list'> not supported as value` during bulk insertions. This happens because MonetDB expects raw primitive datatypes inside the insertion array.
- **Solution**: The `insert_batch` routine has been hardened to intercept nested structural datatypes. Any Python `list` or `dict` object encountered inside a streaming row is automatically flattened back into a standard, compressed JSON string using `json.dumps()` right before feeding the batch array into `cursor.executemany()`. This ensures absolute compatibility with MonetDB analytical columns.

---

## Usage Examples

### Windows Batch Scripts

```bat
REM Start both databases and wait until they are ready
scripts\start_databases.bat

REM Import the default dump into Postgres
scripts\import_dump.bat

REM Import a custom dump file
scripts\import_dump.bat my_dump.sql

REM Run the full PostgreSQL -> MonetDB flow
scripts\run_full_migration.bat

REM Skip the dump import step
scripts\run_full_migration.bat --skip-import

REM Use a custom config file, batch size, and worker count
scripts\run_full_migration.bat --config postgres_config.json --batch-size 5000 --workers 4
```
