import unittest
from uuid import uuid4
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.database.schema_init import ensure_all_database_tables
from app.database.repository import get_active_dataset_info
from app.api.data_management import list_all_datasets


class TestWorkbookTypeSchemaRegression(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.test_dataset_ids = []

    def tearDown(self):
        if self.test_dataset_ids:
            self.db.execute(
                text("DELETE FROM system.datasets WHERE id::text = ANY(:ids)"),
                {"ids": self.test_dataset_ids},
            )
            self.db.commit()
        self.db.close()

    def test_schema_init_ensures_workbook_type_column_exists(self):
        """Verify that ensure_all_database_tables guarantees workbook_type column exists on system.datasets."""
        ensure_all_database_tables(self.db)

        col_check = self.db.execute(
            text(
                """
                SELECT column_name, data_type, column_default
                FROM information_schema.columns
                WHERE table_schema = 'system'
                  AND table_name = 'datasets'
                  AND column_name = 'workbook_type';
                """
            )
        ).mappings().first()

        self.assertIsNotNone(col_check, "system.datasets.workbook_type column must exist")
        self.assertIn("character varying", col_check["data_type"].lower())
        self.assertIn("'RAW'", str(col_check["column_default"]))

    def test_legacy_rows_upgrade_and_preserve_explicit_types(self):
        """
        Prove that existing rows remain intact:
        - NULL and 'raw_data' legacy entries resolve to 'RAW'
        - Explicit DIMENSION and TARGET entries are preserved
        - Existing metadata (academic_year, campus_name, dataset_name) is unchanged
        """
        id_legacy_null = str(uuid4())
        id_legacy_raw_data = str(uuid4())
        id_dimension = str(uuid4())
        id_target = str(uuid4())
        id_explicit_raw = str(uuid4())

        self.test_dataset_ids.extend([
            id_legacy_null,
            id_legacy_raw_data,
            id_dimension,
            id_target,
            id_explicit_raw,
        ])

        # Insert representative datasets with varying legacy states
        self.db.execute(
            text(
                """
                INSERT INTO system.datasets (
                    id, dataset_name, original_filename, workbook_type,
                    academic_year, campus_name, is_active, is_analytics_enabled, status
                ) VALUES
                (:id_null, 'Legacy NULL DS', 'legacy_null.xlsx', NULL, 2026, 'Mohali', FALSE, TRUE, 'normalized'),
                (:id_raw_data, 'Legacy raw_data DS', 'legacy_raw_data.xlsx', 'raw_data', 2026, 'Mohali', FALSE, TRUE, 'normalized'),
                (:id_dim, 'Dimension Master 2026', 'Dimension Tables 2026.xlsx', 'DIMENSION', 2026, 'Mohali', TRUE, TRUE, 'normalized'),
                (:id_tgt, 'Target Master 2026', 'Target Master 2026.xlsx', 'TARGET', 2026, 'Mohali', TRUE, TRUE, 'normalized'),
                (:id_raw, 'Active CRM RAW DS', 'CRM_2026.xlsx', 'RAW', 2026, 'Mohali', TRUE, TRUE, 'normalized')
                """
            ),
            {
                "id_null": id_legacy_null,
                "id_raw_data": id_legacy_raw_data,
                "id_dim": id_dimension,
                "id_tgt": id_target,
                "id_raw": id_explicit_raw,
            },
        )
        self.db.commit()

        # Run schema initializer to simulate startup migration
        ensure_all_database_tables(self.db)

        # Verify each row's workbook_type and metadata preservation
        rows = self.db.execute(
            text(
                """
                SELECT id, dataset_name, workbook_type, academic_year, campus_name
                FROM system.datasets
                WHERE id::text = ANY(:ids)
                """
            ),
            {"ids": self.test_dataset_ids},
        ).mappings().all()

        row_map = {str(r["id"]): r for r in rows}

        # 1. Legacy NULL must resolve to RAW
        self.assertEqual(row_map[id_legacy_null]["workbook_type"], "RAW")
        self.assertEqual(row_map[id_legacy_null]["dataset_name"], "Legacy NULL DS")

        # 2. Legacy 'raw_data' must resolve to RAW
        self.assertEqual(row_map[id_legacy_raw_data]["workbook_type"], "RAW")

        # 3. Explicit DIMENSION must be strictly preserved
        self.assertEqual(row_map[id_dimension]["workbook_type"], "DIMENSION")
        self.assertEqual(row_map[id_dimension]["academic_year"], 2026)

        # 4. Explicit TARGET must be strictly preserved
        self.assertEqual(row_map[id_target]["workbook_type"], "TARGET")
        self.assertEqual(row_map[id_target]["academic_year"], 2026)

        # 5. Explicit RAW must remain RAW
        self.assertEqual(row_map[id_explicit_raw]["workbook_type"], "RAW")

    def test_production_endpoints_succeed_without_undefined_column_error(self):
        """
        Verify that /api/admin/datasets and /api/data/active run without:
        psycopg2.errors.UndefinedColumn: column d.workbook_type does not exist
        """
        # Test repository active dataset query
        active_info = get_active_dataset_info(self.db)
        # Result can be None or dict, but MUST NOT raise an UndefinedColumn exception
        if active_info is not None:
            self.assertIn("id", active_info)

        # Test admin datasets list endpoint
        result = list_all_datasets()
        self.assertIn("total_datasets", result)
        self.assertIn("datasets", result)
        self.assertIsInstance(result["datasets"], list)
        for ds in result["datasets"]:
            self.assertIn("workbook_type", ds)
            self.assertIsInstance(ds["workbook_type"], str)
            self.assertTrue(len(ds["workbook_type"]) > 0)

    def test_simulated_missing_column_migration_step(self):
        """
        Create a temporary simulation table completely missing workbook_type,
        insert pre-existing legacy rows, execute the exact migration statements,
        and confirm column is safely added, existing data is preserved, and defaults to RAW.
        """
        table_name = "system.datasets_migration_sim"
        try:
            self.db.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE;"))
            self.db.execute(text(f"""
                CREATE TABLE {table_name} (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    dataset_name VARCHAR(255) NOT NULL,
                    row_count BIGINT DEFAULT 100
                );
            """))
            # Insert pre-existing row before workbook_type column exists
            sim_id = str(uuid4())
            self.db.execute(text(f"""
                INSERT INTO {table_name} (id, dataset_name, row_count)
                VALUES ('{sim_id}', 'Legacy Pre-existing DS', 555);
            """))
            self.db.commit()

            # Execute the exact additive column DDL from schema_init
            self.db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS workbook_type VARCHAR(50) DEFAULT 'RAW';"))
            self.db.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN workbook_type SET DEFAULT 'RAW';"))
            self.db.execute(text(f"""
                UPDATE {table_name}
                SET workbook_type = 'RAW'
                WHERE workbook_type IS NULL OR workbook_type = 'raw_data' OR workbook_type = 'raw';
            """))
            self.db.commit()

            # Verify the column exists and the legacy row retained its data and defaulted to RAW
            row = self.db.execute(text(f"SELECT id, dataset_name, row_count, workbook_type FROM {table_name} WHERE id = '{sim_id}';")).mappings().first()
            self.assertIsNotNone(row)
            self.assertEqual(row["dataset_name"], "Legacy Pre-existing DS")
            self.assertEqual(row["row_count"], 555)
            self.assertEqual(row["workbook_type"], "RAW")
        finally:
            self.db.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE;"))
            self.db.commit()


if __name__ == "__main__":
    unittest.main()
