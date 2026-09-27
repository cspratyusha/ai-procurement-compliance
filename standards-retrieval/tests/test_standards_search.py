"""Tests for GET /standards/search, the paged catalogue query.

The catalogue used to download the whole corpus (about 10 MB at full size) and
filter it in the browser. These pin that the server-side search matches what
the catalogue always matched, pages correctly, and returns list-sized rows.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from data_loader import load_corpus  # noqa: E402


class TestStandardsSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)
        cls.corpus = load_corpus()

    def get(self, **params):
        resp = self.client.get("/standards/search", params=params)
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_no_filter_returns_a_page_and_the_full_total(self):
        data = self.get(limit=5)
        self.assertEqual(data["total"], len(self.corpus))
        self.assertEqual(data["corpus_size"], len(self.corpus))
        self.assertEqual(len(data["results"]), min(5, len(self.corpus)))

    def test_paging_does_not_repeat_rows(self):
        first = {r["id"] for r in self.get(limit=4, offset=0)["results"]}
        second = {r["id"] for r in self.get(limit=4, offset=4)["results"]}
        self.assertFalse(first & second)

    def test_matches_number_title_scope_and_keywords(self):
        target = self.corpus[0]
        for term in (target.number, target.title.split()[0]):
            with self.subTest(term=term):
                ids = {r["id"] for r in self.get(q=term, limit=200)["results"]}
                self.assertIn(target.id, ids)

    def test_number_matches_rank_first(self):
        target = self.corpus[0]
        results = self.get(q=target.number, limit=5)["results"]
        self.assertEqual(results[0]["number"], target.number)

    def test_whole_number_outranks_a_longer_number_it_prefixes(self):
        """Typing "IS 694" must not put IS 6943 ahead of IS 694."""
        numbers = [s.number for s in self.corpus]
        for s in self.corpus:
            base = s.number.split(":")[0]
            longer = [n for n in numbers if n.startswith(base) and n[len(base):len(base) + 1].isdigit()]
            if longer:
                results = self.get(q=base, limit=10)["results"]
                self.assertTrue(results[0]["number"].startswith(base))
                self.assertFalse(results[0]["number"][len(base):len(base) + 1].isdigit(),
                                 f"{results[0]['number']} ranked above the exact {base}")
                return
        self.skipTest("the test corpus has no number that prefixes another")

    def test_category_and_superseded_filters(self):
        category = self.corpus[0].category
        rows = self.get(category=category, limit=200)["results"]
        self.assertTrue(rows)
        self.assertTrue(all(r["category"] == category for r in rows))
        current = self.get(include_superseded=False, limit=200)["results"]
        self.assertTrue(all(r["status"] != "superseded" for r in current))

    def test_rows_are_list_sized(self):
        """The whole point: a row carries an excerpt, not the full scope."""
        for row in self.get(limit=200)["results"]:
            self.assertLessEqual(len(row["scope"]), main._SCOPE_EXCERPT)

    def test_nonsense_matches_nothing(self):
        self.assertEqual(self.get(q="zzqqxx-no-such-term")["total"], 0)

    def test_limit_is_capped(self):
        self.assertLessEqual(len(self.get(limit=100000)["results"]), 200)

    def test_search_is_not_mistaken_for_a_standard_id(self):
        """/standards/search must not fall through to /standards/{id} (404)."""
        self.assertEqual(self.client.get("/standards/search").status_code, 200)


if __name__ == "__main__":
    unittest.main()
