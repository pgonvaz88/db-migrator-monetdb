import unittest
from unittest.mock import MagicMock, patch

from src.adapters.monetdb import MonetDBAdapter
from src.migrator import run_migration


class TestMigratorTypeMapping(unittest.TestCase):
    def setUp(self):
        # Create a mock MonetDB adapter without triggering connection
        with patch("src.adapters.monetdb.get_monetdb_connection") as mock_conn:
            self.adapter = MonetDBAdapter(
                {
                    "host": "localhost",
                    "database": "db",
                    "username": "monetdb",
                    "password": "password",
                }
            )

    def test_map_postgres_types(self):
        # Test integer mappings
        self.assertEqual(self.adapter.map_postgres_type({"type": "INTEGER"}), "INTEGER")
        self.assertEqual(self.adapter.map_postgres_type({"type": "BIGINT"}), "BIGINT")

        # Test string mappings
        self.assertEqual(
            self.adapter.map_postgres_type({"type": "VARCHAR", "length": 255}),
            "VARCHAR(255)",
        )
        self.assertEqual(
            self.adapter.map_postgres_type({"type": "TEXT", "length": None}), "TEXT"
        )

        # Test decimals
        self.assertEqual(
            self.adapter.map_postgres_type(
                {"type": "NUMERIC", "precision": 10, "scale": 2}
            ),
            "DECIMAL(10,2)",
        )
        self.assertEqual(
            self.adapter.map_postgres_type(
                {"type": "DECIMAL", "precision": 5, "scale": 0}
            ),
            "DECIMAL(5,0)",
        )
        self.assertEqual(
            self.adapter.map_postgres_type(
                {"type": "NUMERIC", "precision": None, "scale": None}
            ),
            "DECIMAL(18,4)",
        )

    def test_map_oracle_types(self):
        # Test Oracle NUMBER configurations
        self.assertEqual(
            self.adapter.map_oracle_type(
                {"type": "NUMBER", "precision": 5, "scale": 0}
            ),
            "INTEGER",
        )
        self.assertEqual(
            self.adapter.map_oracle_type(
                {"type": "NUMBER", "precision": 12, "scale": 0}
            ),
            "BIGINT",
        )
        self.assertEqual(
            self.adapter.map_oracle_type(
                {"type": "NUMBER", "precision": 10, "scale": 2}
            ),
            "DECIMAL(10,2)",
        )
        self.assertEqual(
            self.adapter.map_oracle_type(
                {"type": "NUMBER", "precision": None, "scale": None}
            ),
            "DOUBLE",
        )

        # Test Oracle characters
        self.assertEqual(
            self.adapter.map_oracle_type({"type": "VARCHAR2", "length": 100}),
            "VARCHAR(100)",
        )
        self.assertEqual(
            self.adapter.map_oracle_type({"type": "CLOB", "length": None}), "TEXT"
        )


class TestMigrationOrchestration(unittest.TestCase):
    @patch("src.migrator.PostgresAdapter")
    @patch("src.migrator.MonetDBAdapter")
    def test_successful_migration_flow(self, mock_monet_class, mock_pg_class):
        mock_source = MagicMock()
        mock_pg_class.return_value = mock_source

        mock_source.get_tables.return_value = ["Users", "Orders"]
        mock_source.get_columns.side_effect = lambda t: {
            "Users": [
                {"name": "id", "type": "INTEGER", "nullable": False},
                {"name": "name", "type": "VARCHAR", "length": 50, "nullable": True},
            ],
            "Orders": [
                {"name": "id", "type": "INTEGER", "nullable": False},
                {"name": "user_id", "type": "INTEGER", "nullable": True},
            ],
        }[t]
        mock_source.get_primary_keys.side_effect = lambda t: {
            "Users": ["id"],
            "Orders": ["id"],
        }[t]
        mock_source.get_foreign_keys.side_effect = lambda t: {
            "Users": [],
            "Orders": [
                {
                    "column": "user_id",
                    "referred_table": "Users",
                    "referred_column": "id",
                }
            ],
        }[t]
        mock_source.stream_rows.return_value = [[(1, "Alice")], [(2, "Bob")]]
        mock_source.get_views.return_value = {
            "active_users": "SELECT * FROM users WHERE active = 1"
        }

        mock_target = MagicMock()
        mock_monet_class.return_value = mock_target

        run_migration(
            source_type="postgres",
            source_config={
                "host": "localhost",
                "database": "src",
                "username": "user",
                "password": "pwd",
            },
            target_config={
                "host": "localhost",
                "database": "tgt",
                "username": "user",
                "password": "pwd",
            },
        )

        create_calls = mock_target.create_table.call_args_list
        self.assertEqual(len(create_calls), 2)
        self.assertEqual(create_calls[0][1]["table_name"], "users")
        self.assertEqual(create_calls[1][1]["table_name"], "orders")
        self.assertTrue(mock_target.insert_batch.called)
        mock_target.add_foreign_key.assert_called_once_with(
            "orders",
            {"column": "user_id", "referred_table": "Users", "referred_column": "id"},
        )
        mock_target.create_view.assert_called_once_with(
            "active_users", "SELECT * FROM users WHERE active = 1"
        )

    @patch("src.migrator.PostgresAdapter")
    @patch("src.migrator.MonetDBAdapter")
    def test_migration_with_excluded_tables(self, mock_monet_class, mock_pg_class):
        mock_source = MagicMock()
        mock_pg_class.return_value = mock_source

        mock_source.get_tables.return_value = [
            "Users",
            "Orders",
            "Django_Session",
            "Sys_Logs",
        ]
        mock_source.get_columns.side_effect = lambda t: {
            "Users": [{"name": "id", "type": "INTEGER", "nullable": False}],
            "Orders": [{"name": "id", "type": "INTEGER", "nullable": False}],
        }[t]
        mock_source.get_primary_keys.return_value = ["id"]
        mock_source.get_foreign_keys.return_value = []
        mock_source.stream_rows.return_value = []
        mock_source.get_views.return_value = {}

        mock_target = MagicMock()
        mock_monet_class.return_value = mock_target

        run_migration(
            source_type="postgres",
            source_config={
                "host": "localhost",
                "database": "src",
                "username": "user",
                "password": "pwd",
            },
            target_config={
                "host": "localhost",
                "database": "tgt",
                "username": "user",
                "password": "pwd",
            },
            exclude_tables=["django_session", "SYS_LOGS"],
        )

        create_calls = mock_target.create_table.call_args_list
        self.assertEqual(len(create_calls), 2)
        created_tables = {call[1]["table_name"] for call in create_calls}
        self.assertEqual(created_tables, {"users", "orders"})


if __name__ == "__main__":
    unittest.main()
