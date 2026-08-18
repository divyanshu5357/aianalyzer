import unittest
import uuid
from sqlalchemy import text
from app.database.connection import SessionLocal
from app.analytics.uploaded_analytics import calculate_source_hierarchy_uploaded

class TestSourcePerformanceHierarchy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.mock_dataset_id = str(uuid.uuid4())
        
        # Insert mock records covering all 13 test scenarios
        cls.db.execute(
            text(
                """
                INSERT INTO analytics.uploaded_metrics (
                    id, dataset_id, row_number, lead_type, source, main_source, 
                    cy_leads, cy_cucet, cy_admission, py_leads, py_cucet, py_admission
                ) VALUES 
                -- 1. Scenario: Increased leads/admissions (IN HOUSE, D: NNEXT, GSN)
                (:id1, :ds_id, 1, 'IN HOUSE', 'D: NNEXT', 'GSN', 10, 8, 4, 5, 4, 2),
                -- 2. Scenario: Decreased leads/admissions (OUT SOURCED, SHIKSHA, Shiksha - ED)
                (:id2, :ds_id, 2, 'OUT SOURCED', 'SHIKSHA', 'Shiksha - ED', 5, 4, 1, 10, 8, 3),
                -- 3. Scenario: Zero previous-year leads (OTHERS, DIRECT, YouTube)
                (:id3, :ds_id, 3, 'OTHERS', 'DIRECT', 'YouTube', 8, 6, 2, 0, 0, 0),
                -- 4. Scenario: Zero previous-year admissions (OTHERS, FB, FB Ads)
                (:id4, :ds_id, 4, 'OTHERS', 'FB', 'FB Ads', 10, 5, 3, 5, 2, 0),
                -- 5. Scenario: NULL/empty hierarchy values (will map to OTHERS/OTHER/UNKNOWN)
                (:id5, :ds_id, 5, NULL, '  ', '', 2, 1, 1, 1, 1, 0)
                """
            ),
            {
                "ds_id": cls.mock_dataset_id,
                "id1": str(uuid.uuid4()),
                "id2": str(uuid.uuid4()),
                "id3": str(uuid.uuid4()),
                "id4": str(uuid.uuid4()),
                "id5": str(uuid.uuid4()),
            }
        )
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.execute(
            text("DELETE FROM analytics.uploaded_metrics WHERE dataset_id = :ds_id"),
            {"ds_id": cls.mock_dataset_id}
        )
        cls.db.commit()
        cls.db.close()

    def test_hierarchy_tree_structure_and_active_dataset_isolation(self):
        # 11. Active dataset isolation check
        res_empty = calculate_source_hierarchy_uploaded(self.db, str(uuid.uuid4()), 2026)
        self.assertEqual(len(res_empty), 0)

        # Retrieve tree
        tree = calculate_source_hierarchy_uploaded(self.db, self.mock_dataset_id, 2026)
        
        # 1. Level 1 PY/CY aggregation check
        in_house = next((x for x in tree if x["name"] == "IN-HOUSE"), None)
        out_sourced = next((x for x in tree if x["name"] == "OUT-SOURCED"), None)
        others = next((x for x in tree if x["name"] == "OTHERS"), None)
        
        self.assertIsNotNone(in_house)
        self.assertIsNotNone(out_sourced)
        self.assertIsNotNone(others)

        # 4. Increased leads check
        self.assertEqual(in_house["leads"], 10)
        self.assertEqual(in_house["py_leads"], 5)
        
        # 5. Decreased leads check
        self.assertEqual(out_sourced["leads"], 5)
        self.assertEqual(out_sourced["py_leads"], 10)

        # 6. Increased admissions check
        self.assertEqual(in_house["admission"], 4)
        self.assertEqual(in_house["py_admission"], 2)

        # 7. Decreased admissions check
        self.assertEqual(out_sourced["admission"], 1)
        self.assertEqual(out_sourced["py_admission"], 3)

        # 2. Level 2 PY/CY aggregation check
        l2_node = in_house["children"][0]
        self.assertEqual(l2_node["name"], "NNEXT")
        self.assertEqual(l2_node["leads"], 10)
        self.assertEqual(l2_node["py_leads"], 5)

        # 3. Level 3 PY/CY aggregation check
        l3_node = l2_node["children"][0]
        self.assertEqual(l3_node["name"], "GSN")
        self.assertEqual(l3_node["leads"], 10)
        self.assertEqual(l3_node["py_leads"], 5)

    def test_zero_previous_year_handling(self):
        # 8 & 9. Zero previous-year leads/admissions check
        tree = calculate_source_hierarchy_uploaded(self.db, self.mock_dataset_id, 2026)
        others = next((x for x in tree if x["name"] == "OTHERS"), None)
        
        # In others we have direct (YouTube) and FB (FB Ads) and the NULL node
        # YouTube had cy_leads = 8, py_leads = 0. Growth should be safe (handled in UI or resolved as 0 in calculation)
        direct_l2 = next((x for x in others["children"] if x["name"] == "DIRECT"), None)
        self.assertIsNotNone(direct_l2)
        youtube_l3 = next((x for x in direct_l2["children"] if x["name"] == "YouTube"), None)
        self.assertIsNotNone(youtube_l3)
        self.assertEqual(youtube_l3["py_leads"], 0)
        self.assertEqual(youtube_l3["py_admission"], 0)

    def test_null_hierarchy_values_mapping(self):
        # 13. NULL hierarchy values handling
        tree = calculate_source_hierarchy_uploaded(self.db, self.mock_dataset_id, 2026)
        others = next((x for x in tree if x["name"] == "OTHERS"), None)
        
        # The NULL record should group under OTHERS -> OTHER -> UNKNOWN
        other_l2 = next((x for x in others["children"] if x["name"] == "OTHER"), None)
        self.assertIsNotNone(other_l2)
        unknown_l3 = next((x for x in other_l2["children"] if x["name"] == "UNKNOWN"), None)
        self.assertIsNotNone(unknown_l3)
        
        # Values from the NULL record: cy_leads = 2, py_leads = 1, cy_admission = 1, py_admission = 0
        self.assertEqual(unknown_l3["leads"], 2)
        self.assertEqual(unknown_l3["py_leads"], 1)

    def test_dynamic_selected_year(self):
        # 12. Dynamic selected year checks
        # Active dataset Native CY = 2026 (cy_*), Native PY = 2025 (py_*)
        
        # When year = 2026 (Native CY)
        tree_2026 = calculate_source_hierarchy_uploaded(self.db, self.mock_dataset_id, 2026)
        in_house_2026 = next((x for x in tree_2026 if x["name"] == "IN-HOUSE"), None)
        self.assertEqual(in_house_2026["leads"], 10)
        self.assertEqual(in_house_2026["py_leads"], 5)

        # When year = 2025 (Native PY)
        # CY should map to py_leads (5), PY should map to 0
        tree_2025 = calculate_source_hierarchy_uploaded(self.db, self.mock_dataset_id, 2025)
        in_house_2025 = next((x for x in tree_2025 if x["name"] == "IN-HOUSE"), None)
        self.assertEqual(in_house_2025["leads"], 5)
        self.assertEqual(in_house_2025["py_leads"], 0)

        # When year = 2027 (Native CY + 1)
        # CY should map to 0, PY should map to cy_leads (10)
        tree_2027 = calculate_source_hierarchy_uploaded(self.db, self.mock_dataset_id, 2027)
        in_house_2027 = next((x for x in tree_2027 if x["name"] == "IN-HOUSE"), None)
        self.assertEqual(in_house_2027["leads"], 0)
        self.assertEqual(in_house_2027["py_leads"], 10)
