"""Unit tests for the synthetic interaction log generator (Part 6, Stage D).

Validates:
1. Queries are sourced from data/train_queries.json (keeping data/eval_set.json held out).
2. Accept rate is roughly (1 - noise_rate) within a reasonable statistical tolerance band.
3. Every generated log has source='synthetic' and valid ISO timestamps.
4. Reject entries reference real candidates that were actually present in that query's candidates_shown list (no fabricated IDs).
5. Reject entries have action='reject' and chosen_id=None.
"""
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data_loader import load_eval_set
from feedback.synthetic_logger import generate_synthetic_logs

_TRAIN_QUERIES_PATH = _PROJECT_ROOT / "data" / "train_queries.json"


class TestSyntheticLogger(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Preload train queries ground truth (eval_set is reserved for the promotion gate)."""
        cls.train_data = load_eval_set(str(_TRAIN_QUERIES_PATH))
        cls.correct_map = {item["query"]: item["correct_id"] for item in cls.train_data}

    def test_synthetic_logs_structure_and_source(self):
        """Assert every generated log has source='synthetic' and valid schema fields."""
        logs = generate_synthetic_logs(query_set_path=str(_TRAIN_QUERIES_PATH), noise_rate=0.1, seed=42)
        self.assertGreater(len(logs), 0)

        for log in logs:
            # 1. Source must be 'synthetic'
            self.assertEqual(
                log.source,
                "synthetic",
                f"Expected source='synthetic', got '{log.source}'"
            )
            # 2. Timestamp must be non-empty ISO format
            self.assertTrue(bool(log.timestamp))
            self.assertIn("T", log.timestamp)

            # 3. Action must be accept or reject
            self.assertIn(log.action, ["accept", "reject"])
            if log.action == "reject":
                self.assertIsNone(log.chosen_id)
            elif log.action == "accept":
                self.assertIsNotNone(log.chosen_id)

    def test_noise_rate_within_tolerance(self):
        """Assert the accept rate of correct_id is roughly (1 - noise_rate) within tolerance."""
        noise_rate = 0.15
        logs = generate_synthetic_logs(query_set_path=str(_TRAIN_QUERIES_PATH), noise_rate=noise_rate, seed=123)

        accept_logs = [l for l in logs if l.action == "accept"]
        self.assertEqual(len(accept_logs), len(self.train_data))

        correct_accepts = sum(
            1 for l in accept_logs
            if l.chosen_id == self.correct_map.get(l.query)
        )
        actual_correct_rate = correct_accepts / len(accept_logs)
        expected_rate = 1.0 - noise_rate

        # With 50 queries and noise_rate=0.15, expected ~42.5 correct (~85%).
        # Statistical tolerance band of +/- 0.12 accommodates binomial variance across 50 samples.
        tolerance = 0.12
        self.assertAlmostEqual(
            actual_correct_rate,
            expected_rate,
            delta=tolerance,
            msg=f"Actual rate {actual_correct_rate:.3f} outside tolerance band around {expected_rate:.3f}"
        )

    def test_reject_entries_reference_actual_candidates(self):
        """Assert reject entries reference candidates that were actually shown (no fabricated IDs)."""
        logs = generate_synthetic_logs(query_set_path=str(_TRAIN_QUERIES_PATH), noise_rate=0.1, seed=999)

        # Build map of query -> list of shown candidate IDs from the accept entry
        accept_logs = [l for l in logs if l.action == "accept"]
        query_to_shown = {
            l.query: [c["id"] for c in l.candidates_shown]
            for l in accept_logs
        }

        reject_logs = [l for l in logs if l.action == "reject"]
        self.assertGreater(len(reject_logs), 0)

        for rej in reject_logs:
            query = rej.query
            self.assertIn(query, query_to_shown, f"Reject entry query '{query}' not found in accept logs.")
            shown_ids = query_to_shown[query]

            # Every candidate in the reject log's candidates_shown must be from that query's shown candidates
            for cand in rej.candidates_shown:
                rej_id = cand["id"]
                self.assertIn(
                    rej_id,
                    shown_ids,
                    f"Reject entry referenced fabricated ID '{rej_id}', not in shown candidates {shown_ids}"
                )


if __name__ == "__main__":
    unittest.main()
