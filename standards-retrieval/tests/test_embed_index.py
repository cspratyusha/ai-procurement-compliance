import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_loader import load_corpus, load_eval_set, get_standard_by_id
from indexing.embed_index import build_index, dense_search, load_index


def test_dense_retrieval_sanity():
    print("\n--- [Test 1] Building and Loading Index ---")
    corpus = load_corpus()
    build_index(corpus)
    
    index, ids = load_index()
    assert index.ntotal == len(corpus), f"Expected {len(corpus)} vectors in index, got {index.ntotal}"
    assert len(ids) == len(corpus), f"Expected {len(corpus)} IDs, got {len(ids)}"
    print(f"Index successfully verified: {index.ntotal} vectors.")

    eval_data = load_eval_set()
    print(f"\n--- [Test 2] Sanity Checking Eval Queries (Top-10 Recall) ---")
    
    # Pick 4 representative queries from eval_set
    sample_eval_cases = [eval_data[0], eval_data[4], eval_data[7], eval_data[12]]
    
    for i, case in enumerate(sample_eval_cases, 1):
        query = case["query"]
        target_id = case["correct_id"]
        target_std = get_standard_by_id(target_id)
        
        results = dense_search(query, top_k=10)
        retrieved_ids = [res[0] for res in results]
        
        print(f"\nQuery {i}: {query[:75]}...")
        print(f"  Target: [{target_id}] {target_std.number if target_std else ''}")
        print(f"  Top-3 hits: {[(r[0], f'{r[1]:.4f}') for r in results[:3]]}")
        
        assert target_id in retrieved_ids, (
            f"Target ID '{target_id}' was not found in top-10 dense search results for query: '{query}'"
        )
        rank = retrieved_ids.index(target_id) + 1
        print(f"  --> Target found at Rank #{rank} (Cosine Score: {results[rank-1][1]:.4f}) [PASS]")

    print(f"\n--- [Test 3] Baseline Behavior on Near-Duplicate 'Hard Case' Pairs ---")
    # Near-duplicate Pair:
    # IS-ELEC-001: Single-Core Fixed Conduit Wiring
    # IS-ELEC-002: Flexible Multi-Strand Panel Wiring
    hard_query = "Multi-strand flexible copper connecting wire for industrial motor control centers and automation panel switchgear wiring"
    expected_id = "IS-ELEC-002"
    confounder_id = "IS-ELEC-001"

    results = dense_search(hard_query, top_k=5)
    retrieved_ids = [r[0] for r in results]
    
    rank_expected = retrieved_ids.index(expected_id) + 1 if expected_id in retrieved_ids else -1
    rank_confounder = retrieved_ids.index(confounder_id) + 1 if confounder_id in retrieved_ids else -1

    print(f"Hard Query: '{hard_query}'")
    print(f"  Expected Target: {expected_id} (Rank #{rank_expected})")
    print(f"  Similar Confounder: {confounder_id} (Rank #{rank_confounder})")
    print("  Top Results:")
    for rank, (std_id, score) in enumerate(results, 1):
        std = get_standard_by_id(std_id)
        print(f"    Rank #{rank}: [{std_id}] {std.number} - Score: {score:.4f}")

    if rank_expected == 1:
        print("  Observation: Dense search alone ranked the target #1 on this case.")
    else:
        print(f"  Observation: Dense search placed target at #{rank_expected} vs confounder at #{rank_confounder}. "
              "This demonstrates semantic overlap and validates the need for Stage D (Cross-Encoder / LTR).")

    assert expected_id in retrieved_ids, f"Expected {expected_id} in top-5 retrieved results"
    print("\nAll dense retrieval sanity checks passed successfully!")


if __name__ == "__main__":
    test_dense_retrieval_sanity()
