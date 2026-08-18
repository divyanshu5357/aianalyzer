import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.database.connection import SessionLocal
from app.database.repository import get_active_dataset, set_active_dataset
from sqlalchemy import text

client = TestClient(app)


class TestDashboardAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        res = cls.db.execute(text("SELECT id FROM system.datasets WHERE is_active = TRUE LIMIT 1")).scalar()
        if not res:
            res = cls.db.execute(text("SELECT id FROM system.datasets LIMIT 1")).scalar()
        cls.active_dataset_id = str(res) if res else "test_dataset"
        set_active_dataset(cls.db, cls.active_dataset_id)
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_get_overview(self):
        """Test GET /api/dashboard/overview returns expected KPIs and funnel."""
        response = client.get("/api/dashboard/overview")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("current_year", data)
        self.assertIn("previous_year", data)
        self.assertIn("has_cucet", data)
        self.assertIn("kpis", data)
        self.assertIn("funnel", data)

        kpis = data["kpis"]
        self.assertIn("leads", kpis)
        self.assertIn("admissions", kpis)
        self.assertIn("conversion_rate", kpis)
        self.assertTrue(len(data["funnel"]) >= 2)

    def test_get_filter_options(self):
        """Test GET /api/dashboard/options returns dynamic filter dropdown values."""
        response = client.get("/api/dashboard/options")
        self.assertEqual(response.status_code, 200)
        opts = response.json()
        self.assertIn("academic_sessions", opts)
        self.assertIn("campuses", opts)
        self.assertIn("states", opts)
        self.assertIn("sources", opts)
        self.assertIn("programs", opts)

    def test_filtered_overview(self):
        """Test GET /api/dashboard/overview with campus and state filters."""
        # Get options first
        opts_res = client.get("/api/dashboard/options")
        opts = opts_res.json()
        campus = opts["campuses"][0] if opts["campuses"] else "Mohali"

        response = client.get(f"/api/dashboard/overview?campus={campus}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("kpis", data)

    def test_get_insights(self):
        """Test GET /api/dashboard/insights returns grounded dynamic cards."""
        response = client.get("/api/dashboard/insights")
        self.assertEqual(response.status_code, 200)
        insights = response.json()
        self.assertTrue(isinstance(insights, list))
        for ins in insights:
            self.assertIn("id", ins)
            self.assertIn("title", ins)
            self.assertIn("text", ins)
            self.assertIn("dimension", ins)
            self.assertIn("value", ins)

    def test_get_top_performers(self):
        """Test GET /api/dashboard/top-performers aggregates properly."""
        for metric in ["leads", "admission", "conversion_rate"]:
            response = client.get(f"/api/dashboard/top-performers?metric={metric}&limit=3")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(isinstance(data, dict))
            for dim, items in data.items():
                self.assertTrue(len(items) <= 3)
                for item in items:
                    self.assertIn("entity", item)
                    self.assertIn("value", item)

    def test_get_entity_detail(self):
        """Test GET /api/dashboard/entity/{dimension}/{value}."""
        overview_response = client.get("/api/dashboard/top-performers?metric=admission&limit=1")
        overview_data = overview_response.json()
        
        dimension = "program_name"
        value = "Unknown"
        if "program_name" in overview_data and len(overview_data["program_name"]) > 0:
            dimension = "program_name"
            value = overview_data["program_name"][0]["entity"]

        response = client.get(f"/api/dashboard/entity/{dimension}/{value}")
        if value == "Unknown":
            self.assertEqual(response.status_code, 404)
        else:
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["dimension"], dimension)
            self.assertEqual(data["value"], value)
            self.assertIn("overview", data)
            self.assertIn("breakdowns", data)

            overview = data["overview"]
            self.assertIn("leads", overview)
            self.assertIn("admissions", overview)
            self.assertIn("conversion_rate", overview)
