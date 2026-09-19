"""Unit and integration tests for scheduled retraining and promotion pipeline (Part 6, Stage D).

Validates:
1. Insufficient-data abort path with a tiny logs file (< 10 distinct queries).
2. Worse-candidate rejection: when candidate scores worse, current model is left untouched (verified via content/hash).
3. First-run auto-promotion: when no current model exists, candidate is automatically promoted.
4. Persistent history audit log: appends structured outcomes to retraining_history.jsonl.
5. Real end-to-end retraining cycle on actual synthetic interaction logs.
"""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from feedback.schema import InteractionLog
from feedback.retrain_and_promote import (
    run_retraining_cycle,
    log_retraining_run,
    should_promote,
    promotion_decision,
)

_INTERACTION_LOGS_PATH = _PROJECT_ROOT / "data" / "interaction_logs.jsonl"
_EVAL_SET_PATH = _PROJECT_ROOT / "data" / "eval_set.json"


class TestRetrainAndPromote(unittest.TestCase):

    def setUp(self):
        """Creates temporary sandbox directory for test model and log artifacts."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sandbox = Path(self.temp_dir.name)
        self.temp_logs_path = self.sandbox / "test_logs.jsonl"
        self.temp_current_path = self.sandbox / "test_ltr_model.txt"
        self.temp_candidate_path = self.sandbox / "test_ltr_candidate.txt"
        self.temp_history_path = self.sandbox / "test_retraining_history.jsonl"

    def tearDown(self):
        """Cleans up temporary sandbox."""
        self.temp_dir.cleanup()

    # --- 1. Insufficient Data Abort Test ---

    def test_insufficient_data_abort(self):
        """Assert retraining aborts early with reason='insufficient_data' if distinct queries < 10."""
        # Create tiny logs with only 2 distinct queries
        tiny_logs = [
            InteractionLog(
                query="substation cable 1",
                candidates_shown=[{"id": "IS-ELEC-001", "final_score": 0.9, "rank": 1}],
                chosen_id="IS-ELEC-001",
                action="accept",
                timestamp="2026-09-19T20:00:00Z",
                source="synthetic"
            ),
            InteractionLog(
                query="substation cable 2",
                candidates_shown=[{"id": "IS-ELEC-002", "final_score": 0.8, "rank": 1}],
                chosen_id="IS-ELEC-002",
                action="accept",
                timestamp="2026-09-19T20:00:00Z",
                source="synthetic"
            )
        ]
        with open(self.temp_logs_path, "w", encoding="utf-8") as f:
            for log in tiny_logs:
                f.write(json.dumps(log.model_dump()) + "\n")

        result = run_retraining_cycle(
            logs_path=str(self.temp_logs_path),
            eval_set_path=str(_EVAL_SET_PATH),
            current_model_path=str(self.temp_current_path),
            candidate_model_path=str(self.temp_candidate_path),
            min_queries=10,
            verbose=False
        )

        self.assertFalse(result["promoted"])
        self.assertEqual(result["reason"], "insufficient_data")
        self.assertEqual(result["distinct_queries"], 2)
        self.assertIn("timestamp", result)
        # Candidate model should not be created
        self.assertFalse(self.temp_candidate_path.exists())

    # --- 2. Worse-Candidate Rejection (Untouched Current Model) ---

    def test_worse_candidate_rejected_current_model_untouched(self):
        """Assert that when the candidate model scores worse, the current model file is left untouched."""
        # Write known content into current model file
        original_model_content = "CANONICAL_LIVE_LTR_MODEL_MOCK_CONTENT_V1"
        original_hash = hashlib.sha256(original_model_content.encode("utf-8")).hexdigest()
        self.temp_current_path.write_text(original_model_content, encoding="utf-8")

        # Mock build_training_set to provide sufficient fake queries (> 10)
        fake_X = np.ones((25, 7), dtype=np.float32)
        fake_y = np.array([1, 0] * 12 + [1], dtype=np.int32)
        fake_groups = np.array([2] * 12 + [1], dtype=np.int32)  # 13 distinct queries

        # Mock train_ltr_model to return a dummy booster that writes a candidate file
        mock_booster = MagicMock()
        def mock_save_model(path, **kwargs):
            Path(path).write_text("CANDIDATE_MODEL_INFERIOR_CONTENT", encoding="utf-8")
        mock_booster.save_model = mock_save_model
        mock_booster.best_iteration = 10

        # Mock run_evaluation:
        # First call (candidate) returns NDCG@5 = 0.7200
        # Second call (current) returns NDCG@5 = 0.8800
        eval_call_count = 0
        def mock_run_evaluation(retrieval_fn, eval_set_path=None):
            nonlocal eval_call_count
            eval_call_count += 1
            if eval_call_count == 1:
                # Candidate evaluation (inferior)
                return {
                    "overall": {"precision_at_1": 0.65, "recall_at_5": 0.75, "ndcg_at_5": 0.7200},
                    "by_category": {"easy": {"ndcg_at_5": 0.8000}, "hard_duplicate": {"ndcg_at_5": 0.6400}}
                }
            else:
                # Current evaluation (superior)
                return {
                    "overall": {"precision_at_1": 0.85, "recall_at_5": 0.90, "ndcg_at_5": 0.8800},
                    "by_category": {"easy": {"ndcg_at_5": 0.9500}, "hard_duplicate": {"ndcg_at_5": 0.8100}}
                }

        with patch("feedback.retrain_and_promote.load_logs", return_value=[MagicMock()] * 25), \
             patch("feedback.retrain_and_promote.logs_to_training_data", return_value=(fake_X, fake_y, fake_groups)), \
             patch("feedback.retrain_and_promote.train_ltr_model", return_value=(mock_booster, {})), \
             patch("feedback.retrain_and_promote.lgb.Booster", return_value=MagicMock()), \
             patch("feedback.retrain_and_promote.run_evaluation", side_effect=mock_run_evaluation):

            result = run_retraining_cycle(
                logs_path=str(self.temp_logs_path),
                eval_set_path=str(_EVAL_SET_PATH),
                current_model_path=str(self.temp_current_path),
                candidate_model_path=str(self.temp_candidate_path),
                min_queries=10,
                verbose=False
            )

        # 1. Gate must reject candidate
        self.assertFalse(result["promoted"])
        self.assertIn("candidate_worse", result["reason"])
        self.assertEqual(result["candidate_ndcg5"], 0.7200)
        self.assertEqual(result["current_ndcg5"], 0.8800)

        # 2. Current model file must remain 100% untouched
        after_content = self.temp_current_path.read_text(encoding="utf-8")
        after_hash = hashlib.sha256(after_content.encode("utf-8")).hexdigest()
        self.assertEqual(after_content, original_model_content)
        self.assertEqual(after_hash, original_hash)

        # 3. Candidate model file must have been discarded / deleted
        self.assertFalse(self.temp_candidate_path.exists())

    # --- 3. First-Run Auto-Promotion Test ---

    def test_first_run_auto_promotion(self):
        """Assert that when no current model exists, candidate is automatically promoted."""
        # Ensure current model does not exist
        non_existent_current = self.sandbox / "brand_new_ltr_model.txt"
        self.assertFalse(non_existent_current.exists())

        fake_X = np.ones((30, 7), dtype=np.float32)
        fake_y = np.array([1, 0] * 15, dtype=np.int32)
        fake_groups = np.array([2] * 15, dtype=np.int32)  # 15 distinct queries

        mock_booster = MagicMock()
        def mock_save_model(path, **kwargs):
            Path(path).write_text("FIRST_RUN_CANDIDATE_MODEL_WEIGHTS", encoding="utf-8")
        mock_booster.save_model = mock_save_model
        mock_booster.best_iteration = 15

        def mock_run_evaluation(retrieval_fn, eval_set_path=None):
            return {
                "overall": {"precision_at_1": 0.80, "recall_at_5": 0.88, "ndcg_at_5": 0.8450},
                "by_category": {"easy": {"ndcg_at_5": 0.9000}}
            }

        with patch("feedback.retrain_and_promote.load_logs", return_value=[MagicMock()] * 30), \
             patch("feedback.retrain_and_promote.logs_to_training_data", return_value=(fake_X, fake_y, fake_groups)), \
             patch("feedback.retrain_and_promote.train_ltr_model", return_value=(mock_booster, {})), \
             patch("feedback.retrain_and_promote.lgb.Booster", return_value=MagicMock()), \
             patch("feedback.retrain_and_promote.run_evaluation", side_effect=mock_run_evaluation):

            result = run_retraining_cycle(
                logs_path=str(self.temp_logs_path),
                eval_set_path=str(_EVAL_SET_PATH),
                current_model_path=str(non_existent_current),
                candidate_model_path=str(self.temp_candidate_path),
                min_queries=10,
                verbose=False
            )

        # 1. Gate must auto-promote
        self.assertTrue(result["promoted"])
        self.assertEqual(result["reason"], "first_run_auto_promotion")
        self.assertEqual(result["candidate_ndcg5"], 0.8450)
        self.assertIsNone(result["current_ndcg5"])

        # 2. Candidate must now be copied into production path
        self.assertTrue(non_existent_current.exists())
        self.assertEqual(non_existent_current.read_text(encoding="utf-8"), "FIRST_RUN_CANDIDATE_MODEL_WEIGHTS")

    # --- 4. Persistent History Audit Trail Test ---

    def test_log_retraining_run(self):
        """Assert log_retraining_run appends a clean, valid JSON line to retraining_history.jsonl."""
        dummy_result = {
            "promoted": True,
            "reason": "candidate_equal_or_better",
            "timestamp": "2026-09-19T20:30:00Z",
            "distinct_queries": 50,
            "candidate_ndcg5": 0.8650,
            "current_ndcg5": 0.8450,
            "candidate_eval": {
                "overall": {"precision_at_1": 0.85, "recall_at_5": 0.90, "ndcg_at_5": 0.8650},
                "by_category": {"easy": {"ndcg_at_5": 0.92}, "hard_duplicate": {"ndcg_at_5": 0.81}}
            },
            "current_eval": {
                "overall": {"precision_at_1": 0.80, "recall_at_5": 0.88, "ndcg_at_5": 0.8450},
                "by_category": {"easy": {"ndcg_at_5": 0.88}, "hard_duplicate": {"ndcg_at_5": 0.79}}
            }
        }

        history_path = log_retraining_run(dummy_result, history_path=self.temp_history_path)
        self.assertTrue(history_path.exists())

        lines = [l.strip() for l in history_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)

        record = json.loads(lines[0])
        self.assertTrue(record["promoted"])
        self.assertEqual(record["distinct_queries"], 50)
        self.assertEqual(record["candidate_ndcg5"], 0.8650)
        self.assertEqual(record["current_ndcg5"], 0.8450)
        self.assertEqual(record["candidate_p1"], 0.85)
        self.assertEqual(record["current_p1"], 0.80)
        self.assertIn("timestamp", record)

    # --- 5. Real End-to-End Retraining Cycle ---

    def test_real_end_to_end_cycle_execution(self):
        """Assert a real end-to-end retraining run executes against the clean synthetic logs."""
        self.assertTrue(_INTERACTION_LOGS_PATH.exists(), "interaction_logs.jsonl missing")
        self.assertTrue(_EVAL_SET_PATH.exists(), "eval_set.json missing")

        # Copy existing live model to sandbox as current model so we don't mutate models/ltr_model.txt
        live_model_path = _PROJECT_ROOT / "models" / "ltr_model.txt"
        if live_model_path.exists():
            import shutil
            shutil.copyfile(live_model_path, self.temp_current_path)

        result = run_retraining_cycle(
            logs_path=str(_INTERACTION_LOGS_PATH),
            eval_set_path=str(_EVAL_SET_PATH),
            current_model_path=str(self.temp_current_path),
            candidate_model_path=str(self.temp_candidate_path),
            min_queries=10,
            verbose=True
        )

        self.assertIn("promoted", result)
        self.assertIn("candidate_ndcg5", result)
        self.assertGreaterEqual(result["distinct_queries"], 10)
        self.assertGreater(result["candidate_ndcg5"], 0.0)
        self.assertIsInstance(result["candidate_eval"], dict)

        # Log into sandbox history
        log_retraining_run(result, history_path=self.temp_history_path)
        self.assertTrue(self.temp_history_path.exists())


if __name__ == "__main__":
    unittest.main()
