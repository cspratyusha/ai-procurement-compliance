"""Unit tests for the training-set builder (Part 6, Stage D).

Validates:
1. compute_historical_acceptance_rate():
   - Hand-constructed test: standard shown 4 times, accepted 2 times returns 0.5.
   - Standard never shown returns 0.0.
   - Standard shown 3 times, accepted 0 times returns 0.0.
2. logs_to_training_data():
   - Small hand-constructed fake logs (one query with 1 accept and 1-2 rejects).
   - Produces correct binary labels (accept/correct -> 1, reject -> 0).
   - Produces correct group_sizes (e.g. [2] or [3]).
   - Feature vectors match FEATURE_NAMES length (7) and canonical order from ltr/features.py.
"""
import sys
import unittest
from pathlib import Path
import numpy as np

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.models import Standard
from data_loader import load_corpus
from feedback.schema import InteractionLog
from feedback.build_training_set import (
    load_logs,
    logs_to_training_data,
    compute_historical_acceptance_rate,
)
from ltr.features import FEATURE_NAMES


class TestTrainingSetBuilder(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Loads corpus for standard object lookup."""
        standards = load_corpus()
        cls.corpus = {s.id: s for s in standards}

    # --- 1. Historical Acceptance Rate Tests ---

    def test_compute_historical_acceptance_rate(self):
        """Assert standard shown 4 times and accepted twice returns exactly 0.5."""
        # Construct 4 interaction logs:
        # In all 4, "IS-ELEC-001" is shown.
        # In 2 of them (log 1 and log 3), "IS-ELEC-001" is accepted.
        fake_logs = [
            InteractionLog(
                query="wire query 1",
                candidates_shown=[
                    {"id": "IS-ELEC-001", "final_score": 0.9, "rank": 1},
                    {"id": "IS-ELEC-002", "final_score": 0.7, "rank": 2}
                ],
                chosen_id="IS-ELEC-001",
                action="accept",
                timestamp="2026-09-19T20:00:00Z",
                source="synthetic"
            ),
            InteractionLog(
                query="wire query 2",
                candidates_shown=[
                    {"id": "IS-ELEC-001", "final_score": 0.8, "rank": 1},
                    {"id": "IS-ELEC-002", "final_score": 0.6, "rank": 2}
                ],
                chosen_id="IS-ELEC-002",
                action="accept",
                timestamp="2026-09-19T20:01:00Z",
                source="synthetic"
            ),
            InteractionLog(
                query="wire query 3",
                candidates_shown=[
                    {"id": "IS-ELEC-001", "final_score": 0.85, "rank": 1},
                    {"id": "IS-ELEC-003", "final_score": 0.5, "rank": 2}
                ],
                chosen_id="IS-ELEC-001",
                action="accept",
                timestamp="2026-09-19T20:02:00Z",
                source="synthetic"
            ),
            InteractionLog(
                query="wire query 4",
                candidates_shown=[
                    {"id": "IS-ELEC-001", "final_score": 0.7, "rank": 1},
                    {"id": "IS-ELEC-004", "final_score": 0.4, "rank": 2}
                ],
                chosen_id=None,
                action="reject",
                timestamp="2026-09-19T20:03:00Z",
                source="synthetic"
            )
        ]

        # "IS-ELEC-001" was shown in all 4 logs, accepted in 2 logs (queries 1 and 3)
        rate_elec_001 = compute_historical_acceptance_rate("IS-ELEC-001", fake_logs)
        self.assertEqual(rate_elec_001, 0.5, f"Expected 0.5, got {rate_elec_001}")

        # "IS-ELEC-002" was shown in 2 logs (1 and 2), accepted in 1 log (query 2) -> 1/2 = 0.5
        rate_elec_002 = compute_historical_acceptance_rate("IS-ELEC-002", fake_logs)
        self.assertEqual(rate_elec_002, 0.5)

        # "IS-ELEC-003" was shown in 1 log (query 3), accepted in 0 -> 0/1 = 0.0
        rate_elec_003 = compute_historical_acceptance_rate("IS-ELEC-003", fake_logs)
        self.assertEqual(rate_elec_003, 0.0)

        # Standard never shown anywhere returns 0.0
        rate_never_shown = compute_historical_acceptance_rate("IS-NON-EXISTENT", fake_logs)
        self.assertEqual(rate_never_shown, 0.0)

    # --- 2. Training Data Conversion Tests ---

    def test_logs_to_training_data_labels_and_groups(self):
        """Assert logs_to_training_data() produces correct labels, group_sizes, and feature shapes."""
        query = "Concealed 1.5 sq mm copper wiring for building"
        
        # 3 fake log records for the SAME query:
        # 1 Accept entry for IS-ELEC-001
        # 2 Separate Reject entries for IS-ELEC-002 and IS-ELEC-004
        fake_logs = [
            InteractionLog(
                query=query,
                candidates_shown=[
                    {"id": "IS-ELEC-001", "final_score": 0.95, "rank": 1},
                    {"id": "IS-ELEC-002", "final_score": 0.70, "rank": 2},
                    {"id": "IS-ELEC-004", "final_score": 0.50, "rank": 3}
                ],
                chosen_id="IS-ELEC-001",
                action="accept",
                timestamp="2026-09-19T20:10:00Z",
                source="synthetic"
            ),
            InteractionLog(
                query=query,
                candidates_shown=[
                    {"id": "IS-ELEC-002", "final_score": 0.70, "rank": 2}
                ],
                chosen_id=None,
                action="reject",
                timestamp="2026-09-19T20:10:00Z",
                source="synthetic"
            ),
            InteractionLog(
                query=query,
                candidates_shown=[
                    {"id": "IS-ELEC-004", "final_score": 0.50, "rank": 3}
                ],
                chosen_id=None,
                action="reject",
                timestamp="2026-09-19T20:10:00Z",
                source="synthetic"
            )
        ]

        X, y, group_sizes = logs_to_training_data(fake_logs, corpus=self.corpus)

        # 1. Exactly 1 query group
        self.assertEqual(len(group_sizes), 1)
        self.assertEqual(group_sizes[0], 3)

        # 2. Exactly 3 candidate rows
        self.assertEqual(len(y), 3)
        self.assertEqual(X.shape[0], 3)

        # 3. Label mapping: accept -> 1, rejects -> 0
        # Positive example (IS-ELEC-001) is sorted first
        self.assertEqual(y[0], 1)
        self.assertEqual(y[1], 0)
        self.assertEqual(y[2], 0)

        # 4. Feature vector shape & canonical order
        self.assertEqual(X.shape[1], len(FEATURE_NAMES))
        self.assertEqual(X.shape[1], 7)

        # 5. Check historical_acceptance_rate feature column (index 6)
        # In these fake logs:
        # IS-ELEC-001: shown in log 1, accepted in log 1 -> rate = 1.0
        # IS-ELEC-002: shown in log 1 & log 2 (2 times), accepted 0 times -> rate = 0.0
        # IS-ELEC-004: shown in log 1 & log 3 (2 times), accepted 0 times -> rate = 0.0
        hist_col_idx = FEATURE_NAMES.index("historical_acceptance_rate")
        self.assertEqual(hist_col_idx, 6)
        self.assertAlmostEqual(X[0, hist_col_idx], 1.0, places=4)
        self.assertAlmostEqual(X[1, hist_col_idx], 0.0, places=4)
        self.assertAlmostEqual(X[2, hist_col_idx], 0.0, places=4)


if __name__ == "__main__":
    unittest.main()
