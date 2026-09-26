"""Tests for the standards-hygiene findings and corpus-health counts.

These back two screens that used to be pure fixtures, so the assertions that
matter most are about restraint: a finding is only raised where the data
supports it, a replacement is only named where the corpus actually holds it,
and nothing acquires a timestamp the corpus cannot justify.
"""
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import alerts as alerts_module


class TestSupersessionFindings(unittest.TestCase):
    """Findings derived from a corpus built for the test, not the shipped one."""

    def setUp(self):
        from tests.conftest import _standard

        self.corpus = [
            _standard(
                id="T-OLD", number="IS 1554 (Part 1):1988",
                title="PVC Insulated Cables, superseded edition",
                category="electrical_cables", status="superseded",
            ),
            _standard(
                id="T-NEW", number="IS 1554 (Part 1):2020",
                title="PVC Insulated Cables, current edition",
                category="electrical_cables", status="active",
            ),
            _standard(
                id="T-ORPHAN", number="IS 226:1975",
                title="Structural Steel, superseded with no successor held",
                category="structural_steel", status="superseded",
            ),
            _standard(
                id="T-FINE", number="IS 694:2010",
                title="An ordinary active standard",
                category="electrical_cables", status="active",
            ),
        ]

    def test_replacement_is_named_when_corpus_holds_it(self):
        found = alerts_module._supersession_findings(self.corpus)
        by_standard = {f["standard"]: f for f in found}

        finding = by_standard["IS 1554 (Part 1):1988"]
        self.assertEqual(finding["severity"], "critical")
        self.assertEqual(finding["replacement"], "IS 1554 (Part 1):2020")
        self.assertIn("IS 1554 (Part 1):2020", finding["action"])

    def test_missing_replacement_is_admitted_not_guessed(self):
        """The corpus holds no successor, so none may be named."""
        found = alerts_module._supersession_findings(self.corpus)
        finding = next(f for f in found if f["standard"] == "IS 226:1975")

        self.assertEqual(finding["severity"], "warning")
        self.assertIsNone(finding["replacement"])
        self.assertIn("does not hold", finding["detail"])

    def test_active_standards_raise_no_finding(self):
        found = alerts_module._supersession_findings(self.corpus)
        self.assertNotIn("IS 694:2010", {f["standard"] for f in found})

    def test_a_replacement_is_never_the_superseded_record_itself(self):
        for finding in alerts_module._supersession_findings(self.corpus):
            self.assertNotEqual(finding["replacement"], finding["standard"])


class TestFindingShape(unittest.TestCase):
    """Properties every finding must hold, whatever the corpus."""

    def test_no_finding_carries_a_timestamp(self):
        """The corpus does not record when a revision was published.

        The fixture screen's "2 hours ago" was its most convincing and least
        true detail. Nothing may reintroduce it.
        """
        payload = alerts_module.findings()
        for finding in payload["findings"]:
            for banned in ("time", "timestamp", "when", "age", "unread"):
                self.assertNotIn(banned, finding)

    def test_critical_findings_always_name_a_replacement(self):
        """Critical means "the fix is known" — so the fix must be present."""
        payload = alerts_module.findings()
        for finding in payload["findings"]:
            if finding["severity"] == "critical":
                self.assertTrue(finding["replacement"])

    def test_critical_count_matches_the_findings(self):
        payload = alerts_module.findings()
        counted = sum(1 for f in payload["findings"] if f["severity"] == "critical")
        self.assertEqual(payload["critical_count"], counted)

    def test_findings_are_ordered_critical_first(self):
        severities = [f["severity"] for f in alerts_module.findings()["findings"]]
        self.assertEqual(severities, sorted(severities, key=lambda s: s != "critical"))

    def test_category_filter_narrows_the_scan(self):
        everything = alerts_module.findings()["findings"]
        categories = {f["category"] for f in everything if f["category"]}
        if not categories:
            self.skipTest("no categorised findings in this corpus")

        target = next(iter(categories))
        filtered = alerts_module.findings(category=target)["findings"]
        self.assertTrue(filtered)
        self.assertTrue(all(f["category"] == target for f in filtered))


class TestCoverage(unittest.TestCase):
    """The caveat that stops a short list reading as an all-clear."""

    def test_coverage_reports_what_was_never_checked(self):
        coverage = alerts_module.coverage()
        self.assertGreater(coverage["corpus_size"], 0)
        self.assertGreaterEqual(coverage["amendments_unchecked"], 0)
        self.assertEqual(
            coverage["amendments_researched"] + coverage["amendments_unchecked"],
            coverage["corpus_size"],
        )

    def test_coverage_note_refuses_to_claim_monitoring(self):
        note = alerts_module.coverage()["note"].lower()
        self.assertIn("not a statement that it has none", note)
        self.assertIn("monitors", note)


class TestCorpusHealth(unittest.TestCase):
    """Counts behind the corpus-health screen."""

    def test_counts_partition_the_corpus(self):
        health = alerts_module.corpus_health()
        self.assertEqual(health["active"] + health["superseded"], health["corpus_size"])

    def test_unverified_certification_is_counted_not_hidden(self):
        """An unverified status is explicitly not a clearance, so it is reported."""
        health = alerts_module.corpus_health()
        self.assertGreaterEqual(health["certification_not_verified"], 0)
        self.assertLessEqual(
            health["certification_mandatory"] + health["certification_not_verified"],
            health["corpus_size"],
        )

    def test_sectors_sum_to_the_corpus(self):
        health = alerts_module.corpus_health()
        self.assertEqual(
            sum(s["standards"] for s in health["sectors"]), health["corpus_size"]
        )

    def test_researched_counts_never_exceed_the_corpus(self):
        """The ratio is the honest unit; a numerator above its denominator is a bug."""
        health = alerts_module.corpus_health()
        self.assertLessEqual(health["amendments_researched"], health["corpus_size"])


class TestEndpoints(unittest.TestCase):
    """The HTTP contracts the two screens consume."""

    def test_alerts_endpoint_matches_schema(self):
        from main import app

        with TestClient(app) as client:
            res = client.get("/alerts")
            self.assertEqual(res.status_code, 200)
            body = res.json()

        self.assertIn("findings", body)
        self.assertIn("critical_count", body)
        self.assertIn("coverage", body)
        for finding in body["findings"]:
            self.assertIn(finding["kind"], ("supersession", "amendment"))
            self.assertIn(finding["severity"], ("critical", "warning"))
            self.assertTrue(finding["action"])

    def test_corpus_health_endpoint_matches_schema(self):
        from main import app

        with TestClient(app) as client:
            res = client.get("/corpus-health")
            self.assertEqual(res.status_code, 200)
            body = res.json()

        for field in (
            "corpus_size", "active", "superseded",
            "certification_mandatory", "certification_not_verified",
            "amendments_researched", "sectors",
        ):
            self.assertIn(field, body)

    def test_unknown_category_returns_empty_not_an_error(self):
        """No findings in a sector is a real answer, not a failure."""
        from main import app

        with TestClient(app) as client:
            res = client.get("/alerts", params={"category": "no-such-sector"})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["findings"], [])


if __name__ == "__main__":
    unittest.main()
