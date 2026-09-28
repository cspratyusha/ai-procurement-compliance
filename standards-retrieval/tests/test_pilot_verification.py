"""data/build_full_corpus.py: the pilot's records are checked against BIS and the archive.

The pilot data named editions that do not exist (IS 8112:2018, when BIS merged
IS 8112 into IS 269:2015). Served, they ranked first for everyday searches and
made the real current editions look superseded. These tests hold the rule and
check the served corpus keeps to it.
"""

import json
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "data"))

from apply_bis_status import normalize as upper_key  # noqa: E402
from build_full_corpus import same_product, verify_pilot  # noqa: E402

_CORPUS = _REPO / "data" / "standards_corpus_full.json"
_BIS = _REPO / "data" / "amendments" / "bis_kys.json"
_CORRECTIONS = _REPO / "data" / "pilot_corrections.json"


def pilot(number, title, scope="This standard covers the product.", **extra):
    return {"number": number, "title": title, "scope": scope, "description": "Written for the pilot.",
            "category": "cement_building_materials", "version": "Sixth Revision", "last_amended": "2023-05-19",
            "status": "superseded", "superseded_by_number": "IS 1:2099", "keywords": ["pilot"],
            "sources": ["mock_corpus"], "verified": False, "provenance": "consolidated", **extra}


BIS_RAW = {
    "IS 269:2015": {"title": "Ordinary portland cement - Specification (Sixth Revision)", "page_id": 7},
    "IS 14257:2019": {"title": "Lead - Acid storage batteries for motor vehicles"},
}
SCOPE = ("This standard covers the requirements of the product, its materials, dimensions, "
         "workmanship and tests, as published.")
ARCHIVE = [
    {"number": "IS 12894:2002", "title": "Pulverized Fuel Ash-Lime Bricks", "scope": SCOPE,
     "category": "cement_building_materials", "provenance": "published_text_ocr", "source_url": "https://archive.org/x"},
]


class TestRule:
    def test_an_edition_nobody_lists_is_dropped(self):
        kept, dropped, _ = verify_pilot([pilot("IS 8112:2018", "OPC 43 grade")], [], BIS_RAW,
                                        {"IS 8112:2018": {"by": "IS 269:2015"}})
        assert kept == [] and dropped == ["IS 8112:2018"]

    def test_a_dropped_edition_must_be_explained(self):
        with pytest.raises(SystemExit, match="IS 8112:2018"):
            verify_pilot([pilot("IS 8112:2018", "OPC 43 grade")], [], BIS_RAW, {})

    def test_a_bis_listed_edition_keeps_its_summary_labelled_and_loses_what_was_written(self):
        [record], _, _ = verify_pilot(
            [pilot("IS 269:2015", "Ordinary Portland Cement (33, 43, and 53 Grades) - Unified Specification")],
            [], BIS_RAW, {})
        assert record["title"] == "Ordinary portland cement - Specification"
        assert record["title_source"] == "bis"
        assert record["provenance"] == "scope_written"
        assert record["version"] == "Sixth Revision"          # from BIS's own title
        assert record["description"] == "" and record["last_amended"] == ""
        assert record["status"] == "active" and record["superseded_by_number"] is None
        assert record["sources"] == ["bis.gov.in/knowyourstandards"]
        assert "mock" not in json.dumps(record["keywords"])

    def test_a_summary_of_a_different_product_is_not_kept(self):
        [record], _, _ = verify_pilot(
            [pilot("IS 14257:2019", "Flat three-core PVC insulated submersible pump cables")], [], BIS_RAW, {})
        assert record["provenance"] == "number_and_title_only" and record["scope"] == ""

    def test_the_published_scope_wins(self):
        [record], _, _ = verify_pilot([pilot("IS 12894:2002", "Fly ash bricks")], ARCHIVE, BIS_RAW, {})
        assert record["scope"] == SCOPE and record["provenance"] == "published_text_ocr"
        assert record["title"] == "Pulverized Fuel Ash-Lime Bricks" and record["title_source"] == "archive"
        assert record["sources"] == ["archive.org/gov.in.is"]

    def test_same_product(self):
        assert same_product("PVC Insulated Cables for Working Voltages up to 1100 V",
                            "Polyvinyl chloride insulated unsheathed and sheathed cables for working voltages")
        assert not same_product("Flat three-core PVC insulated submersible pump cables",
                                "Lead - Acid storage batteries for motor vehicles")


@pytest.fixture(scope="module")
def served():
    return json.loads(_CORPUS.read_text(encoding="utf-8"))


class TestServedCorpus:
    def test_no_pilot_record_or_written_description_is_served(self, served):
        assert not [r["number"] for r in served if r.get("provenance") in ("consolidated", "number_and_title_referenced")]
        assert not [r["number"] for r in served
                    if set(r.get("sources") or []) - {"archive.org/gov.in.is", "bis.gov.in/knowyourstandards"}]
        assert not [r["number"] for r in served if (r.get("description") or "").strip()]

    def test_every_edition_is_listed_by_bis_or_published_in_the_archive(self, served):
        bis = {upper_key(k) for k in json.loads(_BIS.read_text(encoding="utf-8"))["standards"]}
        unbacked = [r["number"] for r in served
                    if upper_key(r["number"]) not in bis and "archive.org/gov.in.is" not in (r.get("sources") or [])]
        assert unbacked == []

    def test_the_corrected_editions_are_gone_and_the_real_ones_current(self, served):
        by_number = {r["number"]: r for r in served}
        corrections = json.loads(_CORRECTIONS.read_text(encoding="utf-8"))["replaced"]
        assert not set(corrections) & set(by_number)
        for real in ("IS 12894:2002", "IS 8329:2000", "IS 2185 (Part 3):1984", "IS 14255:1995",
                     "IS 4926:2003", "IS 1554 (Part 1):1988"):
            assert by_number[real]["status"] == "active", real
        for wrong, fix in corrections.items():
            if fix["by"]:
                assert fix["by"] in by_number, f"{wrong} maps to {fix['by']}, which is not held"

    def test_every_query_label_points_at_its_standard(self, served):
        """Ids are positional, so a rebuild that drops records shifts them."""
        by_id = {r["id"]: r["number"] for r in served}
        for name in ("eval_set_full.json", "train_queries_full.json"):
            items = json.loads((_REPO / "data" / name).read_text(encoding="utf-8"))
            wrong = [(i["correct_id"], i["correct_number"]) for i in items
                     if by_id.get(i["correct_id"]) != i["correct_number"]]
            assert wrong == [], name

    def test_data_files_name_no_corrected_edition(self):
        corrections = json.loads(_CORRECTIONS.read_text(encoding="utf-8"))["replaced"]
        pattern = re.compile("|".join(re.escape(f'"{n}"') for n in corrections))
        rules = json.loads((_REPO / "data" / "certification" / "certification_rules.json").read_text(encoding="utf-8"))
        assert not pattern.search(json.dumps(rules["rules"]))
        for name in ("relationships/relationships.json", "eval_set_full.json", "train_queries_full.json"):
            text = (_REPO / "data" / name).read_text(encoding="utf-8")
            relevant = json.dumps(json.loads(text).get("relationships")) if name.startswith("relationships") else text
            assert not pattern.search(relevant), name
