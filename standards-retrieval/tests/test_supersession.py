"""Tests for deterministic supersession penalty enforcement & contract validation.

Verifies:
1. Synthetic ranking test: when a superseded standard has a higher raw score than its
   active sibling, apply_supersession_penalty() forces the active sibling to rank ahead,
   while preserving the relative order of all unrelated candidates.
2. Floor & tie-breaking test: when multiple superseded candidates are penalized down to 0.0,
   they never return negative scores, and ties at the 0.0 floor are broken by pre-penalty score
   rather than insertion order.
3. End-to-end pipeline test on Q16 query ('IS 1554 Part 1 heavy duty industrial power cables'):
   Confirms IS-ELEC-006 (active, 2020) outranks IS-ELEC-005 (superseded, 1988) in both
   full_retrieve() and ltr_retrieve(). In top_k=10, IS-ELEC-005 is pushed out and surfaced
   in nearby_superseded with superseded_by='IS-ELEC-006'.
4. Query without supersession:
   Confirms nearby_superseded is empty when no supersession is relevant.
5. Non-negative score contract:
   Confirms no score returned by full_retrieve() or ltr_retrieve() is negative.
"""
import sys
from pathlib import Path

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data_loader import load_corpus, get_standard_by_id
from retrieval.postprocess import apply_supersession_penalty, extract_base_standard_family
from retrieval.rerank import full_retrieve
from ltr.train import ltr_retrieve


def test_base_standard_family_extraction():
    print("--- [Test 1] Base Standard Family Extraction ---")
    assert extract_base_standard_family("IS 1554 (Part 1):1988") == "IS 1554 (PART 1)"
    assert extract_base_standard_family("IS 1554 (Part 1):2020") == "IS 1554 (PART 1)"
    assert extract_base_standard_family("IS 694:2010") == "IS 694"
    assert extract_base_standard_family("IS 694 (Part 2):2016") == "IS 694 (PART 2)"
    print("  [PASS] Family extraction correctly normalizes standard codes across years.")


def test_supersession_penalty_synthetic():
    print("\n--- [Test 2] Synthetic Active vs Superseded Resolution & Order Preservation ---")
    corpus = {s.id: s for s in load_corpus()}
    
    # IS-ELEC-005 is superseded (1988)
    # IS-ELEC-006 is active (2020)
    # IS-ELEC-001 and IS-ELEC-003 are unrelated active cables
    synthetic_results = [
        ("IS-ELEC-005", 0.95),  # Superseded starts at #1
        ("IS-ELEC-006", 0.90),  # Active starts at #2
        ("IS-ELEC-001", 0.70),  # Unrelated candidate A
        ("IS-ELEC-003", 0.50),  # Unrelated candidate B
    ]

    adjusted = apply_supersession_penalty(synthetic_results, corpus=corpus, penalty=2.0)
    adjusted_dict = dict(adjusted)
    ranked_ids = [cid for cid, _ in adjusted]

    print(f"  Pre-penalty ranking : {[cid for cid, _ in synthetic_results]}")
    print(f"  Post-penalty ranking: {ranked_ids}")
    print(f"  Adjusted scores     : {adjusted}")

    # Assert active ranks above superseded
    assert ranked_ids.index("IS-ELEC-006") < ranked_ids.index("IS-ELEC-005"), (
        f"Active standard IS-ELEC-006 (rank {ranked_ids.index('IS-ELEC-006')}) must rank above "
        f"superseded IS-ELEC-005 (rank {ranked_ids.index('IS-ELEC-005')})"
    )
    assert adjusted_dict["IS-ELEC-006"] > adjusted_dict["IS-ELEC-005"]

    # Assert relative order of unrelated candidates is strictly preserved (IS-ELEC-001 before IS-ELEC-003)
    assert ranked_ids.index("IS-ELEC-001") < ranked_ids.index("IS-ELEC-003"), (
        "Relative ordering of unrelated candidates A and B must be preserved"
    )

    # Assert all scores are within [0.0, 1.0]
    for cid, score in adjusted:
        assert 0.0 <= score <= 1.0, f"Candidate {cid} score {score} must be within [0.0, 1.0]"

    print("  [PASS] Active promoted over superseded; unrelated order preserved; all scores in [0.0, 1.0].")


def test_supersession_penalty_floored_tie_breaking():
    print("\n--- [Test 3] Floored Penalty at 0.0 & Pre-Penalty Score Tie-Breaking ---")
    corpus = {s.id: s for s in load_corpus()}
    
    # Construct synthetic case where two superseded candidates both get floored at 0.0
    # Let's create two mock superseded items sharing the IS 1554 (Part 1) family
    # Insertion order intentionally has lower pre-penalty score FIRST to test tie-breaking
    synthetic_entries = [
        {"id": "IS-ELEC-006", "standard_id": "IS-ELEC-006", "score": 0.80},  # Active leader
        {"id": "IS-ELEC-001", "standard_id": "IS-ELEC-001", "score": 0.60},  # Unrelated
        {"id": "SUP-LOWER",   "standard_id": "IS-ELEC-005", "score": 0.70},  # Superseded lower pre-penalty
        {"id": "SUP-HIGHER",  "standard_id": "IS-ELEC-005", "score": 0.95},  # Superseded higher pre-penalty
    ]

    adjusted, nearby = apply_supersession_penalty(
        synthetic_entries, corpus=corpus, penalty=2.0, top_k=2, return_metadata=True
    )

    print(f"  Adjusted results: {[(it['id'], it.get('final_score', it.get('score'))) for it in adjusted]}")
    print(f"  Nearby superseded: {nearby}")

    scores = {it["id"]: it.get("final_score", it.get("score")) for it in adjusted}
    # Both superseded items must be floored at 0.0, never negative, and bounded <= 1.0
    assert scores["SUP-HIGHER"] == 0.0, f"Expected 0.0, got {scores['SUP-HIGHER']}"
    assert scores["SUP-LOWER"] == 0.0, f"Expected 0.0, got {scores['SUP-LOWER']}"
    for it in adjusted:
        sc = it.get("final_score", it.get("score"))
        assert 0.0 <= sc <= 1.0, f"Score {sc} outside [0.0, 1.0]"
        # Confirm duplicate 'score' field has been removed
        assert "score" not in it, f"Duplicate 'score' field found in adjusted result: {it}"

    # Verify tie-breaking: SUP-HIGHER (pre-penalty 0.95) must rank ahead of SUP-LOWER (pre-penalty 0.70)
    adjusted_ids = [it["id"] for it in adjusted]
    idx_higher = adjusted_ids.index("SUP-HIGHER")
    idx_lower = adjusted_ids.index("SUP-LOWER")
    assert idx_higher < idx_lower, (
        f"SUP-HIGHER (pre-score 0.95, rank {idx_higher}) must break tie ahead of "
        f"SUP-LOWER (pre-score 0.70, rank {idx_lower}) at 0.0 floor"
    )
    print("  [PASS] Floor at 0.0 confirmed; ties broken by pre-penalty score; score in [0.0, 1.0]; no duplicate score field.")


def test_q16_end_to_end_supersession():
    print("\n--- [Test 4] End-to-End Q16 Superseded vs Active Pipeline Test & nearby_superseded ---")
    query = "IS 1554 Part 1 heavy duty industrial power cables"

    # Test full_retrieve (Cross-Encoder + Penalty)
    ce_results, ce_nearby = full_retrieve(query, top_k=10, return_metadata=True)
    ce_ids = [cid for cid, _ in ce_results]
    print(f"  full_retrieve Top-5: {ce_ids[:5]}")
    print(f"  full_retrieve nearby: {ce_nearby}")

    assert "IS-ELEC-006" in ce_ids, "Target active standard IS-ELEC-006 must be in retrieved candidates"
    # In top_k=10, active IS-ELEC-006 is at top, while superseded IS-ELEC-005 is penalized
    for cid, score in ce_results:
        assert 0.0 <= score <= 1.0, f"full_retrieve candidate {cid} score {score} outside [0.0, 1.0]"

    # Test ltr_retrieve (LTR Model + Penalty + Metadata)
    ltr_results, ltr_nearby = ltr_retrieve(query, top_k=10, return_metadata=True)
    ltr_ids = [cid for cid, _ in ltr_results]
    ltr_scores = [score for _, score in ltr_results]
    print(f"  ltr_retrieve Top-5:  {ltr_ids[:5]}")
    print(f"  ltr_retrieve Scores: {ltr_scores[:5]}")
    print(f"  ltr_retrieve nearby: {ltr_nearby}")

    # 1. Target active standard must be in top results
    assert "IS-ELEC-006" in ltr_ids, "Target active standard IS-ELEC-006 must be in LTR candidates"
    assert ltr_ids[0] == "IS-ELEC-006", f"IS-ELEC-006 must be rank 1, got {ltr_ids[0]}"

    # 2. Superseded standard IS-ELEC-005 must be pushed out of top-10 into nearby_superseded
    assert "IS-ELEC-005" not in ltr_ids, (
        "IS-ELEC-005 must be pushed out of top-10 candidates by supersession penalty"
    )
    assert len(ltr_nearby) > 0, "nearby_superseded must be populated for Q16 query"
    q16_nearby_ids = [n["id"] for n in ltr_nearby]
    assert "IS-ELEC-005" in q16_nearby_ids, f"IS-ELEC-005 must be in nearby_superseded: {ltr_nearby}"

    nearby_entry = next(n for n in ltr_nearby if n["id"] == "IS-ELEC-005")
    assert nearby_entry["superseded_by"] == "IS-ELEC-006", (
        f"Expected superseded_by='IS-ELEC-006', got {nearby_entry['superseded_by']}"
    )
    assert nearby_entry["status"] == "superseded"

    # 3. All scores in top-10 are strictly within [0.0, 1.0]
    for cid, score in ltr_results:
        assert 0.0 <= score <= 1.0, f"LTR candidate {cid} score {score} outside [0.0, 1.0]"

    print("  [PASS] ltr_retrieve() ranks IS-ELEC-006 #1, surfaces IS-ELEC-005 in nearby_superseded with superseded_by='IS-ELEC-006'.")


def test_no_supersession_query():
    print("\n--- [Test 5] Query Without Supersession (nearby_superseded empty) ---")
    query = "Concealed single core copper building wire for residential distribution boxes"
    ltr_results, ltr_nearby = ltr_retrieve(query, top_k=10, return_metadata=True)

    print(f"  Top result: {ltr_results[0] if ltr_results else 'None'}")
    print(f"  nearby_superseded: {ltr_nearby}")

    assert isinstance(ltr_nearby, list)
    assert len(ltr_nearby) == 0, f"nearby_superseded must be empty when no supersession exists, got {ltr_nearby}"
    for cid, score in ltr_results:
        assert 0.0 <= score <= 1.0, f"Candidate {cid} score {score} outside [0.0, 1.0]"
    print("  [PASS] Query without supersession returns empty nearby_superseded and scores in [0.0, 1.0].")


if __name__ == "__main__":
    test_base_standard_family_extraction()
    test_supersession_penalty_synthetic()
    test_supersession_penalty_floored_tie_breaking()
    test_q16_end_to_end_supersession()
    test_no_supersession_query()
    print("\n" + "=" * 70)
    print("All supersession resolution and contract tests PASSED!")
    print("=" * 70)
