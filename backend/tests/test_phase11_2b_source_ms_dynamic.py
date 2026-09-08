"""
Phase 11.2B Correction — Authoritative Source_ms Dimension & Dynamic Data Change Test Suite
Validates that Source_ms (organization.source_master) is 100% authoritative with zero hardcoded source lists.
"""
import unittest
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.agent.agent_service import answer_question
from app.agent.tools.source_category_tool import SourceCategoryTool
from app.agent.tools.base import ToolRequest


class TestPhase11_2BSourceMSDynamic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.ds_id = "89281e52-5794-40ae-ab75-3c39239c821b"

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_source_ms_mapping_coverage_audit(self):
        """Verify mapping coverage audit against organization.source_master (Source_ms)."""
        rows = self.db.execute(text("""
            WITH raw_srcs AS (
                SELECT 
                    COALESCE(NULLIF(TRIM(raw_data->>'MSSourcebi'), ''), NULLIF(TRIM(raw_data->>'Source'), '')) as raw_source,
                    COUNT(*) as row_count
                FROM staging.records
                WHERE dataset_id = :ds
                  AND COALESCE(NULLIF(TRIM(raw_data->>'MSSourcebi'), ''), NULLIF(TRIM(raw_data->>'Source'), '')) IS NOT NULL
                GROUP BY 1
            )
            SELECT 
                r.raw_source,
                r.row_count,
                sm.lead_type,
                CASE WHEN sm.source IS NOT NULL THEN 'MATCHED' ELSE 'UNMAPPED' END as mapping_status
            FROM raw_srcs r
            LEFT JOIN organization.source_master sm ON LOWER(TRIM(r.raw_source)) = LOWER(TRIM(sm.source))
        """), {"ds": self.ds_id}).mappings().all()

        matched = sum(1 for r in rows if r["mapping_status"] == "MATCHED")
        total = len(rows)
        coverage_pct = (matched / total * 100.0) if total > 0 else 0.0

        self.assertGreaterEqual(coverage_pct, 90.0, f"Expected Source_ms coverage >= 90%, got {coverage_pct:.2f}%")

    def test_02_inhouse_vs_outsource_lead_comparison(self):
        """Verify 'Compare inhouse vs outsource leads.' uses Source_ms Lead Type."""
        tool = SourceCategoryTool()
        req = ToolRequest(tool_name="source_category", operation="inhouse_vs_outsource", dataset_id=self.ds_id, raw_question="Compare inhouse vs outsource leads.")
        res = tool.execute(self.db, req)
        self.assertTrue(res.success)
        self.assertGreaterEqual(len(res.data), 2)
        categories = {r["category"]: r["leads"] for r in res.data}
        self.assertIn("In House", categories)
        self.assertIn("Out Sourced", categories)
        self.assertGreater(categories["In House"], 0)
        self.assertGreater(categories["Out Sourced"], 0)

    def test_03_top_owners_inhouse_uses_source_ms(self):
        """Verify top owners for Inhouse uses Source_ms.lead_type = 'In House'."""
        tool = SourceCategoryTool()
        req = ToolRequest(tool_name="source_category", operation="top_owners_inhouse", dataset_id=self.ds_id, raw_question="top owners Inhouse")
        res = tool.execute(self.db, req)
        self.assertTrue(res.success)
        self.assertTrue(len(res.data) > 0)
        self.assertIn("inhouse_leads", res.data[0])

    def test_04_data_change_test_dynamic_reclassification(self):
        """
        Data Change Test:
        Re-classify 'Shiksha' in organization.source_master from 'Out Sourced' to 'In House'.
        Verify that In House leads count dynamically increases without code modification!
        Then revert the change back to 'Out Sourced'.
        """
        tool = SourceCategoryTool()
        req = ToolRequest(tool_name="source_category", operation="inhouse_vs_outsource", dataset_id=self.ds_id, raw_question="Compare inhouse vs outsource leads.")

        # Baseline count
        res_before = tool.execute(self.db, req)
        before_dict = {r["category"]: r["leads"] for r in res_before.data}
        inhouse_before = before_dict.get("In House", 0)

        # Re-classify 'Shiksha' to 'In House'
        self.db.execute(text("UPDATE organization.source_master SET lead_type = 'In House' WHERE LOWER(source) = 'shiksha'"))
        self.db.commit()

        try:
            res_after = tool.execute(self.db, req)
            after_dict = {r["category"]: r["leads"] for r in res_after.data}
            inhouse_after = after_dict.get("In House", 0)

            # Shiksha has ~130 leads, so inhouse count MUST increase dynamically!
            self.assertGreater(inhouse_after, inhouse_before, f"Inhouse count should increase after reclassifying Shiksha. Before: {inhouse_before}, After: {inhouse_after}")

        finally:
            # Revert Shiksha back to 'Out Sourced'
            self.db.execute(text("UPDATE organization.source_master SET lead_type = 'Out Sourced' WHERE LOWER(source) = 'shiksha'"))
            self.db.commit()


if __name__ == "__main__":
    unittest.main()
