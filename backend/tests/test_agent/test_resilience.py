import time
import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import text
import httpx
from google.genai import errors

from app.database.connection import SessionLocal
from app.config.settings import settings
from app.agent.agent_service import answer_question
from app.agent.gemini_planner import plan_question, _gemini_cooldown_until
import app.agent.gemini_planner as gp


class TestAgentResilience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        # Retrieve active dataset
        res = cls.db.execute(text("SELECT id FROM system.datasets WHERE is_active = TRUE LIMIT 1")).scalar()
        if not res:
            res = cls.db.execute(text("SELECT id FROM system.datasets LIMIT 1")).scalar()
        cls.active_dataset_id = str(res) if res else "test_dataset"

        # Make sure settings are enabled for the direct planner test cases
        cls.original_enabled = settings.gemini_enabled
        cls.original_key = settings.gemini_api_key
        settings.gemini_enabled = True
        if not settings.gemini_api_key:
            settings.gemini_api_key = "fake_key_for_testing"

    @classmethod
    def tearDownClass(cls):
        settings.gemini_enabled = cls.original_enabled
        settings.gemini_api_key = cls.original_key
        cls.db.close()

    def setUp(self):
        gp._gemini_cooldown_until = 0.0
        self.db.rollback()

    def tearDown(self):
        self.db.rollback()

    @patch("google.genai.Client")
    def test_direct_planner_success(self, mock_client_class):
        """Verify successful structured response from Gemini planning."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"intent": "metric", "operation": "metric", "metric": "leads"}'
        mock_client.models.generate_content.return_value = mock_response
        mock_client_class.return_value = mock_client

        res = gp.plan_question("how many leads?")
        self.assertIsNotNone(res)
        self.assertEqual(res["intent"], "metric")
        mock_client.models.generate_content.assert_called_once()

    @patch("google.genai.Client")
    def test_direct_planner_429_circuit_breaker(self, mock_client_class):
        """Verify 429 RESOURCE_EXHAUSTED triggers circuit breaker cooldown and subsequent requests skip Gemini."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = errors.APIError(429, {"error": {"message": "Resource exhausted"}})
        mock_client_class.return_value = mock_client

        # First request: fails with 429
        res = gp.plan_question("vague question here")
        self.assertIsNone(res)
        self.assertTrue(gp._gemini_cooldown_until > time.time())

        # Reset mock call count to verify it is NOT called on subsequent request
        mock_client.models.generate_content.reset_mock()

        # Second request: should immediately return None without calling Gemini
        res2 = gp.plan_question("another vague question")
        self.assertIsNone(res2)
        mock_client.models.generate_content.assert_not_called()

    @patch("google.genai.Client")
    def test_direct_planner_timeout_retry(self, mock_client_class):
        """Verify timeout exception triggers exactly one retry before falling back."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = httpx.TimeoutException("Connection timed out")
        mock_client_class.return_value = mock_client

        res = gp.plan_question("how many leads?")
        self.assertIsNone(res)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        # Timeout doesn't set long cooldown
        self.assertEqual(gp._gemini_cooldown_until, 0.0)

    @patch("google.genai.Client")
    def test_direct_planner_auth_error_long_cooldown(self, mock_client_class):
        """Verify 403 API key or auth error disables Gemini for a long duration."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = errors.APIError(403, {"error": {"message": "Invalid API Key"}})
        mock_client_class.return_value = mock_client

        res = gp.plan_question("how many leads?")
        self.assertIsNone(res)
        # Cooldown should be configured to 1 day (86400)
        self.assertTrue(gp._gemini_cooldown_until > time.time() + 80000)

    @patch("app.agent.agent_service.plan_question")
    def test_routing_simple_metric_bypasses_gemini(self, mock_plan):
        """Verify simple metric query is confidently parsed locally and bypasses Gemini planner."""
        res = answer_question(self.db, "How many admissions happened in 2026?")
        self.assertEqual(res["response_type"], "text")
        self.assertEqual(res["year"], 2026)
        self.assertIn("admission", res["columns"])
        mock_plan.assert_not_called()

    @patch("app.agent.agent_service.plan_question")
    def test_routing_simple_breakdown_bypasses_gemini(self, mock_plan):
        """Verify simple breakdown query bypasses Gemini."""
        res = answer_question(self.db, "Show leads by state")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("leads", res["columns"])
        self.assertIn("state", res["columns"])
        mock_plan.assert_not_called()

    @patch("app.agent.agent_service.plan_question")
    def test_routing_simple_ranking_bypasses_gemini(self, mock_plan):
        """Verify simple ranking query bypasses Gemini."""
        res = answer_question(self.db, "Which program had the highest admissions?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("admission", res["columns"])
        self.assertIn("program_name", res["columns"])
        mock_plan.assert_not_called()

    @patch("app.agent.agent_service.plan_question")
    def test_routing_simple_comparison_bypasses_gemini(self, mock_plan):
        """Verify simple comparison query bypasses Gemini."""
        res = answer_question(self.db, "Compare Mohali vs Unnao admissions")
        self.assertEqual(res["response_type"], "table")
        mock_plan.assert_not_called()

    @patch("app.agent.agent_service.plan_question")
    def test_routing_simple_top5_bypasses_gemini(self, mock_plan):
        """Verify simple top N query bypasses Gemini."""
        res = answer_question(self.db, "Show top 5 programs")
        self.assertEqual(res["response_type"], "table")
        self.assertTrue(len(res["data"]) <= 5)
        mock_plan.assert_not_called()

    @patch("app.agent.agent_service.plan_question")
    def test_routing_simple_yoy_bypasses_gemini(self, mock_plan):
        """Verify simple YoY improvement query bypasses Gemini."""
        res = answer_question(self.db, "Which programs improved from last year?")
        self.assertEqual(res["response_type"], "table")
        self.assertIn("rate_change", res["columns"])
        mock_plan.assert_not_called()

    @patch("app.agent.agent_service.plan_question")
    def test_unsupported_question_handling(self, mock_plan):
        """Verify unsupported domain queries are rejected locally without database execution."""
        res = answer_question(self.db, "Who is the CEO of Google?")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("don't have enough data", res["answer"])
        mock_plan.assert_not_called()

    @patch("app.agent.agent_service.plan_question")
    def test_ambiguous_question_fallback(self, mock_plan):
        """Verify vague queries trigger the clarification fallback."""
        res = answer_question(self.db, "Show the best one")
        self.assertEqual(res["response_type"], "text")
        self.assertIn("context", res["answer"].lower())
        mock_plan.assert_not_called()

    @patch("app.agent.agent_service.plan_question")
    def test_contextual_question_driver_analysis(self, mock_plan):
        """Verify contextual 'why did it improve' resolves to driver analysis."""
        conv_id = "resilience_context_conv"
        # First question gets context
        answer_question(self.db, "Show top 5 programs", conversation_id=conv_id)

        # Second question asking why
        res = answer_question(self.db, "Why did it improve?", conversation_id=conv_id)
        self.assertEqual(res["response_type"], "table")
        self.assertIn("associations", res["answer"].lower())
        mock_plan.assert_not_called()

    @patch("app.agent.agent_service.plan_question")
    def test_recommendations_work_when_gemini_unavailable(self, mock_plan):
        """Verify recommendation generation operates successfully when Gemini is unavailable."""
        res = answer_question(self.db, "Show leads by state")
        self.assertTrue(len(res.get("recommendations", [])) >= 1)
        mock_plan.assert_not_called()
