"""POST /simulate: the what-if comparison is two real searches and their diff."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)


def test_diff_is_consistent_with_both_result_lists():
    resp = client.post("/simulate", json={
        "query": "PVC insulated copper cable for indoor wiring",
        "conditions": ["high voltage 11 kV", "armoured for underground burial"],
        "top_k": 10,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    base = {r["number"] for r in data["base"]}
    scenario = {r["number"] for r in data["scenario"]}
    assert {r["number"] for r in data["added"]} == scenario - base
    assert {r["number"] for r in data["removed"]} == base - scenario
    assert data["unchanged"] + len(data["moved"]) + len(data["added"]) == len(data["scenario"])
    assert data["scenario_query"].endswith("armoured for underground burial")


def test_every_standard_in_the_answer_is_in_the_corpus():
    numbers = {s.number for s in main.load_corpus()}
    data = client.post("/simulate", json={"query": "cement", "conditions": ["marine exposure"]}).json()
    for row in data["base"] + data["scenario"]:
        assert row["number"] in numbers


def test_needs_a_query_and_a_condition():
    assert client.post("/simulate", json={"query": "", "conditions": ["x"]}).status_code == 400
    assert client.post("/simulate", json={"query": "cement", "conditions": ["  "]}).status_code == 400
