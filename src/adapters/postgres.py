import sys
from typing import Dict, List, Tuple, Any, Iterator
from src.adapters.base import SourceAdapter
from src.logging_utils import logger


def get_postgres_connection(config: Dict[str, Any]):
    try:
        import psycopg

        # Psycopg 3
        conn_str = f"host={config['host']} port={config.get('port', 5432)} dbname={config['database']} user={config['username']} password={config['password']}"
        if "schema" in config:
            conn_str += f" options='-c search_path={config['schema']}'"
        return psycopg.connect(conn_str)
    except ImportError:
        try:
            import psycopg2

            # Psycopg 2 fallback
            return psycopg2.connect(
                host=config["host"],
                port=config.get("port", 5432),
                database=config["database"],
                user=config["username"],
                password=config["password"],
                options=f"-c search_path={config.get('schema', 'public')}",
            )
        except ImportError:
            logger.error("Please install psycopg or psycopg2 to connect to PostgreSQL (e.g., 'pip install psycopg')")
            sys.exit(1)


class PostgresAdapter(SourceAdapter):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.schema = config.get("schema", "public")
        self.conn = get_postgres_connection(config)
        self.cursor = self.conn.cursor()

    def get_tables(self) -> List[str]:
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s AND table_type = 'BASE TABLE';
        """
        self.cursor.execute(query, (self.schema,))
        return [row[0] for row in self.cursor.fetchall()]

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT column_name, data_type, is_nullable, character_maximum_length, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """
        self.cursor.execute(query, (self.schema, table_name))
        cols = []
        for row in self.cursor.fetchall():
            cols.append(
                {
                    "name": row[0],
                    "type": row[1].upper(),
                    "nullable": row[2] == "YES",
                    "length": row[3],
                    "precision": row[4],
                    "scale": row[5],
                }
            )
        return cols

    def get_primary_keys(self, table_name: str) -> List[str]:
        query = """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY kcu.ordinal_position;
        """
        self.cursor.execute(query, (self.schema, table_name))
        return [row[0] for row in self.cursor.fetchall()]

    def get_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = %s
              AND tc.table_name = %s;
        """
        self.cursor.execute(query, (self.schema, table_name))
        fks = []
        for row in self.cursor.fetchall():
            fks.append({"column": row[0], "referred_table": row[1], "referred_column": row[2]})
        return fks

    def get_views(self) -> Dict[str, str]:
        query = """
            SELECT viewname, definition
            FROM pg_views
            WHERE schemaname = %s;
        """
        self.cursor.execute(query, (self.schema,))
        return {row[0]: row[1] for row in self.cursor.fetchall()}

    def stream_rows(self, table_name: str, columns: List[str] = None, batch_size: int = 10000) -> Iterator[List[Tuple]]:
        col_list = ", ".join(f'"{c}"' for c in columns) if columns else "*"
        query = f'SELECT {col_list} FROM "{self.schema}"."{table_name}"'

        try:
            # Create a server-side cursor for memory efficiency
            server_cursor = self.conn.cursor(name=f"stream_{table_name}")
            server_cursor.execute(query)
            while True:
                rows = server_cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield rows
            server_cursor.close()
        except Exception:
            logger.warning(f"Fallback to client-side cursor for table: {table_name}")
            cursor = self.conn.cursor()
            cursor.execute(query)
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                yield rows
            cursor.close()

    def close(self):
        self.cursor.close()
        self.conn.close()
