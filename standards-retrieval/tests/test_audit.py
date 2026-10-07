"""Tests for tender-citation auditing and bill-of-quantities splitting.

Both back screens that used to simulate their work, the audit page ran a
1.8-second timer over five hardcoded findings, and the BOQ page showed a
worked example. The assertions here are mostly about restraint: what the
audit refuses to claim, and what the splitter refuses to guess.
"""
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import audit as audit_module
import extraction


class TestCitationDetection(unittest.TestCase):
    """Finding the IS numbers a document cites."""

    def test_finds_the_common_spellings(self):
        """A citation this misses is a citation that goes unchecked."""
        text = (
            "Cables per IS 694:2010. Cement per IS:269-2015. "
            "Concrete per IS 456. Cable part per IS 1554 (Part 1):1988."
        )
        found = {c["cited"].upper() for c in audit_module.find_citations(text)}

        self.assertIn("IS 694:2010", found)
        self.assertIn("IS 269:2015", found)
        self.assertIn("IS 456", found)
        self.assertIn("IS 1554 (PART 1):1988", found)

    def test_repeated_citation_is_one_finding_with_a_count(self):
        text = "IS 694:2010 applies. See IS 694:2010. Also IS 694:2010."
        citations = audit_module.find_citations(text)

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["occurrences"], 3)

    def test_no_citations_is_empty_not_an_error(self):
        self.assertEqual(audit_module.find_citations("A tender with no standards named."), [])
        self.assertEqual(audit_module.find_citations(""), [])

    def test_context_is_captured_for_location(self):
        """A finding has to be findable in the officer's own document."""
        text = "Clause 4.2: All cables shall conform to IS 694:2010 for working voltages."
        citation = audit_module.find_citations(text)[0]

        self.assertIn("cables shall conform", citation["context"])
        # Whitespace collapsed: PDF extraction wraps mid-clause.
        self.assertNotIn("\n", citation["context"])


class TestAuditFindings(unittest.TestCase):
    """Checking citations against the corpus."""

    def test_superseded_citation_names_its_replacement(self):
        result = audit_module.audit_text("Cement shall conform to IS 269:1989.")
        finding = next(f for f in result["findings"] if f["cited"] == "IS 269:1989")

        self.assertEqual(finding["severity"], "critical")
        self.assertEqual(finding["kind"], "superseded")
        self.assertTrue(finding["replacement"])
        self.assertIn(finding["replacement"], finding["action"])

    def test_undated_citation_is_advisory_not_a_defect(self):
        """An edition-less citation is ambiguous, not wrong.

        Uses IS 694, which is in the pinned test corpus: an undated citation
        can only resolve to an edition when the family is actually held, and
        a citation outside the corpus is correctly reported as unknown
        instead. Naming a standard the corpus does not have would make this
        test assert the wrong branch.
        """
        result = audit_module.audit_text("Cables as per IS 694, general purpose.")
        finding = next(f for f in result["findings"] if f["kind"] == "undated")

        self.assertEqual(finding["severity"], "info")
        # The active edition is named so the ambiguity can be closed.
        self.assertTrue(finding["replacement"])

    def test_undated_citation_outside_the_corpus_is_unknown(self):
        """The other branch: no family held, so no edition can be named."""
        result = audit_module.audit_text("Concrete work as per IS 99998.")
        finding = next(f for f in result["findings"] if f["cited"] == "IS 99998")

        self.assertEqual(finding["kind"], "unknown")
        self.assertIsNone(finding["replacement"])

    def test_unknown_standard_is_reported_as_coverage_not_defect(self):
        """A citation the corpus cannot check is our gap, not the tender's."""
        result = audit_module.audit_text("Steel per IS 99999:2020.")
        finding = next(f for f in result["findings"] if f["cited"] == "IS 99999:2020")

        self.assertEqual(finding["severity"], "info")
        self.assertEqual(finding["kind"], "unknown")
        self.assertIn("not a defect", finding["detail"])

    def test_critical_findings_always_name_a_replacement(self):
        """Critical asserts the fix is known, so the fix must be present."""
        result = audit_module.audit_text(
            "IS 269:1989 and IS 694:2010 and IS 456 and IS 99999:2020 apply."
        )
        for finding in result["findings"]:
            if finding["severity"] == "critical":
                self.assertTrue(finding["replacement"])

    def test_no_citations_is_not_a_pass(self):
        """The load-bearing case: silence must not read as a clean bill."""
        result = audit_module.audit_text("A tender describing goods but naming no standards.")

        self.assertEqual(result["citations_found"], 0)
        self.assertEqual(result["findings"], [])
        self.assertIn("no findings is not a pass", result["note"])

    def test_note_states_what_was_not_checked(self):
        result = audit_module.audit_text("IS 694:2010 applies.")
        self.assertIn("right standards", result["note"])

    def test_findings_ordered_by_severity(self):
        result = audit_module.audit_text(
            "IS 99999:2020, IS 269:1989, IS 456 and IS 694:2010 all apply."
        )
        rank = {"critical": 0, "minor": 1, "info": 2}
        severities = [rank[f["severity"]] for f in result["findings"]]
        self.assertEqual(severities, sorted(severities))

    def test_counts_are_internally_consistent(self):
        result = audit_module.audit_text(
            "IS 269:1989 and IS 694:2010 and IS 456 apply."
        )
        self.assertEqual(
            result["clean_citations"],
            result["citations_found"] - len(result["findings"]),
        )


class TestEditionsAndParts(unittest.TestCase):
    """Citations the demo tender makes, on the records the full corpus holds for them."""

    @classmethod
    def setUpClass(cls):
        from data.models import Standard

        def std(number, status="active", withdrawn=False, superseded_by=None):
            return Standard(id=number, number=number, title=f"Title of {number}", scope="", description="",
                            category="", version="", last_amended="", status=status,
                            withdrawn=withdrawn, superseded_by_number=superseded_by)

        cls.corpus = [
            std("IS 2062:2011", "superseded", withdrawn=True),
            std("IS 2062 (Part 1):2025"), std("IS 2062 (Part 2):2026"),
            std("IS 1239 (Part 1):2004"), std("IS 1239 (Part 2):2011"),
            std("IS 694:2010"),
        ]

    def audit(self, text):
        from unittest import mock
        with mock.patch.object(audit_module, "load_corpus", return_value=self.corpus):
            return {f["cited"]: f for f in audit_module.audit_text(text)["findings"]}

    def test_a_standard_withdrawn_into_parts_names_the_parts(self):
        """BIS withdrew IS 2062:2011 naming nothing; it is IS 2062 (Part 1):2025 and (Part 2):2026 now."""
        f = self.audit("Steel to IS 2062:2011.")["IS 2062:2011"]
        self.assertEqual(f["severity"], "critical")
        self.assertEqual(f["now_in_parts"], ["IS 2062 (Part 1):2025", "IS 2062 (Part 2):2026"])
        self.assertIn("now published in parts", f["detail"])
        self.assertIsNone(f["replacement"])            # BIS names none; a part is not asserted

    def test_a_standard_cited_without_its_part_is_not_called_unknown(self):
        f = self.audit("Galvanized tubes to IS 1239.")["IS 1239"]
        self.assertEqual(f["kind"], "no_part")
        self.assertEqual(f["now_in_parts"], ["IS 1239 (Part 1):2004", "IS 1239 (Part 2):2011"])
        self.assertNotIn("not in this corpus", f["detail"])

    def test_an_earlier_edition_not_held_is_superseded_by_the_one_in_force(self):
        f = self.audit("Cables to IS 694:1990.")["IS 694:1990"]
        self.assertEqual((f["severity"], f["kind"], f["replacement"]), ("critical", "superseded", "IS 694:2010"))

    def test_a_newer_edition_than_the_corpus_holds_stays_unknown(self):
        """The corpus may be behind BIS: a later year is not called superseded."""
        f = self.audit("Cables to IS 694:2030.")["IS 694:2030"]
        self.assertEqual(f["kind"], "unknown")


class TestLineItemSplitting(unittest.TestCase):
    """Splitting a bill of quantities into the goods it lists."""

    BOQ = (
        "SPECIFICATION\n"
        "Item 1: PVC insulated copper cable, single core, 1100 V. Quantity 4500 m.\n"
        "Item 2: Ordinary Portland Cement, 43 grade, in 50 kg bags. Quantity 820 bags.\n"
        "Item 3: Hot rolled structural steel plates. Quantity 12 tonnes.\n"
    )

    def test_splits_numbered_items(self):
        items = extraction.split_line_items(self.BOQ)
        self.assertEqual(len(items), 3)
        self.assertEqual([i["sr"] for i in items], [1, 2, 3])

    def test_item_numbering_is_stripped_from_the_query(self):
        """"Item 1: PVC cable" searches better as "PVC cable"."""
        items = extraction.split_line_items(self.BOQ)
        self.assertFalse(items[0]["query"].lower().startswith("item"))
        self.assertIn("PVC", items[0]["query"])

    def test_ordered_quantity_wins_over_packaging(self):
        """"in 50 kg bags. Quantity 820 bags" must yield 820 bags, not 50 kg."""
        items = extraction.split_line_items(self.BOQ)
        self.assertIn("820", items[1]["quantity"])

    def test_no_line_item_structure_returns_empty(self):
        """Empty means "not a BOQ", which the caller must not render as an empty BOQ."""
        self.assertEqual(
            extraction.split_line_items("A tender describing one product in prose."),
            [],
        )
        self.assertEqual(extraction.split_line_items(""), [])

    def test_bullet_and_numeric_markers_are_recognised(self):
        text = (
            "SPECIFICATION\n"
            "- PVC insulated copper cable for panel wiring\n"
            "- Ordinary Portland Cement 43 grade for civil works\n"
        )
        self.assertEqual(len(extraction.split_line_items(text)), 2)

    def test_item_limit_is_honoured(self):
        text = "SPEC\n" + "\n".join(
            f"Item {i}: Some described product number {i} for the works" for i in range(1, 40)
        )
        self.assertLessEqual(len(extraction.split_line_items(text, limit=10)), 10)


class TestEndpoints(unittest.TestCase):
    """The HTTP contracts the two screens consume."""

    def _upload(self, client, path, text, filename="tender.txt"):
        return client.post(
            path,
            files={"file": (filename, text.encode("utf-8"), "text/plain")},
        )

    def test_audit_endpoint_returns_findings(self):
        from main import app

        with TestClient(app) as client:
            res = self._upload(
                client, "/audit",
                "Clause 4: Cement shall conform to IS 269:1989 for the works.",
            )
            self.assertEqual(res.status_code, 200)
            body = res.json()

        self.assertGreaterEqual(body["citations_found"], 1)
        self.assertIn("note", body)
        self.assertTrue(any(f["kind"] == "superseded" for f in body["findings"]))

    def test_audit_of_a_document_with_no_citations(self):
        from main import app

        with TestClient(app) as client:
            res = self._upload(client, "/audit", "A tender naming no standards at all.")
            self.assertEqual(res.status_code, 200)
            body = res.json()

        self.assertEqual(body["citations_found"], 0)
        self.assertEqual(body["findings"], [])

    def test_boq_endpoint_searches_each_item_separately(self):
        """The whole point: item 2's cement must not lose to item 1's cable."""
        from main import app

        text = (
            "SPECIFICATION\n"
            "Item 1: PVC insulated copper cable, single core, 1100 V. Quantity 4500 m.\n"
            "Item 2: Ordinary Portland Cement, 43 grade, in bags. Quantity 820 bags.\n"
        )

        with TestClient(app) as client:
            res = self._upload(client, "/boq?top_k=3", text, filename="boq.txt")
            self.assertEqual(res.status_code, 200)
            body = res.json()

        self.assertTrue(body["is_boq"])
        self.assertEqual(body["item_count"], 2)

        # Each item got its own ranking, not a share of one flattened query.
        first = {r["number"] for r in body["items"][0]["results"]}
        second = {r["number"] for r in body["items"][1]["results"]}
        self.assertTrue(first)
        self.assertTrue(second)
        self.assertNotEqual(first, second)

    def test_boq_reports_a_non_boq_honestly(self):
        """is_boq: false is "not a BOQ", not "an empty BOQ"."""
        from main import app

        with TestClient(app) as client:
            res = self._upload(
                client, "/boq",
                "A tender describing a single product in continuous prose.",
            )
            self.assertEqual(res.status_code, 200)
            body = res.json()

        self.assertFalse(body["is_boq"])
        self.assertEqual(body["items"], [])

    def test_unreadable_file_is_422_not_500(self):
        from main import app

        with TestClient(app) as client:
            res = client.post(
                "/audit",
                files={"file": ("image.png", b"\x89PNG\r\n\x1a\n", "image/png")},
            )
        self.assertEqual(res.status_code, 422)


class TestUploadLimit(unittest.TestCase):
    def test_the_server_refuses_files_over_10_mb(self):
        """The browser checks too, but a client can send anything."""
        from main import app

        big = b"IS 694:2010 " * (10 * 1024 * 1024 // 12 + 10)
        with TestClient(app) as client:
            for route in ("/audit", "/boq", "/extract"):
                res = client.post(route, files={"file": ("big.txt", big, "text/plain")})
                self.assertEqual(res.status_code, 413, route)


class TestDependencyGaps(unittest.TestCase):
    """What the cited standards depend on that the tender leaves out."""

    def gaps(self, text):
        return {g["standard"].split(":")[0]: g for g in audit_module.audit_text(text)["dependency_gaps"]}

    def test_a_cited_standard_brings_its_dependencies(self):
        """IS 694 specifies its conductor by IS 8130 and its tests by IS 10810."""
        gaps = self.gaps("Cables shall conform to IS 694:2010.")
        self.assertIn("IS 8130", gaps)
        self.assertIn("IS 10810", gaps)
        self.assertEqual(gaps["IS 8130"]["required_by"], ["IS 694:2010"])
        self.assertTrue(gaps["IS 8130"]["evidence"])          # shown with why

    def test_what_the_tender_already_cites_is_not_a_gap(self):
        gaps = self.gaps("Cables to IS 694:2010, conductors to IS 8130, tested to IS 10810.")
        self.assertNotIn("IS 8130", gaps)
        self.assertNotIn("IS 10810", gaps)                    # the whole series covers its parts

    def test_parts_of_one_series_are_one_line(self):
        gaps = [g for g in audit_module.audit_text("Cables shall conform to IS 694:2010.")["dependency_gaps"]
                if g["standard"].startswith("IS 10810")]
        self.assertLessEqual(len(gaps), 1)

    def test_vocabularies_are_not_listed(self):
        for gap in audit_module.audit_text("Cables shall conform to IS 694:2010.")["dependency_gaps"]:
            self.assertNotRegex(gap["title"].lower(), "vocabulary|glossary|terminology")

    def test_no_citations_no_gaps(self):
        result = audit_module.audit_text("No standards are cited here.")
        self.assertEqual((result["dependency_gaps"], result["dependency_gaps_total"]), ([], 0))

    def test_a_passing_mention_is_not_a_dependency(self):
        dep = {"method": "extracted", "found_in": "body", "evidence": "steels for welded tubes (IS 10748 and IS 15647)"}
        self.assertFalse(audit_module._is_dependency(dep))
        dep["evidence"] = "The test shall be conducted as per IS 10810 (Part 58)."
        self.assertTrue(audit_module._is_dependency(dep))
        self.assertTrue(audit_module._is_dependency({"method": "extracted", "found_in": "references"}))


if __name__ == "__main__":
    unittest.main()
