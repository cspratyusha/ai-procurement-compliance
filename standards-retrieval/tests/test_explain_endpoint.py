"""Tests for POST /explain, the explanation call made after results render.

Explanations used to be generated inside /retrieve, so asking for them held the
whole search until the language model finished. They now come from a separate
call. What matters is that the split did not loosen the boundary: the model
may only describe standards the caller named that the corpus actually holds,
and the endpoint degrades to nothing rather than an error.

The model is mocked; the lifespan is not entered, so no retrieval models load.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from data_loader import load_corpus  # noqa: E402


class TestExplainEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        corpus = load_corpus()
        cls.first, cls.second = corpus[0].number, corpus[1].number

    def setUp(self):
        # Force a fresh number index against whichever corpus is loaded.
        if hasattr(main.app.state, "by_number"):
            del main.app.state.by_number

    def test_returns_explanations_for_named_standards(self):
        with patch.object(main.explanation_engine, "is_available", return_value=True), \
             patch.object(main.explanation_engine, "explain",
                          return_value={self.first: "Covers exactly this product."}) as explain:
            resp = self.client.post("/explain", json={"query": "copper cable", "numbers": [self.first]})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"available": True, "explanations": {self.first: "Covers exactly this product."}})
        sent = explain.call_args.args[1]
        self.assertEqual([c["number"] for c in sent], [self.first])
        self.assertTrue(sent[0]["title"])  # the model sees the real title, not just a number

    def test_numbers_not_in_the_corpus_never_reach_the_model(self):
        """A caller cannot smuggle an invented standard into the prompt."""
        with patch.object(main.explanation_engine, "is_available", return_value=True), \
             patch.object(main.explanation_engine, "explain", return_value={}) as explain:
            self.client.post("/explain", json={"query": "q", "numbers": ["IS 99999:2099", self.first]})

        sent = [c["number"] for c in explain.call_args.args[1]]
        self.assertEqual(sent, [self.first])

    def test_only_the_top_five_are_explained(self):
        corpus = load_corpus()
        numbers = [s.number for s in corpus[:8]]
        with patch.object(main.explanation_engine, "is_available", return_value=True), \
             patch.object(main.explanation_engine, "explain", return_value={}) as explain:
            self.client.post("/explain", json={"query": "q", "numbers": numbers})
        self.assertEqual(len(explain.call_args.args[1]), 5)

    def test_unavailable_model_returns_nothing_without_calling_it(self):
        with patch.object(main.explanation_engine, "is_available", return_value=False), \
             patch.object(main.explanation_engine, "explain") as explain:
            resp = self.client.post("/explain", json={"query": "q", "numbers": [self.first]})
        self.assertEqual(resp.json(), {"available": False, "explanations": {}})
        explain.assert_not_called()

    def test_empty_query_is_rejected(self):
        resp = self.client.post("/explain", json={"query": "  ", "numbers": [self.first]})
        self.assertEqual(resp.status_code, 400)

    def test_health_reports_availability(self):
        with patch.object(main.explanation_engine, "is_available", return_value=True):
            self.assertTrue(self.client.get("/health").json()["explanations_available"])
        with patch.object(main.explanation_engine, "is_available", return_value=False):
            self.assertFalse(self.client.get("/health").json()["explanations_available"])


if __name__ == "__main__":
    unittest.main()
