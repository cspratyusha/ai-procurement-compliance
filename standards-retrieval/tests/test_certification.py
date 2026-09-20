"""Tests for the mandatory-certification lookup.

The distinction these guard is not cosmetic: a procurement officer acting on
"no certification required" when the real answer is "we never checked" is the
failure mode that matters, so `none` and `not_verified` must never collapse.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import certification  # noqa: E402


class TestCertificationLookup(unittest.TestCase):
    def test_confirmed_isi_requirement_carries_its_qco(self):
        """A mandatory requirement must name the order that imposes it."""
        result = certification.lookup("IS 694:2010")
        self.assertEqual(result["scheme"], "ISI")
        self.assertTrue(result["mandatory"])
        self.assertIn("Electrical Wires", result["qco"])
        self.assertIn("ISI mark", result["explanation"])

    def test_code_of_practice_has_no_product_certification(self):
        """A code of practice governs workmanship, not a supplied product."""
        result = certification.lookup("IS 456:2000")
        self.assertEqual(result["scheme"], "none")
        self.assertFalse(result["mandatory"])

    def test_unknown_standard_is_not_verified_rather_than_none(self):
        """The critical distinction: unchecked is not the same as cleared.

        Returning 'none' here would tell an official that no certification is
        needed, when the truth is that nobody looked.
        """
        result = certification.lookup("IS 17048:2018")
        self.assertEqual(result["scheme"], "not_verified")
        self.assertFalse(result["mandatory"])
        self.assertIn("not the same", result["explanation"])

    def test_is_number_spellings_resolve_to_the_same_rule(self):
        canonical = certification.lookup("IS 1489 (Part 1):2015")
        self.assertEqual(canonical["scheme"], "ISI")
        for spelling in ("is 1489 (part 1):2015", "IS 1489 (Part 1) : 2015"):
            with self.subTest(spelling=spelling):
                self.assertEqual(certification.lookup(spelling)["scheme"], "ISI")

    def test_withdrawn_editions_are_flagged(self):
        """IS 8112 and IS 12269 were merged into IS 269:2015 and withdrawn.

        The placeholder corpus names editions of them that never existed;
        saying so is better than serving a standard that does not exist.
        """
        note = certification.withdrawn_note("IS 8112:2018")
        self.assertIsNotNone(note)
        self.assertEqual(note["superseded_by"], "IS 269:2015")
        self.assertIsNone(certification.withdrawn_note("IS 694:2010"))

    def test_every_rule_points_at_a_real_standard(self):
        """A rule for a standard not in the corpus can never be surfaced."""
        import json

        repo_root = Path(__file__).resolve().parent.parent.parent
        corpus = {
            s["number"]
            for s in json.loads(
                (repo_root / "data" / "standards_corpus.json").read_text(encoding="utf-8")
            )
        }
        rules = json.loads(
            (repo_root / "data" / "certification" / "certification_rules.json").read_text(
                encoding="utf-8"
            )
        )
        for rule in rules["rules"]:
            with self.subTest(is_number=rule["is_number"]):
                self.assertIn(rule["is_number"], corpus)


if __name__ == "__main__":
    unittest.main()
