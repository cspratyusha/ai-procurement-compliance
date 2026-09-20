"""API contract and integration tests for the standards-retrieval FastAPI service.

Validates:
1. GET /health contract (status="ok", correct corpus_size, ltr_model_loaded boolean).
2. Input validation (empty query -> 400, top_k < 1 -> 400, top_k > 50 capping).
3. Retrieval accuracy on real evaluation queries from data/eval_set.json (asserting correct_id is retrieved).
4. Strict response shape validation against the documented schema contract (Part 4 integration guarantee).
5. Graceful degradation: if LTR model raises an error, service degrades to fallback_score() with 200 OK.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from main import app
from data_loader import load_eval_set, load_corpus


class TestStandardsRetrievalAPI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Initializes FastAPI TestClient with lifespan context manager."""
        # Using TestClient as a context manager triggers the lifespan startup event
        cls.client_cm = TestClient(app)
        cls.client = cls.client_cm.__enter__()
        cls.corpus = load_corpus()
        cls.eval_queries = load_eval_set()

    @classmethod
    def tearDownClass(cls):
        cls.client_cm.__exit__(None, None, None)

    # --- 1. Health & Root Endpoint Tests ---

    def test_root_redirects_to_docs(self):
        """Assert GET / redirects to /docs."""
        response = self.client.get("/", follow_redirects=False)
        self.assertIn(response.status_code, [302, 307])
        self.assertEqual(response.headers.get("location"), "/docs")

    def test_health_check_contract(self):
        """Assert /health returns 200, status='ok', correct corpus_size, and ltr_model_loaded."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("corpus_size"), len(self.corpus))
        self.assertIn("ltr_model_loaded", data)
        self.assertIsInstance(data["ltr_model_loaded"], bool)

        # Ensure exact contract keys
        expected_keys = {"status", "corpus_size", "ltr_model_loaded"}
        self.assertEqual(set(data.keys()), expected_keys)

    # --- 2. Input Validation Tests ---

    def test_empty_query_returns_400(self):
        """Assert empty or whitespace query strings return HTTP 400."""
        # Empty string
        resp1 = self.client.post("/retrieve", json={"query": "", "top_k": 10})
        self.assertEqual(resp1.status_code, 400)
        self.assertIn("Query string must not be empty", resp1.json()["detail"])

        # Whitespace-only string
        resp2 = self.client.post("/retrieve", json={"query": "   \n\t  ", "top_k": 10})
        self.assertEqual(resp2.status_code, 400)

        # GET endpoint alias empty query
        resp3 = self.client.get("/retrieve?query=")
        self.assertEqual(resp3.status_code, 400)

    def test_invalid_top_k_returns_400(self):
        """Assert non-positive top_k returns HTTP 400."""
        resp = self.client.post("/retrieve", json={"query": "cables", "top_k": 0})
        self.assertEqual(resp.status_code, 400)

        resp_neg = self.client.post("/retrieve", json={"query": "cables", "top_k": -5})
        self.assertEqual(resp_neg.status_code, 400)

    def test_top_k_capped_at_sane_max(self):
        """Assert top_k is capped at 50 to prevent abuse."""
        resp = self.client.post("/retrieve", json={"query": "cables", "top_k": 100})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Must return at most 50 items (or corpus size)
        self.assertLessEqual(len(data["results"]), 50)

    # --- 3. Retrieval Accuracy on Eval Set Queries ---

    def test_retrieval_eval_set_queries(self):
        """Assert correct_id appears in returned results for representative eval_set queries."""
        # Select 4 diverse queries from eval_set (cables, cement, steel, use_case)
        sample_queries = [
            self.eval_queries[0],  # Single core copper building wire -> IS-ELEC-001
            self.eval_queries[7],  # Ordinary Portland cement 43 grade -> IS-CEM-001
            self.eval_queries[10], # Seamless carbon steel boiler tubes -> IS-STEEL-004
            self.eval_queries[20], # Use-case: underground road power line -> IS-ELEC-003
        ]

        for item in sample_queries:
            query = item["query"]
            target_id = item["correct_id"]

            resp = self.client.post("/retrieve", json={"query": query, "top_k": 10})
            self.assertEqual(resp.status_code, 200)

            data = resp.json()
            retrieved_ids = [r["id"] for r in data["results"]]

            self.assertIn(
                target_id,
                retrieved_ids,
                f"Query '{query}' failed to retrieve target standard '{target_id}' in top 10. Found: {retrieved_ids}"
            )

    # --- 4. Strict Response Shape & Contract Validation ---

    def test_response_shape_matches_documented_contract(self):
        """Assert the response JSON matches the exact documented schema contract.
        
        Contract:
        {
          "query": str,
          "results": [
            {
              "id": str,
              "number": str,
              "title": str,
              "final_score": float,
              "stage_scores": {
                "dense": float,
                "bm25": float,
                "cross_encoder": float,
                "ltr_or_fallback": float
              },
              "ranker_used": "ltr" | "fallback"
            }
          ]
        }
        """
        query = "PVC insulated building copper wire 1100V"
        resp = self.client.post("/retrieve", json={"query": query, "top_k": 5})
        self.assertEqual(resp.status_code, 200)

        data = resp.json()

        # Top-level keys must match exactly
        self.assertEqual(set(data.keys()), {"query", "results"})
        self.assertEqual(data["query"], query)
        self.assertIsInstance(data["results"], list)
        self.assertGreater(len(data["results"]), 0)

        # Validate item schema
        expected_result_keys = {"id", "number", "title", "final_score", "stage_scores", "ranker_used"}
        expected_stage_keys = {"dense", "bm25", "cross_encoder", "ltr_or_fallback"}

        for item in data["results"]:
            # Check keys
            self.assertEqual(set(item.keys()), expected_result_keys)

            # Check types & values
            self.assertIsInstance(item["id"], str)
            self.assertIsInstance(item["number"], str)
            self.assertIsInstance(item["title"], str)
            self.assertIsInstance(item["final_score"], (float, int))
            self.assertTrue(0.0 <= item["final_score"] <= 1.0, f"final_score {item['final_score']} not in [0.0, 1.0]")

            self.assertIn(item["ranker_used"], ["ltr", "fallback"])

            # Check stage_scores
            stage_scores = item["stage_scores"]
            self.assertEqual(set(stage_scores.keys()), expected_stage_keys)
            for k in expected_stage_keys:
                self.assertIsInstance(stage_scores[k], (float, int))

    # --- 5. Graceful Degradation & Fallback Handling ---

    def test_graceful_degradation_when_ltr_model_fails(self):
        """Assert if LTR model throws during inference, service degrades to fallback_score without 500 error."""
        # Mock the LTR model on app.state to raise an intentional runtime exception
        original_model = getattr(app.state, "ltr_model", None)
        mock_broken_model = MagicMock()
        mock_broken_model.predict.side_effect = RuntimeError("Simulated corrupt LTR model weights")

        try:
            app.state.ltr_model = mock_broken_model

            resp = self.client.post("/retrieve", json={"query": "fire proof copper cable", "top_k": 3})
            self.assertEqual(resp.status_code, 200, "Service must not 500 when LTR throws")

            data = resp.json()
            self.assertGreater(len(data["results"]), 0)

            # Assert ranker_used degraded to fallback
            for item in data["results"]:
                self.assertEqual(item["ranker_used"], "fallback")
                self.assertTrue(0.0 <= item["final_score"] <= 1.0)
                self.assertIn("ltr_or_fallback", item["stage_scores"])

        finally:
            # Restore original model
            app.state.ltr_model = original_model


if __name__ == "__main__":
    unittest.main()
