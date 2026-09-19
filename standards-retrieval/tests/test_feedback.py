"""Unit and integration tests for the feedback-capture layer (Part 6).

Validates:
1. Append-only JSONL durability: sequential calls to append_log() produce clean, uncorrupted lines.
2. Pydantic validation: action="correct" strictly requires corrected_id; action="accept" requires chosen_id.
3. API endpoint integration: POST /feedback saves entries with source="live" and ISO timestamp.
4. GET /logs returns the most recent entries first in correct descending order.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from pydantic import ValidationError
from unittest.mock import patch
from fastapi.testclient import TestClient

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from main import app
from feedback.schema import InteractionLog, FeedbackRequest
from feedback.logger import append_log, read_logs


class TestFeedbackCapture(unittest.TestCase):

    def setUp(self):
        """Creates a temporary JSONL file for isolated file logger testing."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_log_path = Path(self.temp_dir.name) / "test_interaction_logs.jsonl"

    def tearDown(self):
        """Cleans up temporary directory."""
        self.temp_dir.cleanup()

    # --- 1. Schema Validation Tests ---

    def test_action_correct_requires_corrected_id(self):
        """Assert a log with action='correct' strictly requires non-empty corrected_id."""
        sample_candidates = [
            {"id": "IS-ELEC-001", "final_score": 0.85, "rank": 1},
            {"id": "IS-ELEC-002", "final_score": 0.65, "rank": 2}
        ]

        # 1. Missing corrected_id must raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            InteractionLog(
                query="substation power cables",
                candidates_shown=sample_candidates,
                chosen_id=None,
                action="correct",
                corrected_id=None,
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="live"
            )
        self.assertIn("corrected_id is required", str(ctx.exception))

        # 2. Empty string corrected_id must also raise ValidationError
        with self.assertRaises(ValidationError) as ctx2:
            InteractionLog(
                query="substation power cables",
                candidates_shown=sample_candidates,
                chosen_id=None,
                action="correct",
                corrected_id="   ",
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="live"
            )
        self.assertIn("corrected_id is required", str(ctx2.exception))

        # 3. Valid corrected_id passes validation
        valid_log = InteractionLog(
            query="substation power cables",
            candidates_shown=sample_candidates,
            chosen_id=None,
            action="correct",
            corrected_id="IS-ELEC-003",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="live"
        )
        self.assertEqual(valid_log.corrected_id, "IS-ELEC-003")

    def test_action_accept_requires_chosen_id(self):
        """Assert a log with action='accept' strictly requires non-empty chosen_id."""
        sample_candidates = [{"id": "IS-ELEC-001", "final_score": 0.90, "rank": 1}]

        # Missing chosen_id on accept must fail
        with self.assertRaises(ValidationError):
            InteractionLog(
                query="building wire",
                candidates_shown=sample_candidates,
                chosen_id=None,
                action="accept",
                timestamp=datetime.now(timezone.utc).isoformat(),
                source="live"
            )

        # Valid chosen_id succeeds
        valid_log = InteractionLog(
            query="building wire",
            candidates_shown=sample_candidates,
            chosen_id="IS-ELEC-001",
            action="accept",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="live"
        )
        self.assertEqual(valid_log.chosen_id, "IS-ELEC-001")

    def test_action_reject_allows_none_chosen_id(self):
        """Assert action='reject' allows chosen_id=None."""
        log = InteractionLog(
            query="non-existent standard request",
            candidates_shown=[{"id": "IS-ELEC-001", "final_score": 0.12, "rank": 1}],
            chosen_id=None,
            action="reject",
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="live"
        )
        self.assertIsNone(log.chosen_id)
        self.assertEqual(log.action, "reject")

    # --- 2. Append-Only JSONL File Durability Tests ---

    def test_append_log_durability_multiple_writes(self):
        """Assert append_log() appends without corrupting existing lines across multiple writes."""
        entries = [
            InteractionLog(
                query=f"test query {i}",
                candidates_shown=[{"id": f"IS-TEST-{i}", "final_score": 0.5 + i * 0.1, "rank": 1}],
                chosen_id=f"IS-TEST-{i}" if i % 2 == 0 else None,
                action="accept" if i % 2 == 0 else "reject",
                timestamp=f"2026-09-19T20:0{i}:00Z",
                source="synthetic"
            )
            for i in range(3)
        ]

        # Write 3 entries sequentially
        for entry in entries:
            append_log(entry, path=self.test_log_path)

        # Read back raw file lines
        self.assertTrue(self.test_log_path.exists())
        with open(self.test_log_path, "r", encoding="utf-8") as f:
            raw_lines = [line.strip() for line in f if line.strip()]

        # Confirm exactly 3 valid JSON lines
        self.assertEqual(len(raw_lines), 3)

        for i, line in enumerate(raw_lines):
            parsed = json.loads(line)
            self.assertEqual(parsed["query"], f"test query {i}")
            self.assertEqual(parsed["source"], "synthetic")

        # Test read_logs returns them most recent first
        recent_logs = read_logs(path=self.test_log_path, limit=10)
        self.assertEqual(len(recent_logs), 3)
        self.assertEqual(recent_logs[0]["query"], "test query 2")  # Most recent
        self.assertEqual(recent_logs[1]["query"], "test query 1")
        self.assertEqual(recent_logs[2]["query"], "test query 0")  # Oldest

    # --- 3. FastAPI Client Endpoint Integration Tests ---

    def test_api_feedback_and_logs_flow(self):
        """POST feedback entries via TestClient, then GET /logs and assert correct storage and order."""
        client = TestClient(app)

        with patch("main.append_log", side_effect=lambda log: append_log(log, path=self.test_log_path)), \
             patch("main.read_logs", side_effect=lambda limit=50: read_logs(path=self.test_log_path, limit=limit)):
            # 1. Post Accept interaction
            payload_accept = {
                "query": "heavy duty power cable 1100V",
                "candidates_shown": [
                    {"id": "IS-ELEC-006", "final_score": 0.95, "rank": 1},
                    {"id": "IS-ELEC-003", "final_score": 0.72, "rank": 2}
                ],
                "chosen_id": "IS-ELEC-006",
                "action": "accept"
            }
            resp1 = client.post("/feedback", json=payload_accept)
            self.assertEqual(resp1.status_code, 200)
            self.assertEqual(resp1.json(), {"status": "logged"})

            # 2. Post Correct (manual override) interaction
            payload_correct = {
                "query": "fire resistant safety cable",
                "candidates_shown": [
                    {"id": "IS-ELEC-001", "final_score": 0.40, "rank": 1}
                ],
                "chosen_id": None,
                "action": "correct",
                "corrected_id": "IS-ELEC-008"
            }
            resp2 = client.post("/feedback", json=payload_correct)
            self.assertEqual(resp2.status_code, 200)
            self.assertEqual(resp2.json(), {"status": "logged"})

            # 3. Post Reject interaction
            payload_reject = {
                "query": "unsupported procurement query",
                "candidates_shown": [
                    {"id": "IS-CEM-001", "final_score": 0.20, "rank": 1}
                ],
                "chosen_id": None,
                "action": "reject"
            }
            resp3 = client.post("/feedback", json=payload_reject)
            self.assertEqual(resp3.status_code, 200)
            self.assertEqual(resp3.json(), {"status": "logged"})

            # 4. Verify invalid Correct without corrected_id returns 422
            payload_invalid = {
                "query": "invalid correction",
                "candidates_shown": [{"id": "IS-CEM-001", "final_score": 0.5, "rank": 1}],
                "action": "correct",
                "corrected_id": None
            }
            resp_err = client.post("/feedback", json=payload_invalid)
            self.assertEqual(resp_err.status_code, 422)

            # 5. GET /logs to verify recent entries
            resp_logs = client.get("/logs?limit=10")
            self.assertEqual(resp_logs.status_code, 200)
            logs = resp_logs.json()
            self.assertIsInstance(logs, list)
            self.assertGreaterEqual(len(logs), 3)

            # Most recent should be the reject action
            self.assertEqual(logs[0]["query"], "unsupported procurement query")
            self.assertEqual(logs[0]["action"], "reject")
            self.assertEqual(logs[0]["source"], "live")
            self.assertIn("timestamp", logs[0])

            # Second most recent should be the correct action
            self.assertEqual(logs[1]["query"], "fire resistant safety cable")
            self.assertEqual(logs[1]["action"], "correct")
            self.assertEqual(logs[1]["corrected_id"], "IS-ELEC-008")
            self.assertEqual(logs[1]["source"], "live")

            # Third most recent should be the accept action
            self.assertEqual(logs[2]["query"], "heavy duty power cable 1100V")
            self.assertEqual(logs[2]["action"], "accept")
            self.assertEqual(logs[2]["chosen_id"], "IS-ELEC-006")
            self.assertEqual(logs[2]["source"], "live")


if __name__ == "__main__":
    unittest.main()
