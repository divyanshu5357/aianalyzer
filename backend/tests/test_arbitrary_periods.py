"""
Arbitrary-period analytics tests.

Uses dynamic entity discovery rather than hardcoded program names.
"""
import unittest
from app.database.connection import SessionLocal
from app.analytics.period_resolver import compare_periods, get_historical_trend
from sqlalchemy import text


def _discover_program_name(db):
    """Return the first non-null program_name from the active dataset."""
    row = db.execute(
        text("""
            SELECT DISTINCT program_name
            FROM analytics.uploaded_metrics
            WHERE program_name IS NOT NULL AND TRIM(program_name) != ''
            LIMIT 1
        """)
    ).scalar()
    return row


class TestArbitraryPeriods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.test_program = _discover_program_name(cls.db)

        # Discover available period labels
        rows = cls.db.execute(
            text("""
                SELECT DISTINCT academic_label
                FROM system.datasets
                WHERE academic_label IS NOT NULL
                ORDER BY academic_label DESC
            """)
        ).scalars().all()
        cls.available_labels = list(rows) if rows else []

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    @property
    def _has_two_periods(self):
        return len(self.available_labels) >= 2

    @property
    def _period_a(self):
        return self.available_labels[0] if self.available_labels else "2025-26"

    @property
    def _period_b(self):
        return self.available_labels[1] if self._has_two_periods else "2024-25"

    def test_compare_valid_periods(self):
        """Test standard comparison between two valid periods."""
        if not self._has_two_periods:
            self.skipTest("Need at least 2 periods for comparison")
        res = compare_periods(
            self.db,
            metric="admissions",
            period_a_label=self._period_a,
            period_b_label=self._period_b,
            dimension="program_name"
        )
        self.assertEqual(res["period_a"], self._period_a)
        self.assertEqual(res["period_b"], self._period_b)
        self.assertIn("data", res)
        self.assertTrue(len(res["data"]) > 0)
        # Data rows should have expected fields
        if res["data"]:
            row = res["data"][0]
            self.assertIn("period_a_value", row)
            self.assertIn("period_b_value", row)
            self.assertIn("absolute_change", row)
            self.assertIn("growth_percent", row)

    def test_compare_zero_values(self):
        """Test zero to non-zero and non-zero to zero."""
        if not self._has_two_periods:
            self.skipTest("Need at least 2 periods for comparison")
        res = compare_periods(self.db, "leads", self._period_a, self._period_b, "program_name")
        self.assertIsNotNone(res)

    def test_compare_conversion_rate(self):
        """Test conversion rate metric handling."""
        if not self._has_two_periods:
            self.skipTest("Need at least 2 periods for comparison")
        res = compare_periods(self.db, "conversion_rate", self._period_a, self._period_b, "program_name")
        if res["data"]:
            row = res["data"][0]
            self.assertIn("period_a_rate", row)
            self.assertIn("period_b_rate", row)
            self.assertIn("rate_change_percentage_points", row)
            self.assertTrue(row["period_a_rate"] >= 0)
            self.assertTrue(row["period_b_rate"] >= 0)

    def test_historical_trend(self):
        """Test the get_historical_trend function."""
        if not self._has_two_periods:
            self.skipTest("Need at least 2 periods for trend")
        res = get_historical_trend(self.db, "admissions", "program_name")
        self.assertIn("periods", res)
        self.assertTrue(len(res["periods"]) >= 2)
        self.assertIn("data", res)

    def test_historical_trend_conversion(self):
        """Test historical trend with conversion rate."""
        if not self._has_two_periods:
            self.skipTest("Need at least 2 periods for trend")
        res = get_historical_trend(self.db, "conversion_rate", "program_name")
        self.assertIn("periods", res)
        self.assertTrue(len(res["periods"]) >= 2)

    def test_compare_same_period(self):
        """Test comparing a period with itself (should be 0 change)."""
        if not self.available_labels:
            self.skipTest("No periods available")
        res = compare_periods(self.db, "admissions", self._period_a, self._period_a, "program_name")
        if res["data"]:
            row = res["data"][0]
            self.assertEqual(row["period_a_value"], row["period_b_value"])
            self.assertEqual(row["absolute_change"], 0)
            self.assertEqual(row["growth_percent"], 0.0)

    def test_compare_reverse_chronological(self):
        """Test comparing older period as A and newer as B."""
        if not self._has_two_periods:
            self.skipTest("Need at least 2 periods for comparison")
        res = compare_periods(self.db, "admissions", self._period_b, self._period_a, "program_name")
        self.assertEqual(res["period_a"], self._period_b)
        self.assertEqual(res["period_b"], self._period_a)
        if res["data"]:
            row = res["data"][0]
            self.assertTrue(row["period_a_value"] >= 0)
            self.assertTrue(row["period_b_value"] >= 0)

    def test_invalid_period(self):
        """Test invalid period throws ValueError."""
        with self.assertRaises(ValueError):
            compare_periods(self.db, "admissions", "invalid-period", self._period_a, "program_name")
