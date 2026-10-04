"""Accuracy regression guard for the corpus the app actually serves.

The rest of the suite runs against the default corpus, because that is what
the committed indexes and the LightGBM model were built against. But the
deployed service runs `STANDARDS_CORPUS=full` over 31,372 records, and
nothing measured that in CI: the Recall@5 of 0.9958 quoted in the README and
in MODEL_AND_EVALUATION.md was a one-off measurement that no test would have
noticed regressing.

This module closes that gap. It is skipped unless the full corpus and its
index are present, so a fresh clone without the scraped data still gets a
green suite rather than a spurious failure.

The thresholds are deliberately set below the measured values, not at them.
They exist to catch a real regression, not to freeze a number that moves a
little whenever the corpus is rebuilt.
"""

import json
import os
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_REPO = _ROOT.parent
_EVAL = _REPO / "data" / "eval_set_full.json"
_CORPUS = _REPO / "data" / "standards_corpus_full.json"

# A hit is the labelled standard, number and part, in any edition. Labels name
# one edition, but the corpus now holds several editions of thousands of
# standards, and which edition to cite is decided by the supersession rule
# (the edition in force ranks first, and a superseded one names it), which
# has its own tests. Scoring editions here would count the engine wrong for
# returning IS 2167:2025 when the label says IS 2167:2019.
#
# Measured on the 236 held-out queries at 31,372 records (after 9,524 of BIS's
# current standards were added): same standard P@1 0.835, Recall@5 0.941;
# exact edition 0.826 / 0.928; same series 0.881 / 0.962. At 21,848 records the
# exact-edition figures were 0.9153 / 0.9873: the queries are written from the
# standards' titles, and the added records put more near-identical parts and
# editions beside each label. On realistic product queries the same change
# left accuracy unchanged (see PROGRESS.md). At 31,349 records, after the
# pilot's invented editions were dropped and its written text replaced with
# the standards' own: same standard P@1 0.826, Recall@5 0.945 (the pilot's
# keyword-rich summaries had been carrying a few labels). The floors sit clear of the
# measurement, so a rebuild's normal variation passes and a real regression
# does not.
_MIN_RECALL_AT_5 = 0.92
_MIN_P_AT_1 = 0.78


def _standard(number):
    """'IS 694 (Part 2):2016' -> 'IS 694 (PART 2)': the standard, any edition."""
    return re.sub(r"\s*:\s*\d{4}.*$", "", " ".join((number or "").upper().split()))

# Keep the default run quick; the full 236 queries take several minutes.
# Set FULL_EVAL_QUERIES=0 to run all of them.
_SAMPLE = int(os.environ.get("FULL_EVAL_QUERIES", "60"))


pytestmark = pytest.mark.skipif(
    not (_EVAL.exists() and _CORPUS.exists()),
    reason="full corpus or its eval set is not present in this checkout",
)


@pytest.fixture(scope="module")
def full_corpus_client():
    """A TestClient bound to the full corpus, built in isolation.

    The session-wide fixture in conftest pins the default corpus. This test
    is the one place that deliberately does otherwise, so it sets the
    variable itself and reimports the modules that read it at import time.
    """
    import importlib
    import sys

    previous = os.environ.get("STANDARDS_CORPUS")
    os.environ["STANDARDS_CORPUS"] = "full"

    for name in [m for m in list(sys.modules)
                 if m.split(".")[0] in {"main", "data_loader", "retrieval",
                                        "indexing", "ltr"}]:
        sys.modules.pop(name, None)

    try:
        from fastapi.testclient import TestClient
        main = importlib.import_module("main")
        with TestClient(main.app) as client:
            health = client.get("/health").json()
            if health.get("corpus_size", 0) < 5000:
                pytest.skip(
                    f"full corpus index not built: /health reports "
                    f"{health.get('corpus_size')} standards"
                )
            yield client
    finally:
        if previous is None:
            os.environ.pop("STANDARDS_CORPUS", None)
        else:
            os.environ["STANDARDS_CORPUS"] = previous
        for name in [m for m in list(sys.modules)
                     if m.split(".")[0] in {"main", "data_loader", "retrieval",
                                            "indexing", "ltr"}]:
            sys.modules.pop(name, None)


def _queries():
    items = json.loads(_EVAL.read_text(encoding="utf-8"))
    if _SAMPLE and _SAMPLE < len(items):
        # Evenly spaced rather than the first N, so every sector is sampled.
        step = len(items) / float(_SAMPLE)
        return [items[int(i * step)] for i in range(_SAMPLE)]
    return items


def test_recall_at_5_on_the_served_corpus(full_corpus_client):
    """The right standard must be in the top five for nearly every query."""
    items = _queries()
    hits = 0
    first = 0
    misses = []

    for item in items:
        resp = full_corpus_client.post(
            "/retrieve", json={"query": item["query"], "top_k": 5})
        assert resp.status_code == 200, resp.text
        numbers = [_standard(r["number"]) for r in resp.json()["results"]]
        wanted = _standard(item["correct_number"])
        if wanted in numbers[:5]:
            hits += 1
            if numbers and numbers[0] == wanted:
                first += 1
        else:
            misses.append((item["query"][:60], item["correct_number"], numbers[:3]))

    recall = hits / len(items)
    p_at_1 = first / len(items)

    report = "\n".join(
        f"    {q!r} wanted {num}, got {got}" for q, num, got in misses[:8])
    assert recall >= _MIN_RECALL_AT_5, (
        f"Recall@5 fell to {recall:.4f} over {len(items)} queries "
        f"(floor {_MIN_RECALL_AT_5}). First misses:\n{report}"
    )
    assert p_at_1 >= _MIN_P_AT_1, (
        f"P@1 fell to {p_at_1:.4f} over {len(items)} queries "
        f"(floor {_MIN_P_AT_1})."
    )
    print(f"\n  Recall@5 {recall:.4f}, P@1 {p_at_1:.4f} "
          f"over {len(items)} held-out queries at full corpus size.")


def test_out_of_scope_query_is_declined_on_the_served_corpus(full_corpus_client):
    """The confidence gate must still decline what no standard covers, at scale.

    This is the behaviour the product is sold on, and it is the one most
    likely to erode quietly as the corpus grows: with 21,848 standards there
    is always some text that looks vaguely close.

    These used to be "laptop computer" and "mobile phone charger". At full size
    that premise is false: BIS covers IT equipment (IS 13252, in the corpus),
    so declining a laptop as out of scope would train the gate to refuse a
    regulated product. The queries are now requests no Indian Standard
    specifies, the borderline ones from eval/calibrate_confidence.py included.

    "hotel booking for official travel" was one, until BIS published IS
    19384:2025 on online travel agency services (read from its portal in
    October 2026): a related standard now exists, and "uncertain" is the
    honest verdict for it.
    """
    for query in ["group health insurance for employees",
                  "legal advice on a contract dispute",
                  "catering for a staff canteen",       # highest-scoring out-of-scope
                  "mobile app development"]:
        resp = full_corpus_client.post(
            "/retrieve", json={"query": query, "top_k": 5})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("confidence") == "none", (
            f"Out-of-scope query {query!r} returned confidence "
            f"{data.get('confidence')!r}; it must be 'none' so the interface "
            f"renders no recommendations."
        )


def test_unmatched_wording_never_yields_a_confident_recommendation(full_corpus_client):
    """A covered product in words no standard uses must not get a wrong 'strong'.

    "Laptop" appears in no title. Before the everyday-word mapping retrieval
    surfaced a drawing-office straightedge; with the catalogue expanded from
    BIS's record it surfaces office-equipment measurement methods, held on
    their title only. Whatever the verdict, the engine must not present that as
    a confident recommendation, and a match on a title alone never is.
    """
    resp = full_corpus_client.post(
        "/retrieve", json={"query": "laptop computer for office use", "top_k": 5})
    assert resp.status_code == 200, resp.text
    assert resp.json().get("confidence") != "strong"


def test_a_match_on_a_title_alone_is_never_strong(full_corpus_client):
    """A record with no scope text cannot confirm what the standard covers."""
    resp = full_corpus_client.post(
        "/retrieve", json={"query": "jute bags for packing 50 kg foodgrains", "top_k": 5})
    data = resp.json()
    if data["results"] and not data["results"][0]["scope"]:
        assert data["confidence"] != "strong"
        assert "title" in data["confidence_reason"]


def test_vague_in_scope_wording_is_uncertain_not_declined(full_corpus_client):
    """Short real-world phrasing of a covered product must not be told it is out of scope."""
    for query in ["bricks for wall construction", "cotton bedsheet"]:
        resp = full_corpus_client.post(
            "/retrieve", json={"query": query, "top_k": 5})
        assert resp.status_code == 200, resp.text
        assert resp.json().get("confidence") != "none", (
            f"{query!r} names a product the catalogue covers; 'none' would tell the "
            f"officer it is outside the catalogue."
        )


def test_the_product_specification_ranks_above_its_test_methods(full_corpus_client):
    """A buyer naming goods needs the goods' standard first; test methods are allied standards.

    "ceramic floor tiles" once put a dozen parts of IS 13630 (methods of test)
    above IS 15622, the tiles, and pushed IS 15622 out of scoring altogether.
    """
    for query, expected, within in [("ceramic floor tiles", "IS 15622", 3),
                                    ("stainless steel kitchen sink", "IS 13983", 1)]:
        resp = full_corpus_client.post("/retrieve", json={"query": query, "top_k": 5})
        numbers = [r["number"] for r in resp.json()["results"]]
        assert any(n.startswith(expected) for n in numbers[:within]), f"{query!r}: {numbers}"
    # Asked about testing, the test methods are the answer and are not demoted.
    resp = full_corpus_client.post("/retrieve", json={"query": "methods of test for ceramic tiles", "top_k": 5})
    assert resp.json()["results"][0]["number"].startswith("IS 13630")


def test_in_scope_queries_are_answered_on_the_served_corpus(full_corpus_client):
    """Guard against the gate becoming so strict it declines real work."""
    cases = [
        ("PVC insulated copper cable for indoor panel wiring", "IS 694"),
        ("hot rolled structural steel for building frames", "IS 2062"),
    ]
    for query, expected_prefix in cases:
        resp = full_corpus_client.post(
            "/retrieve", json={"query": query, "top_k": 5})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("confidence") == "strong", (
            f"In-scope query {query!r} returned confidence "
            f"{data.get('confidence')!r}, expected 'strong'."
        )
        numbers = [r["number"] for r in data["results"]]
        assert any(n.startswith(expected_prefix) for n in numbers), (
            f"Expected a {expected_prefix} standard for {query!r}, got {numbers}"
        )
