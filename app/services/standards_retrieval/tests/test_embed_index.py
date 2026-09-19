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

    print(f"\n--- [Test 3] Baseline Behavior on Supersession 'Hard Case' Pair ---")
    # Real supersession pair in corpus:
    # std_017: IS 226:1975 (Structural Steel, Standard Quality) — superseded
    # std_001: IS 2062:2011 (Hot Rolled Structural Steel) — active successor
    hard_query = "structural steel standard quality for general construction purposes"
    active_id = "std_001"       # IS 2062:2011 — active successor
    superseded_id = "std_017"   # IS 226:1975 — superseded

    results = dense_search(hard_query, top_k=10)
    retrieved_ids = [r[0] for r in results]

    rank_active = retrieved_ids.index(active_id) + 1 if active_id in retrieved_ids else -1
    rank_superseded = retrieved_ids.index(superseded_id) + 1 if superseded_id in retrieved_ids else -1

    print(f"Hard Query: '{hard_query}'")
    print(f"  Active Standard: {active_id} (Rank #{rank_active})")
    print(f"  Superseded Standard: {superseded_id} (Rank #{rank_superseded})")
    print("  Top Results:")
    for rank, (std_id, score) in enumerate(results[:5], 1):
        std = get_standard_by_id(std_id)
        print(f"    Rank #{rank}: [{std_id}] {std.number if std else '?'} - Score: {score:.4f}")

    # Both standards should appear in top-10 for this query (they're semantically close)
    assert active_id in retrieved_ids or superseded_id in retrieved_ids, (
        f"Expected at least one of {active_id}/{superseded_id} in top-10 dense results"
    )

    if rank_active >= 1 and rank_superseded >= 1:
        if rank_active < rank_superseded:
            print("  Observation: Dense search correctly ranked active successor above superseded.")
        else:
            print(f"  Observation: Dense search placed superseded at #{rank_superseded} vs active at #{rank_active}. "
                  "This demonstrates the need for the supersession penalty in postprocess.")
    else:
        found = active_id if active_id in retrieved_ids else superseded_id
        print(f"  Observation: Only {found} found in top-10. Semantic overlap not fully captured by dense alone.")

    print("\nAll dense retrieval sanity checks passed successfully!")


if __name__ == "__main__":
    test_dense_retrieval_sanity()
