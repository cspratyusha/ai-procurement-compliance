"""Tests for published-amendment data.

An amendment can change the material, the test regime or the acceptance
criteria, so a tender citing an un-amended edition can specify something that
is no longer conformant. The tests here are mostly about not overstating what
we know: a count without dates must not become invented dates, and an
unresearched standard must not read as having no amendments.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import amendments  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestAmendments(unittest.TestCase):
    def test_known_standard_lists_its_amendments(self):
        result = amendments.for_standard("IS 456:2000")
        self.assertTrue(result["checked"])
        self.assertEqual(result["count"], 6)
        self.assertEqual(len(result["amendments"]), 6)

        fourth = next(a for a in result["amendments"] if a["number"] == 4)
        self.assertEqual(fourth["readable_date"], "May 2013")
        self.assertEqual(fourth["confidence"], "confirmed")
        self.assertIn("aggregates", fourth["summary"].lower())

    def test_count_without_dates_does_not_invent_them(self):
        """BIS states IS 694 has four amendments but not which or when.

        Listing four entries with plausible-looking dates would be fabrication.
        The count is reported; the list stays empty.
        """
        result = amendments.for_standard("IS 694:2010")
        self.assertTrue(result["checked"])
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["amendments"], [])
        self.assertIn("4 published amendments", result["citation"])

    def test_unresearched_standard_is_reported_as_unchecked(self):
        """Not the same as having no amendments."""
        result = amendments.for_standard("IS 17048:2018")
        self.assertFalse(result["checked"])
        self.assertIsNone(result["count"])
        self.assertEqual(result["citation"], "IS 17048:2018")
        self.assertIn("not been checked", result["note"])

    def test_citation_names_the_latest_amendment_when_known(self):
        citation = amendments.for_standard("IS 456:2000")["citation"]
        self.assertIn("IS 456:2000", citation)
        self.assertIn("all 6 amendments", citation)
        self.assertIn("Amendment No. 6", citation)
        self.assertIn("June 2024", citation)

    def test_citation_omits_an_unknown_date(self):
        """IS 800 amendment 2 has no published date in our sources."""
        result = amendments.for_standard("IS 800:2007")
        second = next(a for a in result["amendments"] if a["number"] == 2)
        self.assertIsNone(second["readable_date"])
        self.assertNotIn("None", result["citation"])

    def test_is_number_spellings_resolve(self):
        canonical = amendments.for_standard("IS 456:2000")
        for spelling in ("is 456:2000", "IS 456 : 2000"):
            with self.subTest(spelling=spelling):
                self.assertEqual(
                    amendments.for_standard(spelling)["count"], canonical["count"]
                )

    def test_every_entry_is_for_a_standard_in_the_corpus(self):
        corpus = {
            s["number"]
            for s in json.loads(
                (_REPO_ROOT / "data" / "standards_corpus.json").read_text(encoding="utf-8")
            )
        }
        payload = json.loads(
            (_REPO_ROOT / "data" / "amendments" / "amendments.json").read_text(encoding="utf-8")
        )
        for number in payload["standards"]:
            with self.subTest(number=number):
                self.assertIn(number, corpus)

    def test_every_amendment_declares_its_confidence(self):
        """A 'likely' date read from a secondary source must say so."""
        payload = json.loads(
            (_REPO_ROOT / "data" / "amendments" / "amendments.json").read_text(encoding="utf-8")
        )
        for number, entry in payload["standards"].items():
            for item in entry.get("amendments", []):
                with self.subTest(number=number, amendment=item["number"]):
                    self.assertIn(item.get("confidence"), {"confirmed", "likely"})


if __name__ == "__main__":
    unittest.main()
