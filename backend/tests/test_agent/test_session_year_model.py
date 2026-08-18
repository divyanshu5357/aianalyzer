import unittest
from unittest.mock import MagicMock
from app.ingestion.period_detector import parse_label
from app.analytics.period_resolver import (
    parse_year_input,
    list_all_analytical_years,
    resolve_year_column,
    compare_periods,
)

class TestSessionYearModel(unittest.TestCase):
    def test_session_parsing(self):
        self.assertEqual(parse_label("2025-26"), (2025, 2026))
        self.assertEqual(parse_label("2023-24"), (2023, 2024))
        self.assertEqual(parse_year_input("2025-26"), 2026)
        self.assertEqual(parse_year_input("2025"), 2025)
        self.assertEqual(parse_year_input(2025), 2025)

    def test_same_year_validation(self):
        db_mock = MagicMock()
        with self.assertRaises(ValueError) as ctx:
            compare_periods(db_mock, "admissions", "2026", "2026", "program_name")
        self.assertIn("Please select two different years for comparison", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx2:
            compare_periods(db_mock, "admissions", 2025, 2025, "program_name")
        self.assertIn("Please select two different years for comparison", str(ctx2.exception))

    def test_resolve_year_column_mapping(self):
        db_mock = MagicMock()
        # Mock database rows for datasets: 2025-26 (start: 2025, end: 2026)
        dataset_row = {
            "id": "ds-123",
            "period_start_year": 2025,
            "period_end_year": 2026,
            "academic_label": "2025-26",
            "is_period_active": True,
            "is_active": True,
        }
        db_mock.execute.return_value.mappings.return_value.all.return_value = [dataset_row]

        # Year 2026 should map to CY column (cy_admission)
        ds_id, col_cy, year, role = resolve_year_column(db_mock, 2026, "admissions")
        self.assertEqual(ds_id, "ds-123")
        self.assertEqual(col_cy, "cy_admission")
        self.assertEqual(year, 2026)
        self.assertEqual(role, "cy")

        # Year 2025 should map to PY column (py_admission)
        ds_id2, col_py, year2, role2 = resolve_year_column(db_mock, 2025, "admissions")
        self.assertEqual(ds_id2, "ds-123")
        self.assertEqual(col_py, "py_admission")
        self.assertEqual(year2, 2025)
        self.assertEqual(role2, "py")

if __name__ == "__main__":
    unittest.main()
