"""Tests for the researched certification mapping and its coverage.

Certification is the highest-stakes data in this system because the failure is
asymmetric: claiming a mark is needed when it is not is an inconvenience;
claiming none is needed when one is costs a tender. Nearly every assertion
here is therefore about the difference between "checked, none applies" and
"never checked", which must never collapse into each other.
"""
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import certification


class TestRuleListing(unittest.TestCase):
    """What `all_rules()` returns, and what it deliberately omits."""

    def test_only_researched_standards_are_listed(self):
        """The corpus holds thousands nobody has checked; none may appear here.

        Listing an unresearched standard as "no scheme" would convert an
        absence of research into a positive clearance.
        """
        rules = certification.all_rules()
        listed = {r["is_number"] for r in rules}

        # A real standard that exists in the corpus but has no researched rule.
        unresearched = certification.lookup("IS 7098 (Part 2):2011")
        if unresearched["scheme"] == "not_verified":
            self.assertNotIn("IS 7098 (Part 2):2011", listed)

    def test_every_rule_has_a_scheme_and_explanation(self):
        for rule in certification.all_rules():
            self.assertIn(rule["scheme"], {"ISI", "CRS", "Hallmark", "none"})
            self.assertTrue(rule["explanation"])

    def test_mandatory_is_only_true_for_a_real_scheme(self):
        for rule in certification.all_rules():
            if rule["scheme"] == "none":
                self.assertFalse(rule["mandatory"])
            else:
                self.assertTrue(rule["mandatory"])

    def test_mandatory_rules_name_the_order_they_rest_on(self):
        """A legal obligation with no citation cannot be checked or defended."""
        for rule in certification.all_rules():
            if rule["mandatory"]:
                self.assertTrue(
                    rule["qco"],
                    f"{rule['is_number']} claims a mandatory scheme with no QCO",
                )

    def test_mandatory_rules_sort_first(self):
        mandatory_flags = [r["mandatory"] for r in certification.all_rules()]
        self.assertEqual(mandatory_flags, sorted(mandatory_flags, reverse=True))

    def test_is_numbers_use_the_stored_spelling_not_the_lookup_key(self):
        """Lookup keys are upper-cased; the UI must not render "(PART 1)".

        Only meaningful for numbers containing a part designation, since
        "IS 269:2015" is identical either way.
        """
        with_parts = [r for r in certification.all_rules() if "(Part" in r["is_number"]]
        self.assertTrue(with_parts, "expected at least one multi-part standard")

        for rule in with_parts:
            self.assertNotIn("(PART", rule["is_number"])

    def test_listing_agrees_with_per_standard_lookup(self):
        """The list and the detail endpoint must not disagree about a scheme."""
        for rule in certification.all_rules():
            looked_up = certification.lookup(rule["is_number"])
            self.assertEqual(looked_up["scheme"], rule["scheme"])
            self.assertEqual(looked_up["mandatory"], rule["mandatory"])


class TestCoverage(unittest.TestCase):
    """The statement of what was not researched."""

    def test_counts_partition_the_researched_set(self):
        coverage = certification.coverage()
        self.assertEqual(
            coverage["mandatory"] + coverage["no_scheme"],
            coverage["standards_researched"],
        )

    def test_counts_match_the_rule_list(self):
        coverage = certification.coverage()
        rules = certification.all_rules()

        self.assertEqual(coverage["standards_researched"], len(rules))
        self.assertEqual(coverage["mandatory"], sum(1 for r in rules if r["mandatory"]))

    def test_note_refuses_to_read_absence_as_clearance(self):
        note = certification.coverage()["note"].lower()
        self.assertIn("not_verified", note)
        self.assertIn("not a statement", note)

    def test_source_is_named(self):
        self.assertIn("BIS", certification.coverage()["source"])


class TestUnresearchedStandards(unittest.TestCase):
    """The behaviour that the whole screen rests on."""

    def test_unknown_standard_is_not_verified_not_cleared(self):
        result = certification.lookup("IS 99999:2020")

        self.assertEqual(result["scheme"], "not_verified")
        self.assertFalse(result["mandatory"])
        self.assertIn("not the same as", result["explanation"])

    def test_not_verified_is_distinct_from_none(self):
        """'checked, none applies' and 'never checked' are different answers."""
        rules = certification.all_rules()
        checked_none = [r for r in rules if r["scheme"] == "none"]
        if not checked_none:
            self.skipTest("no 'none' rules in the current data")

        confirmed = certification.lookup(checked_none[0]["is_number"])
        unknown = certification.lookup("IS 99999:2020")

        self.assertEqual(confirmed["scheme"], "none")
        self.assertEqual(unknown["scheme"], "not_verified")
        self.assertNotEqual(confirmed["explanation"], unknown["explanation"])


class TestEndpoint(unittest.TestCase):
    """The HTTP contract the certification screen consumes."""

    def test_rules_endpoint_matches_schema(self):
        from main import app

        with TestClient(app) as client:
            res = client.get("/certification-rules")
            self.assertEqual(res.status_code, 200)
            body = res.json()

        self.assertIn("rules", body)
        self.assertIn("coverage", body)
        for rule in body["rules"]:
            self.assertIn("is_number", rule)
            self.assertIn("scheme", rule)
            if rule["mandatory"]:
                self.assertTrue(rule["qco"])

    def test_endpoint_never_lists_a_not_verified_scheme(self):
        """'not_verified' is a per-lookup answer, never a listed rule."""
        from main import app

        with TestClient(app) as client:
            body = client.get("/certification-rules").json()

        for rule in body["rules"]:
            self.assertNotEqual(rule["scheme"], "not_verified")


if __name__ == "__main__":
    unittest.main()
