from typing import Dict, List, Tuple, Any, Iterator


class SourceAdapter:
    """Base interface for all source database adapters (Postgres, Oracle)."""

    def get_tables(self) -> List[str]:
        raise NotImplementedError()

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        raise NotImplementedError()

    def get_primary_keys(self, table_name: str) -> List[str]:
        raise NotImplementedError()

    def get_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        raise NotImplementedError()

    def get_views(self) -> Dict[str, str]:
        raise NotImplementedError()

    def stream_rows(self, table_name: str, columns: List[str] = None, batch_size: int = 10000) -> Iterator[List[Tuple]]:
        raise NotImplementedError()

    def close(self):
        raise NotImplementedError()
