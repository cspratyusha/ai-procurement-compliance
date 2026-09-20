"""Tests for the LLM explanation layer.

The model is not under test. What is under test is the boundary around it:
that a fabricated standard number can never reach the user, that a dead or
slow model degrades to no explanations rather than to an error, and that
explanations never touch ranking.

An LLM inventing an IS number in a procurement tool is the worst output this
system could produce, so the validation that prevents it has the most tests.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import explanation  # noqa: E402

CANDIDATES = [
    {"number": "IS 694:2010", "title": "PVC Insulated Cables", "scope": "Single-core cables."},
    {"number": "IS 8112:2018", "title": "OPC 43 Grade", "scope": "Ordinary Portland cement."},
]


def _model_returns(payload: dict):
    """Patch the HTTP call so the model 'returns' a given JSON body."""
    return patch.object(
        explanation, "_post", return_value={"response": json.dumps(payload)}
    )


class TestExplanationValidation(unittest.TestCase):
    def setUp(self):
        explanation._availability = True  # skip the reachability probe

    def tearDown(self):
        explanation._availability = None

    def test_valid_explanations_are_returned(self):
        with _model_returns({
            "explanations": [
                {"number": "IS 694:2010", "reason": "Covers single-core PVC cable for fixed wiring."},
                {"number": "IS 8112:2018", "reason": "Covers cement, not cable."},
            ]
        }):
            result = explanation.explain("copper cable", CANDIDATES)

        self.assertEqual(set(result), {"IS 694:2010", "IS 8112:2018"})
        self.assertIn("single-core", result["IS 694:2010"].lower())

    def test_invented_standard_numbers_are_discarded(self):
        """The load-bearing guard.

        A model that helpfully adds "IS 9999:2020" must not have that reach a
        tender document. Unrecognised numbers are dropped, and the legitimate
        explanations around them still survive.
        """
        with _model_returns({
            "explanations": [
                {"number": "IS 694:2010", "reason": "Genuine candidate."},
                {"number": "IS 9999:2020", "reason": "Entirely invented standard."},
                {"number": "IS 1786:2008", "reason": "Real standard, but not a candidate here."},
            ]
        }):
            result = explanation.explain("copper cable", CANDIDATES)

        self.assertEqual(set(result), {"IS 694:2010"})
        self.assertNotIn("IS 9999:2020", result)
        self.assertNotIn("IS 1786:2008", result)

    def test_unparseable_output_yields_no_explanations(self):
        with patch.object(explanation, "_post", return_value={"response": "I cannot help with that."}):
            self.assertEqual(explanation.explain("copper cable", CANDIDATES), {})

    def test_json_wrapped_in_prose_is_salvaged(self):
        """Small models sometimes add a preamble despite JSON mode."""
        wrapped = 'Here you go:\n{"explanations":[{"number":"IS 694:2010","reason":"Fits."}]}\nHope that helps.'
        with patch.object(explanation, "_post", return_value={"response": wrapped}):
            result = explanation.explain("copper cable", CANDIDATES)
        self.assertEqual(result, {"IS 694:2010": "Fits."})

    def test_model_failure_degrades_to_empty(self):
        """A dead model must not break a search that already succeeded."""
        for failure in (OSError("connection refused"), TimeoutError("timed out")):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(explanation, "_post", side_effect=failure):
                    self.assertEqual(explanation.explain("copper cable", CANDIDATES), {})

    def test_malformed_entries_are_skipped_individually(self):
        with _model_returns({
            "explanations": [
                {"number": "IS 694:2010", "reason": "Good."},
                {"number": "IS 8112:2018"},          # missing reason
                {"reason": "orphaned reason"},        # missing number
                "not even an object",
            ]
        }):
            result = explanation.explain("copper cable", CANDIDATES)
        self.assertEqual(set(result), {"IS 694:2010"})

    def test_overlong_reason_is_trimmed(self):
        with _model_returns({
            "explanations": [{"number": "IS 694:2010", "reason": "word " * 200}]
        }):
            result = explanation.explain("copper cable", CANDIDATES)
        self.assertLessEqual(len(result["IS 694:2010"]), 301)

    def test_no_candidates_means_no_call(self):
        with patch.object(explanation, "_post") as post:
            self.assertEqual(explanation.explain("anything", []), {})
            post.assert_not_called()

    def test_unavailable_model_means_no_call(self):
        explanation._availability = False
        with patch.object(explanation, "_post") as post:
            self.assertEqual(explanation.explain("copper cable", CANDIDATES), {})
            post.assert_not_called()

    def test_only_the_top_candidates_are_sent(self):
        """Cost control: a long result list must not become a long prompt."""
        many = [
            {"number": f"IS {900 + i}:2020", "title": f"Standard {i}", "scope": ""}
            for i in range(12)
        ]
        captured = {}

        def capture(path, payload, timeout):
            captured["prompt"] = payload["prompt"]
            return {"response": json.dumps({"explanations": []})}

        with patch.object(explanation, "_post", side_effect=capture):
            explanation.explain("query", many)

        self.assertIn("IS 900:2020", captured["prompt"])
        self.assertNotIn("IS 911:2020", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
