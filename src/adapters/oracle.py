import sys
from typing import Dict, List, Tuple, Any, Iterator
from src.adapters.base import SourceAdapter
from src.logging_utils import logger


def get_oracle_connection(config: Dict[str, Any]):
    try:
        import oracledb

        # 1. Inicializar el modo Thick apuntando a tu Instant Client descargado
        # (En Linux/macOS puedes dejar los paréntesis vacíos si configuraste LD_LIBRARY_PATH)
        try:
            oracledb.init_oracle_client(lib_dir=r"C:\Software\Oracle\instantclient_19_28")
        except Exception as e:
            # Si ya está inicializado o no existe la ruta en otra máquina, avisar o ignorar si ya fue configurado
            logger.debug(f"Instant Client init notice: {e}")

        # Modern python-oracledb
        conn = oracledb.connect(
            user=config["username"],
            password=config["password"],
            dsn=f"{config['host']}:{config.get('port', 1521)}/{config['service_name']}",
        )

        # Automatic LOB to string/bytes mapping
        def output_type_handler(cursor, name, default_type, size, precision, scale):
            if default_type == oracledb.DB_TYPE_CLOB:
                return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
            if default_type == oracledb.DB_TYPE_BLOB:
                return cursor.var(oracledb.DB_TYPE_LONG_RAW, arraysize=cursor.arraysize)

        conn.outputtypehandler = output_type_handler
        return conn
    except ImportError:
        try:
            import cx_Oracle

            # Legacy cx_Oracle fallback
            dsn = cx_Oracle.makedsn(
                config["host"],
                config.get("port", 1521),
                service_name=config["service_name"],
            )
            conn = cx_Oracle.connect(user=config["username"], password=config["password"], dsn=dsn)

            # Automatic LOB to string/bytes mapping for cx_Oracle
            def output_type_handler(cursor, name, default_type, size, precision, scale):
                if default_type == cx_Oracle.CLOB:
                    return cursor.var(cx_Oracle.LONG_STRING, arraysize=cursor.arraysize)
                if default_type == cx_Oracle.BLOB:
                    return cursor.var(cx_Oracle.LONG_BINARY, arraysize=cursor.arraysize)

            conn.outputtypehandler = output_type_handler
            return conn
        except ImportError:
            logger.error("Please install oracledb or cx_Oracle to connect to Oracle (e.g., 'pip install oracledb')")
            sys.exit(1)


class OracleAdapter(SourceAdapter):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.schema = config.get("schema", config["username"]).upper()
        self.conn = get_oracle_connection(config)
        self.cursor = self.conn.cursor()

    def get_tables(self) -> List[str]:
        query = """
            SELECT table_name 
            FROM all_tables 
            WHERE owner = :owner
        """
        self.cursor.execute(query, {"owner": self.schema})
        return [row[0] for row in self.cursor.fetchall()]

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT column_name, data_type, nullable, data_length, data_precision, data_scale
            FROM all_tab_columns
            WHERE owner = :owner AND table_name = :table_name
            ORDER BY column_id
        """
        self.cursor.execute(query, {"owner": self.schema, "table_name": table_name.upper()})
        cols = []
        for row in self.cursor.fetchall():
            cols.append(
                {
                    "name": row[0].lower(),  # Convert to lowercase for target standard
                    "type": row[1].upper(),
                    "nullable": row[2] == "Y",
                    "length": row[3],
                    "precision": row[4],
                    "scale": row[5],
                }
            )
        return cols

    def get_primary_keys(self, table_name: str) -> List[str]:
        query = """
            SELECT cols.column_name
            FROM all_constraints cons
            JOIN all_cons_columns cols 
              ON cons.constraint_name = cols.constraint_name 
              AND cons.owner = cols.owner
            WHERE cons.constraint_type = 'P'
              AND cons.owner = :owner
              AND cons.table_name = :table_name
            ORDER BY cols.position
        """
        self.cursor.execute(query, {"owner": self.schema, "table_name": table_name.upper()})
        return [row[0].lower() for row in self.cursor.fetchall()]

    def get_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        query = """
            SELECT
                a.column_name,
                c_pk.table_name AS foreign_table,
                b.column_name AS foreign_column
            FROM all_cons_columns a
            JOIN all_constraints c 
              ON a.constraint_name = c.constraint_name AND a.owner = c.owner
            JOIN all_constraints c_pk 
              ON c.r_constraint_name = c_pk.constraint_name AND c.r_owner = c_pk.owner
            JOIN all_cons_columns b 
              ON c_pk.constraint_name = b.constraint_name AND b.owner = c_pk.owner AND b.position = a.position
            WHERE c.constraint_type = 'R'
              AND c.owner = :owner
              AND c.table_name = :table_name
        """
        self.cursor.execute(query, {"owner": self.schema, "table_name": table_name.upper()})
        fks = []
        for row in self.cursor.fetchall():
            fks.append(
                {
                    "column": row[0].lower(),
                    "referred_table": row[1].lower(),
                    "referred_column": row[2].lower(),
                }
            )
        return fks

    def get_views(self) -> Dict[str, str]:
        # CLOB handling for text definitions in Oracle
        query = """
            SELECT view_name, text
            FROM all_views
            WHERE owner = :owner
        """
        self.cursor.execute(query, {"owner": self.schema})
        views = {}
        for row in self.cursor.fetchall():
            name = row[0].lower()
            text = row[1]
            if hasattr(text, "read"):
                text = text.read()
            views[name] = text
        return views

    def stream_rows(self, table_name: str, columns: List[str] = None, batch_size: int = 10000) -> Iterator[List[Tuple]]:
        col_list = ", ".join(f'"{c.upper()}"' for c in columns) if columns else "*"
        query = f'SELECT {col_list} FROM "{self.schema}"."{table_name.upper()}"'
        self.cursor.execute(query)
        while True:
            rows = self.cursor.fetchmany(batch_size)
            if not rows:
                break
            yield rows

    def close(self):
        self.cursor.close()
        self.conn.close()
