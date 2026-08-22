import csv
import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.ingestion.job_tracker import get_job_status, mark_job_completed

client = TestClient(app)

class TestAsyncUploadFlow(unittest.TestCase):

    def setUp(self):
        self.test_csv = "/tmp/test_async_upload.csv"
        headers = ["Owner", "Cluster", "Lead Type", "Source Cluster", "MSSourcebi", "Campus Name", "State Group", "Program Name (Short)", "CY Leads", "CY CUCET", "CY Admission", "PY Leads", "PY CUCET", "PY Admission"]
        with open(self.test_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for i in range(1, 11):
                w.writerow(["Alice", "North", "Direct", "Digital Cluster", "Google", "Mohali", "Punjab", "B.Tech CSE", 10, 5, 2, 8, 4, 1])

    def tearDown(self):
        if os.path.exists(self.test_csv):
            os.remove(self.test_csv)

    @patch("app.api.upload._process_single_file")
    @patch("app.api.upload._detect_and_check")
    def test_sync_upload_backward_compatibility(self, mock_detect, mock_process):
        mock_process.return_value = {
            "dataset_id": "test-dataset-id",
            "filename": "2023-24_leads.csv",
            "upload_status": "new",
            "file_type": "csv",
        }
        mock_detect.return_value = {
            "status": "success",
            "period": "2023-24",
            "academic_year": "2023-24",
        }
        with open(self.test_csv, "rb") as f:
            response = client.post("/api/data/upload", files=[("files", ("2023-24_leads.csv", f, "text/csv"))])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("files", data)

    @patch("app.api.upload.set_active_dataset")
    @patch("app.api.upload._process_single_file")
    @patch("app.api.upload._detect_and_check")
    def test_async_background_upload_and_status_polling(self, mock_detect, mock_process, mock_set_active):
        job_id = "test_job_async_123"
        mock_process.return_value = {
            "dataset_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
            "filename": "2024-25_leads.csv",
            "upload_status": "confirmed",
        }
        mock_detect.return_value = {
            "status": "success",
            "period": "2024-25",
        }

        with open(self.test_csv, "rb") as f:
            response = client.post(f"/api/data/upload?job_id={job_id}", files=[("files", ("2024-25_leads.csv", f, "text/csv"))])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "processing")
        self.assertEqual(data["job_id"], job_id)

        # Verify job tracker status lookup
        status = get_job_status(job_id)
        self.assertIsNotNone(status)
        self.assertEqual(status["job_id"], job_id)
        self.assertIn(status["status"], ["processing", "completed"])
