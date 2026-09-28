"""Tests for the certification rule listing and its coverage statement."""

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import certification  # noqa: E402


class TestRuleListing(unittest.TestCase):
    def test_the_bis_lists_are_loaded_in_full(self):
        """Hundreds of products, not the 17 researched by hand before."""
        self.assertGreater(len(certification.all_rules()), 700)

    def test_statuses_and_schemes_agree(self):
        for rule in certification.all_rules():
            self.assertIn(rule["status"], {"in_force", "deferred", "voluntary", "checked_none"})
            self.assertEqual(rule["mandatory"], rule["status"] == "in_force")
            if rule["status"] == "checked_none":
                self.assertEqual(rule["scheme"], "none")
            else:
                self.assertIn(rule["scheme"], {"ISI", "CRS", "Scheme X", "Hallmark"})
            self.assertTrue(rule["explanation"])

    def test_every_obligation_names_and_links_its_order(self):
        """A legal obligation with no citation cannot be checked or defended."""
        for rule in certification.all_rules():
            if rule["status"] in ("in_force", "deferred"):
                with self.subTest(is_number=rule["is_number"]):
                    self.assertTrue(rule["qco"])
                    self.assertTrue(rule["qco_url"])
                    self.assertTrue(rule["products"])

    def test_in_force_sorts_first(self):
        order = {"in_force": 0, "deferred": 1, "voluntary": 2, "checked_none": 3}
        ranks = [order[r["status"]] for r in certification.all_rules()]
        self.assertEqual(ranks, sorted(ranks))

    def test_listing_agrees_with_per_standard_lookup(self):
        for rule in certification.all_rules():
            looked_up = certification.lookup(rule["is_number"])
            self.assertEqual(looked_up["status"], rule["status"])
            self.assertEqual(looked_up["mandatory"], rule["mandatory"])

    def test_numbers_are_in_corpus_spelling(self):
        for rule in certification.all_rules():
            self.assertNotIn("(PART", rule["is_number"])
            self.assertNotIn("Section", rule["is_number"])


class TestCoverage(unittest.TestCase):
    def test_counts_partition_the_listing(self):
        c = certification.coverage()
        self.assertEqual(c["mandatory"] + c["deferred"] + c["voluntary"] + c["no_scheme"],
                         c["standards_researched"])
        self.assertEqual(c["standards_researched"], len(certification.all_rules()))

    def test_source_and_date_are_stated(self):
        c = certification.coverage()
        self.assertIn("BIS", c["source"])
        self.assertTrue(c["retrieved"])
        self.assertIn("not_verified", c["note"])


class TestEndpoint(unittest.TestCase):
    def test_rules_endpoint_matches_schema(self):
        from main import app

        with TestClient(app) as client:
            body = client.get("/certification-rules").json()

        self.assertGreater(len(body["rules"]), 700)
        for rule in body["rules"]:
            self.assertNotIn(rule["scheme"], ("not_verified", "not_listed", "related"))
            if rule["mandatory"]:
                self.assertTrue(rule["qco"])
        self.assertIn("deferred", body["coverage"])


if __name__ == "__main__":
    unittest.main()
