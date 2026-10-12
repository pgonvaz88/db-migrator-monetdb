import sys
import json
from typing import Dict, List, Tuple, Any
from src.logging_utils import logger


def get_monetdb_connection(config: Dict[str, Any]):
    try:
        import pymonetdb

        return pymonetdb.connect(
            hostname=config["host"],
            port=config.get("port", 50000),
            database=config["database"],
            username=config["username"],
            password=config["password"],
        )
    except ImportError:
        logger.error("Please install pymonetdb to connect to MonetDB (e.g., 'pip install pymonetdb')")
        sys.exit(1)


class MonetDBAdapter:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.conn = get_monetdb_connection(config)
        self.cursor = self.conn.cursor()
        self.schema = config.get("schema", "sys")
        
        # Ensure target schema exists if it is not the default system schema
        if self.schema and self.schema.lower() != "sys":
            try:
                self.cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
                self.conn.commit()
            except Exception as e:
                logger.debug(f"Schema creation notice for '{self.schema}': {e}")

    def map_postgres_type(self, col: Dict[str, Any]) -> str:
        t = col["type"]
        if t in ("INTEGER", "SERIAL", "INT", "INT4"):
            return "INTEGER"
        elif t in ("BIGINT", "BIGSERIAL", "INT8"):
            return "BIGINT"
        elif t in ("SMALLINT", "SMALLSERIAL", "INT2"):
            return "SMALLINT"
        elif t in ("CHARACTER VARYING", "VARCHAR", "TEXT", "UUID", "JSON", "JSONB"):
            return f"VARCHAR({col['length']})" if col["length"] else "TEXT"
        elif t in ("CHARACTER", "CHAR"):
            return f"CHAR({col['length']})" if col["length"] else "CHAR(1)"
        elif t == "BOOLEAN":
            return "BOOLEAN"
        elif t in ("NUMERIC", "DECIMAL"):
            p, s = col["precision"], col["scale"]
            if p and s is not None:
                return f"DECIMAL({p},{s})"
            elif p:
                return f"DECIMAL({p},0)"
            return "DECIMAL(18,4)"
        elif t in ("DOUBLE PRECISION", "FLOAT8"):
            return "DOUBLE"
        elif t in ("REAL", "FLOAT4"):
            return "REAL"
        elif t in (
            "TIMESTAMP",
            "TIMESTAMP WITHOUT TIME ZONE",
            "TIMESTAMP WITH TIME ZONE",
            "TIMESTAMPTZ",
        ):
            return "TIMESTAMP"
        elif t == "DATE":
            return "DATE"
        elif t in ("BYTEA", "OID"):
            return "BLOB"
        else:
            logger.warning(f"Unknown PostgreSQL type: {t}, defaulting to TEXT")
            return "TEXT"

    def map_oracle_type(self, col: Dict[str, Any]) -> str:
        t = col["type"]
        if t == "NUMBER":
            p, s = col["precision"], col["scale"]
            if p is None and s is None:
                return "DOUBLE"
            elif s == 0 or s is None:
                if p <= 4:
                    return "SMALLINT"
                elif p <= 9:
                    return "INTEGER"
                else:
                    return "BIGINT"
            else:
                return f"DECIMAL({p},{s})"
        elif "CHAR" in t or t in ("CLOB", "NCLOB"):
            return f"VARCHAR({col['length']})" if col["length"] and col["length"] < 4000 else "TEXT"
        elif "DATE" in t or "TIMESTAMP" in t:
            return "TIMESTAMP"
        elif t in ("RAW", "BLOB", "LONG RAW"):
            return "BLOB"
        elif t == "FLOAT":
            return "DOUBLE"
        else:
            logger.warning(f"Unknown Oracle type: {t}, defaulting to TEXT")
            return "TEXT"

    def execute(self, sql: str, params: Any = None):
        try:
            if params:
                self.cursor.execute(sql, params)
            else:
                self.cursor.execute(sql)
        except Exception as e:
            logger.error(f"Error executing SQL: {sql[:200]}")
            logger.error(str(e))
            self.conn.rollback()
            raise e

    def create_table(
        self,
        table_name: str,
        columns: List[Dict[str, Any]],
        pks: List[str],
        source_type: str,
    ):
        table_name = table_name.lower()
        col_defs = []
        for col in columns:
            name = col["name"].lower()
            if source_type == "postgres":
                m_type = self.map_postgres_type(col)
            else:
                m_type = self.map_oracle_type(col)

            null_def = "" if col["nullable"] else " NOT NULL"
            col_defs.append(f'"{name}" {m_type}{null_def}')

        if pks:
            pk_cols = ", ".join(f'"{pk.lower()}"' for pk in pks)
            col_defs.append(f"CONSTRAINT pk_{table_name} PRIMARY KEY ({pk_cols})")

        defs = ",\n  ".join(col_defs)
        sql = f'CREATE TABLE "{self.schema}"."{table_name}" (\n  {defs}\n);'
        logger.info(f"Creating table: {table_name}")
        self.execute(f'DROP TABLE IF EXISTS "{self.schema}"."{table_name}" CASCADE;')
        self.execute(sql)
        self.conn.commit()

    def insert_batch(self, table_name: str, columns: List[str], batch: List[Tuple]):
        if not batch:
            return
        table_name = table_name.lower()
        cols = ", ".join(f'"{col.lower()}"' for col in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f'INSERT INTO "{self.schema}"."{table_name}" ({cols}) VALUES ({placeholders})'

        # Limpieza para CLOB/JSONField y formato tupla estricto de pymonetdb
        cleaned_batch = []
        for row in batch:
            cleaned_row = []
            for item in row:
                if isinstance(item, (list, dict)):
                    cleaned_row.append(json.dumps(item, ensure_ascii=False))
                else:
                    cleaned_row.append(item)
            cleaned_batch.append(tuple(cleaned_row))

        try:
            self.cursor.executemany(sql, cleaned_batch)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Batch insert failed for table {table_name}. Retrying individually for debugging...")
            for i, row in enumerate(batch):
                try:
                    self.cursor.execute(sql, row)
                    self.conn.commit()
                except Exception as row_err:
                    self.conn.rollback()
                    logger.error(f"Row {i} failed: {row}. Error: {row_err}")
            raise e

    def add_foreign_key(self, table_name: str, fk: Dict[str, Any]):
        table_name = table_name.lower()
        col = fk["column"].lower()
        ref_table = fk["referred_table"].lower()
        ref_col = fk["referred_column"].lower()
        constraint_name = f"fk_{table_name}_{col}"

        if len(constraint_name) > 63:
            constraint_name = constraint_name[:63]

        sql = f'ALTER TABLE "{self.schema}"."{table_name}" ADD CONSTRAINT "{constraint_name}" FOREIGN KEY ("{col}") REFERENCES "{self.schema}"."{ref_table}" ("{ref_col}");'
        logger.info(f"Adding foreign key: {table_name}.{col} -> {ref_table}.{ref_col}")
        try:
            self.execute(sql)
            self.conn.commit()
        except Exception as e:
            logger.warning(f"Could not apply FK constraint '{constraint_name}': {e}. Continuing anyway.")

    def create_view(self, view_name: str, definition_sql: str):
        view_name = view_name.lower()
        self.execute(f'DROP VIEW IF EXISTS "{self.schema}"."{view_name}" CASCADE;')

        sql = f'CREATE VIEW "{self.schema}"."{view_name}" AS {definition_sql}'
        logger.info(f"Creating view: {view_name}")
        try:
            self.execute(sql)
            self.conn.commit()
        except Exception as e:
            logger.warning(
                f"Could not create view '{view_name}' automatically. Dialect incompatibilities may exist. Error: {e}"
            )

    def close(self):
        self.cursor.close()
        self.conn.close()
