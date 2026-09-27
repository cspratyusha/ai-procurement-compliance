"""Tests for the query log and the dashboard statistics it feeds.

The property under test throughout is honesty: every figure the dashboard
shows must be a count of something that actually happened. The tests that
matter most here are the ones asserting what is *not* counted, synthetic
bootstrap records, and rates that cannot yet be calculated.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from feedback.query_log import append_query, read_queries
from feedback.stats import compute_stats


def _iso(days_ago=0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _query(**overrides):
    """A complete query-log record, overridable field by field."""
    base = dict(
        query="PVC insulated copper cable 1100 V",
        top_result_id="IS-ELEC-001",
        top_result_number="IS 694:2010",
        top_score=0.82,
        confidence="strong",
        category="electrical_cables",
        result_count=10,
        corpus_size=30,
        elapsed_ms=380,
        language=None,
        source="live",
        timestamp=_iso(),
    )
    base.update(overrides)
    return base


class TestQueryLog(unittest.TestCase):
    """The append-only log itself."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "query_logs.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_reads_as_empty(self):
        """An engine that has served nothing is a normal state, not an error."""
        self.assertEqual(read_queries(path=self.path), [])

    def test_appends_are_durable_and_ordered(self):
        for i in range(3):
            append_query(path=self.path, **_query(query=f"query {i}"))

        records = read_queries(path=self.path)
        self.assertEqual([r["query"] for r in records], ["query 0", "query 1", "query 2"])

    def test_corrupt_line_is_skipped_not_fatal(self):
        """A partial write must cost one record, not the whole history."""
        append_query(path=self.path, **_query(query="good one"))
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("{not valid json\n")
        append_query(path=self.path, **_query(query="good two"))

        records = read_queries(path=self.path)
        self.assertEqual([r["query"] for r in records], ["good one", "good two"])

    def test_logging_never_raises(self):
        """A search must not fail because its own bookkeeping did."""
        # A path whose parent is an existing *file* cannot be created.
        blocker = Path(self.tmp.name) / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        append_query(path=blocker / "deeper.jsonl", **_query())  # must not raise


class TestStats(unittest.TestCase):
    """Aggregation over the two logs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.qpath = Path(self.tmp.name) / "query_logs.jsonl"
        self.ipath = Path(self.tmp.name) / "interaction_logs.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _stats(self):
        return compute_stats(query_log_path=self.qpath, interaction_log_path=self.ipath)

    def _interaction(self, **overrides):
        base = dict(
            query="cable",
            candidates_shown=[{"id": "IS-ELEC-001", "final_score": 0.8, "rank": 1}],
            chosen_id="IS-ELEC-001",
            action="accept",
            corrected_id=None,
            timestamp=_iso(),
            source="live",
        )
        base.update(overrides)
        with open(self.ipath, "a", encoding="utf-8") as f:
            f.write(json.dumps(base) + "\n")

    def test_empty_logs_report_empty(self):
        """Zero, explicitly flagged, never a plausible-looking placeholder."""
        s = self._stats()
        self.assertFalse(s["has_live_data"])
        self.assertEqual(s["queries_total"], 0)
        self.assertIsNone(s["match_rate"])
        self.assertIsNone(s["acceptance_rate"])
        self.assertIsNone(s["median_latency_ms"])
        self.assertEqual(s["recent_queries"], [])

    def test_counts_served_searches(self):
        for i in range(5):
            append_query(path=self.qpath, **_query(query=f"q{i}"))
        s = self._stats()
        self.assertTrue(s["has_live_data"])
        self.assertEqual(s["queries_total"], 5)
        self.assertEqual(s["queries_last_7d"], 5)

    def test_synthetic_queries_are_not_counted_as_usage(self):
        """The bootstrap records are real, but they are not use."""
        append_query(path=self.qpath, **_query(source="live"))
        append_query(path=self.qpath, **_query(source="synthetic"))
        append_query(path=self.qpath, **_query(source="synthetic"))

        s = self._stats()
        self.assertEqual(s["queries_total"], 1)

    def test_synthetic_interactions_reported_separately(self):
        self._interaction(source="live")
        self._interaction(source="synthetic")
        self._interaction(source="synthetic")

        s = self._stats()
        self.assertEqual(s["feedback_total"], 1)
        self.assertEqual(s["synthetic_interactions"], 2)

    def test_no_match_queries_counted(self):
        """The standards-gap signal: what officials asked for that the corpus lacks."""
        append_query(path=self.qpath, **_query(confidence="strong"))
        append_query(path=self.qpath, **_query(confidence="strong"))
        append_query(path=self.qpath, **_query(confidence="none", top_result_number=None))

        s = self._stats()
        self.assertEqual(s["no_match_queries"], 1)
        self.assertAlmostEqual(s["match_rate"], 66.7, places=1)

    def test_time_windows_exclude_older_records(self):
        append_query(path=self.qpath, **_query(timestamp=_iso(days_ago=1)))
        append_query(path=self.qpath, **_query(timestamp=_iso(days_ago=10)))
        append_query(path=self.qpath, **_query(timestamp=_iso(days_ago=60)))

        s = self._stats()
        self.assertEqual(s["queries_total"], 3)
        self.assertEqual(s["queries_last_30d"], 2)
        self.assertEqual(s["queries_last_7d"], 1)

    def test_median_latency_resists_cold_start_outlier(self):
        """One 45-second model load must not become the reported response time."""
        for ms in (300, 350, 400):
            append_query(path=self.qpath, **_query(elapsed_ms=ms))
        append_query(path=self.qpath, **_query(elapsed_ms=45000))

        s = self._stats()
        self.assertEqual(s["median_latency_ms"], 375)

    def test_acceptance_rate_counts_all_decisions(self):
        self._interaction(action="accept")
        self._interaction(action="accept")
        self._interaction(action="reject", chosen_id=None)
        self._interaction(action="correct", corrected_id="IS-ELEC-002")

        s = self._stats()
        self.assertEqual(s["feedback_accepted"], 2)
        self.assertEqual(s["feedback_rejected"], 1)
        self.assertEqual(s["feedback_corrected"], 1)
        self.assertEqual(s["acceptance_rate"], 50.0)

    def test_recent_queries_newest_first(self):
        for i in range(3):
            append_query(path=self.qpath, **_query(query=f"q{i}"))
        s = self._stats()
        self.assertEqual([r["query"] for r in s["recent_queries"]], ["q2", "q1", "q0"])

    def test_categories_ranked_by_frequency(self):
        for _ in range(3):
            append_query(path=self.qpath, **_query(category="electrical_cables"))
        append_query(path=self.qpath, **_query(category="cement"))

        s = self._stats()
        self.assertEqual(s["categories"][0], {"category": "electrical cables", "queries": 3})

    def test_one_sector_spelled_two_ways_counts_once(self):
        """A log spanning a corpus switch holds both spellings of one sector.

        Counting them separately would show the same sector twice and
        understate each half.
        """
        for _ in range(2):
            append_query(path=self.qpath, **_query(category="electrical_cables"))
        append_query(path=self.qpath, **_query(category="Electrical Cables & Wires"))

        s = self._stats()
        self.assertEqual(len(s["categories"]), 1)
        self.assertEqual(s["categories"][0], {"category": "electrical cables", "queries": 3})

    def test_unparseable_timestamp_does_not_break_aggregation(self):
        append_query(path=self.qpath, **_query(timestamp="not a date"))
        append_query(path=self.qpath, **_query())

        s = self._stats()
        self.assertEqual(s["queries_total"], 2)    # still a served search
        self.assertEqual(s["queries_last_7d"], 1)  # but not placeable in a window


class TestStatsEndpoint(unittest.TestCase):
    """The HTTP contract the dashboard consumes."""

    def test_stats_endpoint_matches_schema(self):
        from main import app

        with TestClient(app) as client:
            res = client.get("/stats")
            self.assertEqual(res.status_code, 200)
            body = res.json()

        for field in (
            "has_live_data", "queries_total", "no_match_queries",
            "recent_queries", "categories", "synthetic_interactions",
        ):
            self.assertIn(field, body)


def test_retrieve_logs_the_search_it_served(_isolate_query_log):
    """The link between the two: searching must leave a record.

    A pytest function rather than a unittest method so it can take the
    session fixture that redirects the log away from the real file.
    """
    from main import app

    marker = "PVC insulated copper cable 1100 V logged by test_stats"
    with TestClient(app) as client:
        res = client.post("/retrieve", json={"query": marker, "top_k": 5})
        assert res.status_code == 200

    # Other tests share this session-scoped log, so find this search rather
    # than asserting on the file's length.
    records = [r for r in read_queries(path=_isolate_query_log) if r["query"] == marker]
    assert len(records) == 1
    assert records[0]["source"] == "live"
    assert records[0]["confidence"] in ("strong", "uncertain", "none")
    assert isinstance(records[0]["elapsed_ms"], int)


if __name__ == "__main__":
    unittest.main()
