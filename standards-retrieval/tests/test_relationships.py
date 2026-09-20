"""Tests for the allied-standards cluster.

The problem statement asks for the applicable cluster, not one hit. A tender
citing IS 694 for cable but omitting IS 8130 for the conductor is incomplete,
and that incompleteness is what this feature exists to surface. So the tests
are about whether the cluster is complete and honestly labelled, not about
whether a lookup returns something.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import relationships  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestRelationships(unittest.TestCase):
    def test_material_cluster_is_returned_grouped(self):
        """IS 456 cites cement, aggregate and reinforcement standards."""
        result = relationships.related_to("IS 456:2000")
        self.assertTrue(result["researched"])

        numbers = {
            item["number"]
            for group in result["depends_on"]
            for item in group["standards"]
        }
        for expected in ("IS 269:2015", "IS 1786:2008", "IS 383"):
            self.assertIn(expected, numbers)

        headings = [g["heading"] for g in result["depends_on"]]
        self.assertIn("Material specifications", headings)

    def test_cable_cluster_separates_materials_from_test_methods(self):
        """IS 694 depends on conductor/insulation specs and a test series.

        Grouping matters: a procurement officer needs to know which of these
        specifies the goods and which specifies how to prove conformance.
        """
        result = relationships.related_to("IS 694:2010")
        by_type = {g["type"]: g for g in result["depends_on"]}

        self.assertIn("material_spec", by_type)
        self.assertIn("test_method", by_type)
        self.assertEqual(
            {s["number"] for s in by_type["test_method"]["standards"]}, {"IS 10810"}
        )

    def test_citations_outside_the_corpus_are_shown_and_flagged(self):
        """Hiding them would silently truncate the cluster.

        IS 8130 and IS 5831 are real dependencies of IS 694 that the pilot
        corpus does not hold. Omitting them would produce exactly the
        incomplete citation this feature exists to prevent.
        """
        result = relationships.related_to("IS 694:2010")
        outside = [
            item
            for group in result["depends_on"]
            for item in group["standards"]
            if item["outside_corpus"]
        ]
        self.assertTrue(outside)
        for item in outside:
            self.assertTrue(item["title"], "an unlinkable entry still needs a title")

    def test_reverse_edges_are_derived(self):
        """IS 2062 is cited by several standards; it declares none itself."""
        result = relationships.related_to("IS 2062:2011")
        citing = {item["number"] for item in result["referenced_by"]}
        for expected in ("IS 456:2000", "IS 800:2007", "IS 808:1989"):
            self.assertIn(expected, citing)

    def test_unresearched_standard_says_so(self):
        """Absent data must not read as 'this standard has no references'."""
        result = relationships.related_to("IS 17048:2018")
        self.assertFalse(result["researched"])
        self.assertEqual(result["total"], 0)

    def test_is_number_spellings_resolve(self):
        canonical = relationships.related_to("IS 1489 (Part 1):2015")
        for spelling in ("is 1489 (part 1):2015", "IS 1489 (Part 1) : 2015"):
            with self.subTest(spelling=spelling):
                self.assertEqual(
                    relationships.related_to(spelling)["total"], canonical["total"]
                )

    def test_every_in_corpus_edge_resolves(self):
        """A link to a standard we do not hold must be flagged, not broken."""
        corpus = {
            s["number"]
            for s in json.loads(
                (_REPO_ROOT / "data" / "standards_corpus.json").read_text(encoding="utf-8")
            )
        }
        payload = json.loads(
            (_REPO_ROOT / "data" / "relationships" / "relationships.json").read_text(
                encoding="utf-8"
            )
        )
        for rel in payload["relationships"]:
            with self.subTest(source=rel["source"], target=rel["target"]):
                self.assertIn(rel["source"], corpus, "source must be in the corpus")
                if not rel.get("outside_corpus"):
                    self.assertIn(
                        rel["target"],
                        corpus,
                        "target is absent from the corpus but not flagged outside_corpus",
                    )

    def test_relation_types_are_documented(self):
        """Every type used must have an explanation the UI can show."""
        payload = json.loads(
            (_REPO_ROOT / "data" / "relationships" / "relationships.json").read_text(
                encoding="utf-8"
            )
        )
        documented = set(payload["_meta"]["relation_types"])
        used = {rel["type"] for rel in payload["relationships"]}
        self.assertTrue(used <= documented, f"undocumented types: {used - documented}")


if __name__ == "__main__":
    unittest.main()
