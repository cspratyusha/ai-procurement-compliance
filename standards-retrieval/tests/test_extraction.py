"""Tests for tender-document extraction.

The thing worth testing is not "did we get text out" but "did we get the
*right* text out". A tender is mostly boilerplate by volume — EMD, eligibility,
arbitration, signature blocks — so an extractor that returns everything
produces a query dominated by legal language and finds nothing useful.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extraction  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestExtraction(unittest.TestCase):
    def test_all_formats_find_the_specification_section(self):
        """PDF, DOCX and TXT must agree on what the document is about."""
        for name in ("sample_tender.pdf", "sample_tender.docx", "sample_tender.txt"):
            with self.subTest(name=name):
                result = extraction.extract(name, read(name))
                self.assertIn("SPECIFICATION", (result.matched_section or "").upper())
                query = result.query.lower()

                # Both products in the specification survive extraction.
                self.assertIn("cable", query)
                self.assertIn("cement", query)

                # The boilerplate that surrounds them does not.
                for noise in ("earnest money", "jurisdiction", "arbitration", "tender fee"):
                    self.assertNotIn(noise, query, f"{noise!r} leaked into the query")

    def test_wrapped_lines_do_not_lose_their_product(self):
        """Extracted text wraps mid-sentence; filtering must not split on that.

        "Item 3: Ordinary Portland Cement, 43 grade, for the civil works
        associated with" carries no technical marker on its own physical line.
        Filtering line-by-line dropped it, losing the cement entirely.
        """
        result = extraction.extract("sample_tender.pdf", read("sample_tender.pdf"))
        self.assertIn("cement", result.query.lower())

    def test_scanned_pdf_is_rejected_with_a_usable_message(self):
        """A scan has no text layer. Say so; do not search an empty string."""
        with self.assertRaises(extraction.ExtractionError) as ctx:
            extraction.extract("scanned_no_text.pdf", read("scanned_no_text.pdf"))
        message = str(ctx.exception).lower()
        self.assertIn("scan", message)
        self.assertIn("ocr", message)

    def test_unsupported_types_are_rejected(self):
        for name in ("notes.doc", "photo.jpg", "sheet.xlsx"):
            with self.subTest(name=name):
                with self.assertRaises(extraction.ExtractionError):
                    extraction.extract(name, b"x" * 200)

    def test_oversize_file_is_rejected_server_side(self):
        """The browser limit is a convenience; this one is the real guard."""
        oversize = b"x" * (extraction.MAX_FILE_BYTES + 1)
        with self.assertRaises(extraction.ExtractionError) as ctx:
            extraction.extract("big.pdf", oversize)
        self.assertIn("limit", str(ctx.exception).lower())

    def test_empty_file_is_rejected(self):
        with self.assertRaises(extraction.ExtractionError):
            extraction.extract("empty.txt", b"")

    def test_query_is_capped(self):
        """An embedding model truncates; cap before it does, on a word boundary."""
        long_spec = (
            "TECHNICAL SPECIFICATION\n\n"
            + "PVC insulated copper cable 1.5 sq mm 1100 V conforming to IS 694. " * 400
        )
        result = extraction.extract("long.txt", long_spec.encode("utf-8"))
        self.assertLessEqual(len(result.query), extraction.MAX_QUERY_CHARS)

    def test_document_without_a_heading_still_works_but_warns(self):
        """No recognised heading means we scanned everything — say so."""
        plain = (
            "Supply of PVC insulated copper conductor cable, 2.5 sq mm, "
            "1100 V grade, for internal wiring of the office building."
        )
        result = extraction.extract("plain.txt", plain.encode("utf-8"))
        self.assertIn("cable", result.query.lower())
        self.assertIsNone(result.matched_section)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
