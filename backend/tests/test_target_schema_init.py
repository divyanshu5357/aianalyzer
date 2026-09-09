import inspect
import unittest
from unittest.mock import MagicMock
from app.database import schema_init
from app.ingestion import target_executor
from app.analytics import target_engine


class TestTargetSchemaInitialization(unittest.TestCase):
    def test_schema_init_contains_analytics_targets_ddl(self):
        """Verify ensure_all_database_tables includes analytics.targets creation and indexes."""
        source = inspect.getsource(schema_init.ensure_all_database_tables)
        self.assertIn("CREATE TABLE IF NOT EXISTS analytics.targets", source)
        self.assertIn("idx_targets_scope", source)
        self.assertIn("idx_targets_dataset_id", source)
        self.assertIn("idx_targets_batch_id", source)
        self.assertIn("target_batch_id", source)
        self.assertIn("target_leads", source)
        self.assertIn("target_admissions", source)
        self.assertIn("target_cucet", source)

    def test_target_executor_has_ensure_targets_table(self):
        """Verify target_executor defines ensure_targets_table and calls it in execute_target_ingestion."""
        self.assertTrue(hasattr(target_executor, "ensure_targets_table"))
        self.assertTrue(callable(target_executor.ensure_targets_table))

        exec_source = inspect.getsource(target_executor.execute_target_ingestion)
        self.assertIn("ensure_targets_table(db)", exec_source)

    def test_ensure_targets_table_executes_valid_ddl_on_db_session(self):
        """Verify ensure_targets_table executes DDL against provided db session."""
        mock_db = MagicMock()
        target_executor.ensure_targets_table(mock_db)
        self.assertTrue(mock_db.execute.called)
        executed_sql = str(mock_db.execute.call_args[0][0].text)
        self.assertIn("CREATE TABLE IF NOT EXISTS analytics.targets", executed_sql)
        self.assertTrue(mock_db.commit.called)

    def test_target_engine_handles_missing_targets_gracefully(self):
        """Verify target_engine.get_target_performance handles query exceptions gracefully without crashing."""
        mock_db = MagicMock()
        def mock_execute(sql, *args, **kwargs):
            if "analytics.targets" in str(sql):
                raise Exception('relation "analytics.targets" does not exist')
            m = MagicMock()
            m.mappings.return_value.all.return_value = []
            return m

        mock_db.execute.side_effect = mock_execute
        # Should catch error, rollback, and continue without raising
        result = target_engine.get_target_performance(db=mock_db, academic_year=2026)
        self.assertIsInstance(result, dict)
        self.assertIn("items", result)
        self.assertIn("summary", result)


if __name__ == "__main__":
    unittest.main()
