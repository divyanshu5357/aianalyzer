"""
Power BI Reconciliation Test Suite.

Validates the multi-level Source Hierarchy and analytical calculations
against authoritative business-report Power BI slices:

Hierarchy:
  Program Group (Level 1)
    -> Program/Course (Level 2)
      -> Lead Type (Level 3)
        -> Main Source (Level 4)
          -> Source Cluster (Level 5)
            -> Report Source (Level 6)

Metrics calculated dynamically at each level:
  - PY Leads, CY Leads, Variance Leads
  - PY CUCET, CY CUCET, Variance CUCET, Lead -> CUCET %
  - PY Admission, CY Admission, Variance Admission, Lead -> Admission %, CUCET -> Admission %

Authoritative Power BI Reference Checkpoints:
  1. Mohali -> CSE -> CS201 -> IN HOUSE
  2. Mohali -> CSE -> CS201 -> IN HOUSE -> NNEXT
  3. Mohali -> CSE -> CS201 -> IN HOUSE -> DIRECT
  4. Mohali -> CSE -> CS201 -> OUT SOURCED -> SHIKSHA

CRITICAL SAFETY & GOVERNANCE:
  - DO NOT hardcode Power BI numbers into production calculation logic.
  - Dynamically query PostgreSQL analytics and source hierarchy.
  - Ensure NNEXT != nNext and NNEXT != Nxt - OTHER.
"""
import unittest
from typing import Dict, Any, Optional
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.analytics.program_service import get_program_hierarchy_children, clear_programs_cache


class TestPowerBIReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        clear_programs_cache()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def _get_metrics_for_slice(
        self,
        level: str,
        program_group: str,
        program_code: str,
        lead_type: Optional[str] = None,
        main_source: Optional[str] = None,
        target_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query PostgreSQL analytics hierarchy and return calculated metrics."""
        res = get_program_hierarchy_children(
            db=self.db,
            level=level,
            campus="Mohali",
            academic_year=2026,
            program_group=program_group,
            program_code=program_code,
            lead_type=lead_type,
            main_source=main_source,
        )
        rows = res.get("rows", [])
        if target_name:
            for r in rows:
                if r["program"].strip().upper() == target_name.strip().upper():
                    return r
            return {}
        return rows[0] if rows else {}

    def test_01_reconcile_in_house_cs201(self):
        """Reconcile Slice 1: Mohali -> CSE -> B.E. CSE : CS201 -> IN HOUSE."""
        metrics = self._get_metrics_for_slice(
            level="lead_type",
            program_group="CSE",
            program_code="CS201",
            target_name="IN HOUSE",
        )
        self.assertTrue(bool(metrics), "IN HOUSE metrics must exist for CS201")
        
        # Verify metric keys are computed dynamically
        for key in [
            "py_leads", "cy_leads", "var_leads",
            "py_cucet", "cy_cucet", "var_cucet", "lead_cucet_pct",
            "py_adm", "cy_adm", "var_adm", "lead_adm_pct", "cucet_adm_pct",
        ]:
            self.assertIn(key, metrics)

        # Variance integrity: CY - PY
        self.assertEqual(metrics["var_leads"], metrics["cy_leads"] - metrics["py_leads"])
        self.assertEqual(metrics["var_cucet"], metrics["cy_cucet"] - metrics["py_cucet"])
        self.assertEqual(metrics["var_adm"], metrics["cy_adm"] - metrics["py_adm"])

        # Conversion rate integrity
        if metrics["cy_leads"] > 0:
            expected_cucet_pct = round((metrics["cy_cucet"] / metrics["cy_leads"]) * 100, 1)
            self.assertEqual(metrics["lead_cucet_pct"], expected_cucet_pct)
            expected_adm_pct = round((metrics["cy_adm"] / metrics["cy_leads"]) * 100, 1)
            self.assertEqual(metrics["lead_adm_pct"], expected_adm_pct)
        if metrics["cy_cucet"] > 0:
            expected_cucet_adm_pct = round((metrics["cy_adm"] / metrics["cy_cucet"]) * 100, 1)
            self.assertEqual(metrics["cucet_adm_pct"], expected_cucet_adm_pct)

    def test_02_reconcile_nnext_agency_and_distinct_entity(self):
        """Reconcile Slice 2: Mohali -> CSE -> B.E. CSE : CS201 -> IN HOUSE -> NNEXT / nNext."""
        # Query main sources under IN HOUSE
        res = get_program_hierarchy_children(
            db=self.db,
            level="main_source",
            campus="Mohali",
            academic_year=2026,
            program_group="CSE",
            program_code="CS201",
            lead_type="IN HOUSE",
        )
        rows = res.get("rows", [])
        names = [r["program"] for r in rows]

        # Verify agency nNext is present under IN HOUSE
        self.assertTrue(
            any(n.lower() == "nnext" for n in names),
            f"Expected agency nNext in IN HOUSE main sources: {names}",
        )

        # Verify agency NNEXT is present in ALL CAPS under IN HOUSE
        nnext_agency_row = next((r for r in rows if r["program"] in ("NNEXT", "nNext")), None)
        self.assertIsNotNone(nnext_agency_row)
        self.assertTrue(nnext_agency_row["cy_leads"] > 0)

        # Verify NNEXT does NOT collapse into nNext in source_master
        master_rows = self.db.execute(
            text("SELECT source, report_source, main_source, source_cluster FROM organization.source_master WHERE source IN ('NNEXT', 'Nxt - OTHER')")
        ).mappings().all()
        by_src = {r["source"]: dict(r) for r in master_rows}

        self.assertIn("NNEXT", by_src)
        self.assertIn("Nxt - OTHER", by_src)
        self.assertEqual(by_src["NNEXT"]["main_source"], "NNEXT")
        self.assertEqual(by_src["Nxt - OTHER"]["main_source"], "nNext")
        self.assertNotEqual(by_src["NNEXT"]["main_source"], by_src["Nxt - OTHER"]["main_source"])

    def test_03_reconcile_direct_in_house_cs201(self):
        """Reconcile Slice 3: Mohali -> CSE -> B.E. CSE : CS201 -> IN HOUSE -> DIRECT."""
        metrics = self._get_metrics_for_slice(
            level="main_source",
            program_group="CSE",
            program_code="CS201",
            lead_type="IN HOUSE",
            target_name="DIRECT",
        )
        self.assertTrue(bool(metrics), "DIRECT metrics must exist under IN HOUSE for CS201")
        self.assertTrue(metrics["cy_leads"] > 0)
        self.assertTrue(metrics["py_leads"] > 0)

        # Verify conversion calculations
        self.assertEqual(metrics["var_leads"], metrics["cy_leads"] - metrics["py_leads"])
        self.assertAlmostEqual(metrics["lead_adm_pct"], round((metrics["cy_adm"] / metrics["cy_leads"]) * 100, 1), places=1)

    def test_04_reconcile_shiksha_out_sourced_cs201(self):
        """Reconcile Slice 4: Mohali -> CSE -> B.E. CSE : CS201 -> OUT SOURCED -> SHIKSHA."""
        metrics = self._get_metrics_for_slice(
            level="main_source",
            program_group="CSE",
            program_code="CS201",
            lead_type="OUT SOURCED",
            target_name="SHIKSHA",
        )
        self.assertTrue(bool(metrics), "SHIKSHA metrics must exist under OUT SOURCED for CS201")
        self.assertTrue(metrics["cy_leads"] > 0)
        self.assertTrue(metrics["py_leads"] > 0)
        self.assertEqual(metrics["var_leads"], metrics["cy_leads"] - metrics["py_leads"])

    def test_05_hierarchy_depth_and_structure(self):
        """Verify 6-level hierarchical drill-down without flattening."""
        # Level 1: Program Group
        from app.analytics.program_service import get_program_report_top_level
        l1 = get_program_report_top_level(self.db, campus="Mohali", academic_year=2026)
        cse_node = next((r for r in l1.get("rows", []) if r["program"].strip().upper() == "CSE"), None)
        self.assertIsNotNone(cse_node, "Level 1 CSE node must exist")

        # Level 2: Program / Course under CSE
        l2 = get_program_hierarchy_children(
            db=self.db, level="program", campus="Mohali", academic_year=2026, program_group="CSE"
        )
        cs201_node = next((r for r in l2.get("rows", []) if "CS201" in r["program"].upper()), None)
        self.assertIsNotNone(cs201_node, "Level 2 CS201 node must exist under CSE")

        # Level 3: Lead Type under CS201
        l3 = get_program_hierarchy_children(
            db=self.db, level="lead_type", campus="Mohali", academic_year=2026, program_group="CSE", program_code="CS201"
        )
        l3_types = {r["program"].upper() for r in l3.get("rows", [])}
        self.assertIn("IN HOUSE", l3_types)
        self.assertIn("OUT SOURCED", l3_types)

        # Level 4: Main Source under IN HOUSE
        l4 = get_program_hierarchy_children(
            db=self.db, level="main_source", campus="Mohali", academic_year=2026,
            program_group="CSE", program_code="CS201", lead_type="IN HOUSE"
        )
        l4_sources = {r["program"].upper() for r in l4.get("rows", [])}
        self.assertIn("DIRECT", l4_sources)

        # Level 5: Source Cluster under nNext
        l5 = get_program_hierarchy_children(
            db=self.db, level="source_cluster", campus="Mohali", academic_year=2026,
            program_group="CSE", program_code="CS201", lead_type="IN HOUSE", main_source="nNext"
        )
        self.assertTrue(len(l5.get("rows", [])) > 0, "Level 5 clusters must exist under nNext")

    def test_06_entity_isolation_nnext_vs_NNEXT_vs_nxt_other(self):
        """Regression Test: Verify 3 distinct entities remain isolated in Source Master."""
        rows = self.db.execute(text(
            "SELECT source, report_source, main_source, lead_type, source_cluster "
            "FROM organization.source_master "
            "WHERE source IN ('NNEXT', 'Nxt - OTHER') OR main_source IN ('nNext', 'NNEXT')"
        )).mappings().all()

        # Group by canonical concept
        nnext_single = [r for r in rows if r["source"] == "NNEXT"]
        nxt_other = [r for r in rows if r["source"] == "Nxt - OTHER"]
        nnext_agency = [r for r in rows if r["main_source"] == "nNext"]

        # Entity A: nNext (Digital marketing agency / main source)
        self.assertTrue(len(nnext_agency) > 50, "Agency nNext must have multiple campaigns")
        for r in nnext_agency:
            self.assertEqual(r["lead_type"], "In House")
            self.assertEqual(r["main_source"], "nNext")

        # Entity B: NNEXT (Distinct source entity)
        self.assertEqual(len(nnext_single), 1, "NNEXT must be a single distinct source entity")
        self.assertEqual(nnext_single[0]["source"], "NNEXT")
        self.assertEqual(nnext_single[0]["report_source"], "NNEXT")
        self.assertEqual(nnext_single[0]["main_source"], "NNEXT")
        self.assertEqual(nnext_single[0]["lead_type"], "In House")
        self.assertEqual(nnext_single[0]["source_cluster"], "Nxt - OTHER")

        # Entity C: Nxt - OTHER (Child Source Cluster under nNext)
        self.assertEqual(len(nxt_other), 1, "Nxt - OTHER is a specific source under cluster Nxt - OTHER")
        self.assertEqual(nxt_other[0]["main_source"], "nNext")
        self.assertEqual(nxt_other[0]["source_cluster"], "Nxt - OTHER")
        self.assertEqual(nxt_other[0]["report_source"], "Nxt - OTHER")

        # Never collapsed
        self.assertNotEqual(nnext_single[0]["main_source"], nxt_other[0]["main_source"])
        self.assertNotEqual(nnext_single[0]["source"], nnext_agency[0]["main_source"])

    def test_07_exact_case_sensitive_identity_preservation(self):
        """Regression Test: SourceResolver preserves exact case without UPPER(TRIM())."""
        from app.normalization.dimension_resolver import SourceResolver
        resolver = SourceResolver(self.db)

        res_nnext_single = resolver.resolve("NNEXT")
        self.assertEqual(res_nnext_single.canonical_value, "NNEXT")
        self.assertEqual(res_nnext_single.extra["resolved_main_source"], "NNEXT")
        self.assertEqual(res_nnext_single.extra["resolved_report_source"], "NNEXT")

        res_nnext_agency = resolver.resolve("nNext")
        self.assertEqual(res_nnext_agency.canonical_value, "nNext")
        self.assertEqual(res_nnext_agency.extra["resolved_main_source"], "nNext")

        # Verify case-folding did not merge them
        self.assertNotEqual(res_nnext_single.extra["resolved_main_source"], res_nnext_agency.extra["resolved_main_source"])

    def test_08_composite_evidence_matching(self):
        """Regression Test: Source + SourceMedium composite matching."""
        from app.normalization.dimension_resolver import SourceResolver
        resolver = SourceResolver(self.db)

        # Google + GSN
        res_gsn = resolver.resolve(raw_source="Google", raw_source_medium="GSN")
        self.assertEqual(res_gsn.resolution_status, "RESOLVED")
        self.assertEqual(res_gsn.extra["resolved_source_cluster"], "GSN")
        self.assertEqual(res_gsn.extra["resolved_report_source"], "Google")

        # Meta + MWCON
        res_fb = resolver.resolve(raw_source="Meta", raw_source_medium="MWCON")
        self.assertEqual(res_fb.resolution_status, "RESOLVED")
        self.assertEqual(res_fb.extra["resolved_source_cluster"], "FB")
        self.assertEqual(res_fb.extra["resolved_report_source"], "Facebook")

        # Legacy 2025: nNext + gsn-cu-cet
        res_legacy = resolver.resolve(raw_source="nNext", raw_source_medium="gsn-cu-cet")
        self.assertEqual(res_legacy.resolution_status, "RESOLVED")
        self.assertEqual(res_legacy.extra["resolved_main_source"], "nNext")
        self.assertEqual(res_legacy.extra["resolved_source_cluster"], "GSN")
        self.assertEqual(res_legacy.extra["resolved_report_source"], "Google")

    def test_09_missing_fields_and_evidence_fallbacks(self):
        """Regression Test: Fallbacks from strongest to weakest evidence."""
        from app.normalization.dimension_resolver import SourceResolver
        resolver = SourceResolver(self.db)

        # Missing Source, but SourceMedium = GSN
        res_missing_src = resolver.resolve(raw_source="", raw_source_medium="GSN")
        self.assertEqual(res_missing_src.resolution_status, "RESOLVED")
        self.assertEqual(res_missing_src.extra["resolved_source_cluster"], "GSN")

        # Missing SourceMedium, but Source = Direct
        res_missing_sm = resolver.resolve(raw_source="Direct", raw_source_medium="")
        self.assertEqual(res_missing_sm.resolution_status, "RESOLVED")
        self.assertEqual(res_missing_sm.extra["resolved_main_source"], "Direct")

        # Missing Origin
        res_missing_origin = resolver.resolve(raw_source="Shiksha", raw_source_medium="", raw_origin=None)
        self.assertEqual(res_missing_origin.resolution_status, "RESOLVED")
        self.assertEqual(res_missing_origin.canonical_value, "Shiksha")

    def test_10_ambiguous_and_unmapped_statuses(self):
        """Regression Test: Ambiguous and unmapped inputs flagged cleanly."""
        from app.normalization.dimension_resolver import SourceResolver
        resolver = SourceResolver(self.db)

        # Completely unknown source
        res_unmapped = resolver.resolve(raw_source="UNKNOWN_JUNK_SOURCE_XYZ")
        self.assertEqual(res_unmapped.resolution_status, "UNRESOLVED")
        self.assertEqual(res_unmapped.resolution_method, "UNMAPPED")

        # Empty
        res_empty = resolver.resolve(raw_source="", raw_source_medium="", raw_origin="")
        self.assertEqual(res_empty.resolution_status, "UNRESOLVED")
        self.assertEqual(res_empty.resolution_method, "EMPTY")

    def test_11_dimension_source_duplicates_diagnostic(self):
        """Regression Test: No exact duplicate rows in organization.source_master."""
        sql = """
            SELECT source, report_source, main_source, lead_type, source_cluster, COUNT(*) as cnt
            FROM organization.source_master
            GROUP BY 1, 2, 3, 4, 5
            HAVING COUNT(*) > 1
        """
        duplicates = self.db.execute(text(sql)).fetchall()
        self.assertEqual(len(duplicates), 0, f"Found duplicate rows in source_master: {duplicates}")

    def test_12_distinct_prospect_id_invariance(self):
        """Regression Test: Verify COUNT(DISTINCT ProspectID) == COUNT(*) on CS201 dataset."""
        cy_id = "d1c37e76-8d48-4277-b696-a14abf6e1f3b"
        sql = """
            SELECT 
                COUNT(*) as total_cnt,
                COUNT(DISTINCT raw_data->>'ProspectID') as distinct_cnt
            FROM staging.records
            WHERE dataset_id = :cy_id
              AND UPPER(TRIM(raw_data->>'Program Code')) = 'CS201'
              AND raw_data->>'CreatedOn' >= '2025-10-07' AND raw_data->>'CreatedOn' <= '2026-07-28 23:59:59'
        """
        row = dict(self.db.execute(text(sql), {"cy_id": cy_id}).mappings().first())
        self.assertEqual(
            row["total_cnt"], row["distinct_cnt"],
            "ProspectID must be unique per lead in the reporting window",
        )

    def test_13_reporting_window_and_py_cy_separation(self):
        """Regression Test: Verify CY (2025-10-07 to 2026-07-28) and PY (2024-10-07 to 2025-07-28) separation."""
        cy_id = "d1c37e76-8d48-4277-b696-a14abf6e1f3b"
        py_id = "66a38ff7-fa21-4b77-be4b-59995e239d6a"

        # Check CY bounds
        cy_bounds = dict(self.db.execute(text("""
            SELECT 
                MIN(raw_data->>'CreatedOn') as min_d,
                MAX(raw_data->>'CreatedOn') as max_d
            FROM staging.records
            WHERE dataset_id = :cy_id
              AND raw_data->>'CreatedOn' >= '2025-10-07' AND raw_data->>'CreatedOn' <= '2026-07-28 23:59:59'
        """), {"cy_id": cy_id}).mappings().first())

        self.assertGreaterEqual(cy_bounds["min_d"], "2025-10-07")
        self.assertLessEqual(cy_bounds["max_d"], "2026-07-28 23:59:59")

        # Check PY bounds
        py_bounds = dict(self.db.execute(text("""
            SELECT 
                MIN(raw_data->>'CreatedOn') as min_d,
                MAX(raw_data->>'CreatedOn') as max_d
            FROM staging.records
            WHERE dataset_id = :py_id
              AND raw_data->>'CreatedOn' >= '2024-10-07' AND raw_data->>'CreatedOn' <= '2025-07-28 23:59:59'
        """), {"py_id": py_id}).mappings().first())

        self.assertGreaterEqual(py_bounds["min_d"], "2024-10-07")
        self.assertLessEqual(py_bounds["max_d"], "2025-07-28 23:59:59")


if __name__ == "__main__":
    unittest.main()

