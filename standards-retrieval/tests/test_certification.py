"""Tests for the mandatory-certification lookup, read from BIS's compulsory lists.

The failure that matters is asymmetric: telling an officer "no certification
needed" when an order requires it puts an uncertifiable product into a live
tender. So these pin that each status means what it says, that every
obligation names its order, that deferred orders are not reported as in
force, and that "not on the lists" never appears when the lists are missing.
"""

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent / "data" / "certification"))

import certification  # noqa: E402
from parse_bis_compulsory import numbers_in  # noqa: E402


class TestInForce(unittest.TestCase):
    def test_isi_requirement_carries_its_order(self):
        result = certification.lookup("IS 694:2010")
        self.assertEqual((result["scheme"], result["status"]), ("ISI", "in_force"))
        self.assertTrue(result["mandatory"])
        self.assertIn("Electrical Wires", result["qco"])
        self.assertIn("ISI mark", result["explanation"])
        self.assertTrue(result["qco_url"])

    def test_crs_requirement(self):
        result = certification.lookup("IS 16242 (Part 1):2014")      # UPS / inverters
        self.assertEqual((result["scheme"], result["status"]), ("CRS", "in_force"))
        self.assertIn("registration", result["explanation"].lower())

    def test_spellings_and_editions_resolve_to_the_same_family(self):
        for spelling in ("IS 1489 (Part 1):2015", "is 1489 (part 1):1991", "IS 1489 (Part 1) : 2015"):
            with self.subTest(spelling=spelling):
                self.assertEqual(certification.lookup(spelling)["status"], "in_force")

    def test_a_different_part_is_not_the_same_standard(self):
        self.assertEqual(certification.family("IS 1489 (Part 1):2015"), ("IS", "1489", ("1",)))
        self.assertNotEqual(certification.family("IS 1489 (Part 1)"), certification.family("IS 1489 (Part 2)"))

    def test_edition_differences_are_stated(self):
        rules = [r for r in certification.all_rules() if r["status"] == "in_force" and ":" in r["listed_as"]]
        rule = rules[0]
        family = rule["listed_as"].rsplit(":", 1)[0]
        other = f"{family}:1900" if not rule["listed_as"].endswith("1900") else f"{family}:1901"
        self.assertIn("edition", certification.lookup(other)["explanation"])


class TestDeferred(unittest.TestCase):
    """S.O. 5038(E), 6 Nov 2025: the Electrical Equipment QCO is deferred except Sr. 1.1(a)."""

    def test_deferred_categories_are_not_mandatory(self):
        result = certification.lookup("IS/IEC 60947-4-1:2000")          # contactors
        self.assertEqual(result["status"], "deferred")
        self.assertFalse(result["mandatory"])
        self.assertIn("5038", result["explanation"])

    def test_the_one_category_in_force_is_mandatory(self):
        result = certification.lookup("IS/IEC 60947-2:2003")            # circuit breakers, 1.1(a)
        self.assertEqual((result["scheme"], result["status"]), ("Scheme X", "in_force"))
        self.assertIn("deferred", result["explanation"])                # its other categories


class TestNotObligations(unittest.TestCase):
    def test_code_of_practice_checked_none(self):
        result = certification.lookup("IS 456:2000")
        self.assertEqual((result["scheme"], result["status"]), ("none", "checked_none"))
        self.assertFalse(result["mandatory"])

    def test_not_listed_says_when_the_lists_were_read(self):
        result = certification.lookup("IS 99999:2020")
        self.assertEqual(result["status"], "not_listed")
        self.assertFalse(result["mandatory"])
        self.assertIn(certification.coverage()["retrieved"], result["explanation"])

    def test_migrated_standard_names_its_successor(self):
        """CRS moved IS 13252 (Part 1) products (laptops, TVs) to IS/IEC 62368-1."""
        result = certification.lookup("IS 13252 (Part 1):2010")
        self.assertEqual(result["status"], "related_listed")
        self.assertIn("IS/IEC 62368-1", result["explanation"])

    def test_particular_part_points_to_the_listed_general_part(self):
        """Household appliances are listed under IS 302 (Part 1) with product names."""
        result = certification.lookup("IS 302 (Part 2/Sec 206):1994")
        self.assertEqual(result["status"], "related_listed")
        self.assertTrue(all(n.startswith("IS 302 (Part 1)") for n in result["related"]))
        self.assertFalse(result["mandatory"])

    def test_without_the_lists_nothing_is_called_not_listed(self):
        saved = certification._BIS_PATH
        try:
            certification._BIS_PATH = saved.with_name("missing.json")
            certification.reset_cache()
            result = certification.lookup("IS 99999:2020")
            self.assertEqual(result["status"], "not_verified")
            self.assertIn("not the same", result["explanation"])
            self.assertEqual(certification.lookup("IS 456:2000")["status"], "checked_none")
        finally:
            certification._BIS_PATH = saved
            certification.reset_cache()


class TestWithdrawn(unittest.TestCase):
    def test_withdrawn_editions_are_flagged(self):
        note = certification.withdrawn_note("IS 8112:2018")
        self.assertIsNotNone(note)
        self.assertEqual(note["superseded_by"], "IS 269:2015")
        self.assertIsNone(certification.withdrawn_note("IS 694:2010"))


class TestParser(unittest.TestCase):
    """BIS's web list spells numbers loosely; the parser writes corpus spelling."""

    def test_number_spellings(self):
        cases = {
            "IS 17077 :2019/ISO 19062-1 : 2015": ["IS 17077:2019"],
            "IS 302-2:26": ["IS 302 (Part 2/Sec 26)"],
            "IS/IEC 60947 : Part 4 : Sec 1 : 2018": ["IS/IEC 60947-4-1:2018"],
            "IS/IEC 62368: Part 1: 2023": ["IS/IEC 62368-1:2023"],
            "IS 7809 (Part3/ Sec1): 1986": ["IS 7809 (Part 3/Sec 1):1986"],
            "IS 302 (Part 1) : 2024 IEC 60335-1:2020": ["IS 302 (Part 1):2024"],
            "IS 14286 IS/IEC 61730 -1 IS/IEC 61730 -2": ["IS 14286", "IS/IEC 61730-1", "IS/IEC 61730-2"],
            "IS/ISO 11951 : 2016": ["IS/ISO 11951:2016"],
        }
        for cell, expected in cases.items():
            with self.subTest(cell=cell):
                self.assertEqual(numbers_in(cell), expected)


if __name__ == "__main__":
    unittest.main()
