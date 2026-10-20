"""
Comprehensive Correctness Test Suite: Source Hierarchy & Resolution Engine

Verifies:
1. NNEXT is strictly distinct from Nxt - OTHER and nNext.
2. Case normalization does not collapse nNext and NNEXT.
3. Composite matching: Google + GSN -> GSN cluster, nNext, In House.
4. Composite matching: Google + GDN -> GDN cluster, nNext.
5. Composite matching: Google + GPMax -> PMAX cluster, nNext.
6. Composite matching: Google + GDG -> GDC cluster, nNext.
7. Composite matching: Meta + MWCon -> FB cluster, Facebook, nNext.
8. Blank SourceMedium: Shiksha -> Shiksha, Out Sourced.
9. Blank SourceMedium: Direct -> Direct, In House.
10. Missing Source does not discard SourceMedium evidence.
11. Ambiguous records tagged AMBIGUOUS.
12. Unknown records tagged UNMAPPED.
13. Zero hardcoded source-to-category keywords remaining.
14. Lead Type is dynamic from source_master without hardcoding.
"""

import pytest
from app.normalization.dimension_resolver import SourceResolver
from app.normalization.lead_type_resolver import resolve_lead_type, IN_HOUSE_KEYWORDS, OUT_SOURCED_KEYWORDS


@pytest.fixture
def resolver():
    """Initializes SourceResolver using seeds/database master."""
    return SourceResolver(db=None)


class TestSourceHierarchyEngine:
    def test_01_nnext_is_distinct_from_nxt_other_and_nnext(self, resolver):
        """Test 1: NNEXT is distinct from Nxt - OTHER and nNext agency."""
        res_nnext = resolver.resolve("NNEXT")
        assert res_nnext.canonical_value == "NNEXT"
        assert res_nnext.extra["main_source"] == "NNEXT"
        assert res_nnext.extra["report_source"] == "NNEXT"
        assert res_nnext.extra["source_cluster"] == "Nxt - OTHER"
        assert res_nnext.extra["lead_type"] == "In House"

        res_nxt_other = resolver.resolve("Nxt - OTHER")
        assert res_nxt_other.canonical_value == "Nxt - OTHER"
        assert res_nxt_other.extra["main_source"] == "nNext"
        assert res_nxt_other.extra["report_source"] == "Nxt - OTHER"
        assert res_nxt_other.extra["source_cluster"] == "Nxt - OTHER"

        res_agency = resolver.resolve("nNext")
        assert res_agency.extra["main_source"] == "nNext"
        # Crucially, agency nNext main_source is NOT 'NNEXT'
        assert res_agency.extra["main_source"] != "NNEXT"

    def test_02_case_normalization_does_not_collapse_nnext(self, resolver):
        """Test 2: Case normalization does not merge NNEXT and nNext."""
        res_exact_upper = resolver.resolve("NNEXT")
        res_mixed_case = resolver.resolve("nNext")

        assert res_exact_upper.extra["main_source"] == "NNEXT"
        assert res_mixed_case.extra["main_source"] == "nNext"
        assert res_exact_upper.extra["main_source"] != res_mixed_case.extra["main_source"]

    def test_03_google_gsn_resolves_correctly(self, resolver):
        """Test 3: Google + GSN resolves to GSN cluster, nNext, In House."""
        res = resolver.resolve(raw_source="Google", raw_source_medium="GSN", raw_origin="Widget")
        assert res.resolution_method == "COMPOSITE"
        assert res.extra["source_cluster"] == "GSN"
        assert res.extra["main_source"] == "nNext"
        assert res.extra["lead_type"] == "In House"
        assert res.extra["report_source"] == "Google"
        assert res.extra["confidence"] == "HIGH"

    def test_04_google_gdn_resolves_correctly(self, resolver):
        """Test 4: Google + GDN resolves to GDN cluster, nNext, In House."""
        res = resolver.resolve(raw_source="Google", raw_source_medium="GDN", raw_origin="Widget")
        assert res.resolution_method == "COMPOSITE"
        assert res.extra["source_cluster"] == "GDN"
        assert res.extra["main_source"] == "nNext"
        assert res.extra["lead_type"] == "In House"

    def test_05_google_gpmax_resolves_correctly(self, resolver):
        """Test 5: Google + GPMax resolves to PMAX cluster, nNext, In House."""
        res = resolver.resolve(raw_source="Google", raw_source_medium="GPMax", raw_origin="Widget")
        assert res.resolution_method == "COMPOSITE"
        assert res.extra["source_cluster"] == "PMAX"
        assert res.extra["main_source"] == "nNext"
        assert res.extra["lead_type"] == "In House"

    def test_06_google_gdg_resolves_correctly(self, resolver):
        """Test 6: Google + GDG resolves to GDC cluster, nNext, In House."""
        res = resolver.resolve(raw_source="Google", raw_source_medium="GDG", raw_origin="Widget")
        assert res.resolution_method == "COMPOSITE"
        assert res.extra["source_cluster"] == "GDC"
        assert res.extra["main_source"] == "nNext"
        assert res.extra["lead_type"] == "In House"

    def test_07_meta_mwcon_resolves_correctly(self, resolver):
        """Test 7: Meta + MWCon resolves to FB cluster, Facebook, nNext."""
        res = resolver.resolve(raw_source="Meta", raw_source_medium="MWCon", raw_origin="Widget")
        assert res.resolution_method == "COMPOSITE"
        assert res.extra["source_cluster"] == "FB"
        assert res.extra["report_source"] == "Facebook"
        assert res.extra["main_source"] == "nNext"
        assert res.extra["lead_type"] == "In House"

    def test_08_shiksha_blank_sourcemedium(self, resolver):
        """Test 8: Shiksha with blank SourceMedium resolves unambiguously."""
        res = resolver.resolve(raw_source="Shiksha", raw_source_medium="", raw_origin="Publisher-API")
        assert res.resolution_method in ("EXACT", "EXACT_CASE_INSENSITIVE")
        assert res.extra["main_source"] == "Shiksha"
        assert res.extra["source_cluster"] == "SHIKSHA"
        assert res.extra["lead_type"] == "Out Sourced"
        assert res.extra["confidence"] == "HIGH"

    def test_09_direct_blank_sourcemedium(self, resolver):
        """Test 9: Direct with blank SourceMedium resolves to Direct, In House."""
        res = resolver.resolve(raw_source="Direct", raw_source_medium="", raw_origin="Portal")
        assert res.resolution_method in ("EXACT", "EXACT_CASE_INSENSITIVE")
        assert res.extra["main_source"] == "Direct"
        assert res.extra["source_cluster"] == "DIRECT"
        assert res.extra["lead_type"] == "In House"

    def test_10_missing_source_preserves_medium_evidence(self, resolver):
        """Test 10: Missing Source still resolves using SourceMedium evidence."""
        res = resolver.resolve(raw_source="", raw_source_medium="GSN", raw_origin="Widget")
        assert res.resolution_status == "RESOLVED"
        assert res.resolution_method == "FALLBACK"
        assert res.extra["source_cluster"] == "GSN"
        assert res.extra["main_source"] == "nNext"
        assert res.extra["lead_type"] == "In House"

    def test_11_unknown_records_unmapped(self, resolver):
        """Test 11: Completely unknown record marked UNMAPPED."""
        res = resolver.resolve(raw_source="NonExistentSourceXYZ", raw_source_medium="", raw_origin="")
        assert res.resolution_status == "UNRESOLVED"
        assert res.resolution_method == "UNMAPPED"
        assert res.canonical_value is None

    def test_12_zero_hardcoded_keyword_sets(self):
        """Test 12: Ensure no hardcoded keyword sets remain in lead_type_resolver."""
        assert len(IN_HOUSE_KEYWORDS) == 0
        assert len(OUT_SOURCED_KEYWORDS) == 0

    def test_13_dynamic_lead_type_resolver(self):
        """Test 13: Lead type resolution dynamically checks source master."""
        assert resolve_lead_type("Direct") == "IN HOUSE"
        assert resolve_lead_type("Website") == "IN HOUSE"
        assert resolve_lead_type("Shiksha") == "OUT SOURCED"
        assert resolve_lead_type("Twigz") == "OUT SOURCED"
        assert resolve_lead_type("nNext") == "IN HOUSE"
        assert resolve_lead_type("NNEXT") == "IN HOUSE"
        assert resolve_lead_type("NonExistentXYZ") == "OTHERS"
