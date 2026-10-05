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
        # The hand-read test series is there, and the conductor spec is not
        # mixed into the test methods. Parts of IS 10810 read from the text may
        # join it; that is the same series, correctly grouped.
        test_numbers = {s["number"] for s in by_type["test_method"]["standards"]}
        self.assertIn("IS 10810", test_numbers)
        self.assertNotIn("IS 8130", test_numbers)

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
            # Hand-read links carry a title. A link read from text to a standard
            # the corpus does not hold has no reliable title (guessing one from
            # OCR would invent it), so it must carry the passage instead.
            self.assertTrue(
                item["title"] or item.get("evidence"),
                "an unlinkable entry needs a title or the passage it was read from",
            )

    def test_reverse_edges_are_derived(self):
        """IS 2062 is cited by several standards; it declares none itself."""
        result = relationships.related_to("IS 2062:2011")
        citing = {item["number"] for item in result["referenced_by"]}
        for expected in ("IS 456:2000", "IS 800:2007", "IS 808:1989"):
            self.assertIn(expected, citing)

    def test_unresearched_standard_says_so(self):
        """Absent data must not read as 'this standard has no references'.

        IS 15530:2021 is held on its number and title only: the archive item
        filed under it is an amendment to IS 15532 (data/archive/misfiled.json),
        so its own text was never read, and nothing cites it. (IS 1734 (Part
        1):1983 was this example until the corpus held the edition 19 standards
        cite.)
        """
        result = relationships.related_to("IS 15530:2021")
        self.assertFalse(result["researched"])
        self.assertFalse(result["text_read"])
        self.assertEqual(result["total"], 0)

    def test_text_read_with_no_citations_is_not_unresearched(self):
        """Read and citing nothing is a finding; never read is not."""
        result = relationships.related_to("IS 10006:1981")
        self.assertTrue(result["researched"])
        self.assertTrue(result["text_read"])
        self.assertEqual(result["depends_on"], [])

    def test_extracted_links_carry_their_evidence(self):
        """Every automatically read link must be checkable by a person."""
        result = relationships.related_to("IS 456:2000")
        extracted = [s for g in result["depends_on"] for s in g["standards"] if s["method"] == "extracted"]
        self.assertGreater(len(extracted), 20)
        for item in extracted:
            self.assertTrue(item.get("evidence"), f"{item['number']} has no evidence passage")

    def test_curated_link_wins_over_the_extracted_one(self):
        """IS 694 -> IS 8130 is hand-read; the text also cites it. Show it once."""
        result = relationships.related_to("IS 694:2010")
        rows = [s for g in result["depends_on"] for s in g["standards"] if s["number"].startswith("IS 8130")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["method"], "curated")

    def test_popular_standards_cap_the_reverse_list_but_report_the_total(self):
        """IS 4905 (random sampling) is cited by over a thousand standards, now
        split between its 1968 edition and the 2015 one the corpus also holds."""
        result = relationships.related_to("IS 4905:1968")
        self.assertLessEqual(len(result["referenced_by"]), relationships.REFERENCED_BY_LIMIT)
        self.assertGreater(result["referenced_by_total"], relationships.REFERENCED_BY_LIMIT)
        both = result["referenced_by_total"] + relationships.related_to("IS 4905:2015")["referenced_by_total"]
        self.assertGreater(both, 1000)

    def test_is_number_spellings_resolve(self):
        canonical = relationships.related_to("IS 1489 (Part 1):2015")
        for spelling in ("is 1489 (part 1):2015", "IS 1489 (Part 1) : 2015"):
            with self.subTest(spelling=spelling):
                self.assertEqual(
                    relationships.related_to(spelling)["total"], canonical["total"]
                )

    def test_every_in_corpus_edge_resolves(self):
        """A link to a standard we do not hold must be flagged, not broken.

        Checked against the corpus the engine serves, not the pilot's.
        """
        corpus = {
            s["number"]
            for s in json.loads(
                (_REPO_ROOT / "data" / "standards_corpus_full.json").read_text(encoding="utf-8")
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

    def test_safety_standards_are_grouped_as_such(self):
        """A ceiling fan standard cites IS 302 (Part 1), the appliance safety standard."""
        result = relationships.related_to("IS 374:2019")
        by_type = {g["type"]: g for g in result["depends_on"]}
        self.assertIn("safety", by_type)
        self.assertEqual(by_type["safety"]["heading"], "Safety standards")
        self.assertTrue(any(s["number"].startswith("IS 302 (Part 1)") for s in by_type["safety"]["standards"]))

    def test_only_references_become_safety_standards(self):
        """A product named 'safety', or a safety glossary or test, keeps its own type."""
        def edge(title, rel_type):
            return {"number": title, "title": title, "type": rel_type, "note": None,
                    "outside_corpus": False, "method": "extracted"}

        edges = relationships._classified([
            edge("Safety of toys", "normative_reference"),
            edge("Fire safety of buildings (General): details of construction", "installation"),
            edge("Safety glass - Specification", "normative_reference"),
            edge("Specification for Industrial Safety Helmets", "normative_reference"),
            edge("Glossary of terms associated with fire safety", "terminology"),
            edge("Methods of test for safety evaluation of cosmetics", "test_method"),
        ], title_of=lambda n: None)
        self.assertEqual([e["type"] for e in edges], [
            "safety", "safety", "normative_reference", "normative_reference", "terminology", "test_method"])

    def test_classification_does_not_change_the_shared_edges(self):
        """Edges are loaded once and shared across requests; a request must not rewrite them."""
        relationships.related_to("IS 374:2019")
        relationships._load()
        stored = relationships._FORWARD[relationships._normalize("IS 374:2019")]
        self.assertFalse(any(e["type"] == "safety" for e in stored))

    def test_a_citation_outside_the_corpus_takes_its_title_from_bis(self):
        # IS 2112:2025 is on BIS's record but not in the catalogue.
        self.assertTrue(relationships._default_title_of("IS 2112:2025").lower().startswith("silver and silver alloys"))
        # A citation with no edition year reads as its newest edition's title.
        self.assertIn("Safety", relationships._default_title_of("IS 302 (Part 1)"))
        self.assertIsNone(relationships._default_title_of("IS 99999:2020"))

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
