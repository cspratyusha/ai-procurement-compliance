"""Guard against training on the evaluation set.

`build_training_data` used to load the query set *and* the evaluation set as
its training input. The eval queries were held out from the train/test split
but not from training, so the model had seen every query it was then scored
on. On the 96-standard corpus that produced NDCG@5 = 1.0000 and P@1 = 100% —
a memorisation artifact reported as accuracy.

That is the most dangerous class of bug in this project, because it does not
look like a failure. It looks like success.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ltr.train as train  # noqa: E402


class TestTrainingIsolation(unittest.TestCase):
    """The eval set must not reach training unless explicitly asked for."""

    def _captured_paths(self, env: dict) -> list:
        """Run build_training_data far enough to see which files it chose."""
        captured = []

        def fake_load_eval_set(path):
            captured.append(Path(path).name)
            return []  # no queries: stop before any model work

        with patch.dict(os.environ, env, clear=False), \
             patch.object(train, "load_eval_set", side_effect=fake_load_eval_set), \
             patch.object(train, "load_corpus", return_value=[]):
            try:
                train.build_training_data()
            except Exception:
                # We only care which files were opened, not the outcome of a
                # run we deliberately starved of data.
                pass

        return captured

    def test_eval_set_is_excluded_by_default(self):
        for corpus in ("canonical", "expanded", "full", ""):
            with self.subTest(corpus=corpus or "mock"):
                names = self._captured_paths({"STANDARDS_CORPUS": corpus,
                                              "LTR_INCLUDE_EVAL_IN_TRAINING": ""})
                if not names:
                    # That corpus has no query sets on disk yet, so there is
                    # nothing to leak. Not a failure.
                    continue
                for name in names:
                    self.assertNotIn(
                        "eval_set", name,
                        f"{name} is the evaluation set and must not be trained on",
                    )

    def test_eval_set_can_be_included_deliberately(self):
        """Shipping a model may warrant every labelled example.

        That is a legitimate choice, but it must be explicit, and the score
        from such a run is not a measurement.
        """
        names = self._captured_paths({"STANDARDS_CORPUS": "expanded",
                                      "LTR_INCLUDE_EVAL_IN_TRAINING": "1"})
        self.assertTrue(any("eval_set" in n for n in names))

    def test_query_set_is_always_present(self):
        """Excluding the eval set must not leave training with nothing."""
        names = self._captured_paths({"STANDARDS_CORPUS": "expanded",
                                      "LTR_INCLUDE_EVAL_IN_TRAINING": ""})
        self.assertTrue(any("train_queries" in n for n in names))


if __name__ == "__main__":
    unittest.main()
