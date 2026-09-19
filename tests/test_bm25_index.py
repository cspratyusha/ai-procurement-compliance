import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_loader import load_corpus, load_eval_set, get_standard_by_id
from indexing.bm25_index import build_index as build_bm25_index, bm25_search, load_index as load_bm25_index
from indexing.embed_index import dense_search


def test_bm25_retrieval():
    print("=" * 75)
    print("TESTING SPARSE (BM25) RETRIEVAL & DENSE VS SPARSE COMPARISON")
    print("=" * 75)

    # 1. Build and verify BM25 Index
    print("\n--- [Step 1] Building and Verifying BM25 Index ---")
    corpus = load_corpus()
    build_bm25_index(corpus)
    
    bm25, ids = load_bm25_index()
    assert len(bm25.doc_len) == len(corpus), f"Expected {len(corpus)} docs in BM25, got {len(bm25.doc_len)}"
    assert len(ids) == len(corpus), f"Expected {len(corpus)} IDs, got {len(ids)}"
    print(f"BM25 index successfully verified with {len(ids)} documents.")

    eval_data = load_eval_set()

    # 2. Side-by-Side Comparison on 4 representative eval queries
    print("\n--- [Step 2] Side-by-Side Comparison: Dense (FAISS) vs Sparse (BM25) ---")
    print("Logging ranks & scores to provide diagnostic baseline for Hybrid Fusion (RRF):\n")
    
    # Header format
    header = f"{'Query / Target':<45} | {'Dense Rank (Score)':<22} | {'BM25 Rank (Score)':<22} | {'Agreement'}"
    print(header)
    print("-" * len(header))

    # Use first 4 eval queries (real std_* IDs)
    sample_queries = eval_data[:4]

    for case in sample_queries:
        query = case["query"]
        target_id = case["correct_id"]
        target_std = get_standard_by_id(target_id)
        
        # Dense search
        dense_results = dense_search(query, top_k=10)
        dense_ids = [r[0] for r in dense_results]
        dense_rank = dense_ids.index(target_id) + 1 if target_id in dense_ids else ">10"
        dense_score = next((r[1] for r in dense_results if r[0] == target_id), 0.0)
        
        # BM25 search
        bm25_results = bm25_search(query, top_k=10)
        bm25_ids = [r[0] for r in bm25_results]
        bm25_rank = bm25_ids.index(target_id) + 1 if target_id in bm25_ids else ">10"
        bm25_score = next((r[1] for r in bm25_results if r[0] == target_id), 0.0)

        agree = "AGREE (Both Top-1)" if dense_rank == 1 and bm25_rank == 1 else "DIVERGE"
        short_q = (query[:38] + "...") if len(query) > 38 else query
        
        dense_str = f"#{dense_rank} ({dense_score:.4f})"
        bm25_str = f"#{bm25_rank} ({bm25_score:.2f})"
        print(f"{short_q:<45} | {dense_str:<22} | {bm25_str:<22} | {agree}")

    # 3. Assertions on BM25 Strengths (Exact Standard Numbers & Rare Keywords)
    print("\n--- [Step 3] Validating BM25 Strengths (Numbers & Rare Keywords) ---")
    
    # Filter by difficulty="exact_identifier" — these queries contain standard numbers where BM25 excels
    bm25_targeted_cases = [c for c in eval_data if c.get("difficulty") == "exact_identifier"]
    assert len(bm25_targeted_cases) >= 3, (
        f"Expected at least 3 exact_identifier test queries in eval_set.json, got {len(bm25_targeted_cases)}"
    )
    # Test first 5 exact_identifier queries to keep test duration reasonable
    bm25_targeted_cases = bm25_targeted_cases[:5]

    for i, case in enumerate(bm25_targeted_cases, 1):
        query = case["query"]
        target_id = case["correct_id"]
        target_std = get_standard_by_id(target_id)
        
        bm25_results = bm25_search(query, top_k=5)
        bm25_ids = [r[0] for r in bm25_results]
        
        dense_results = dense_search(query, top_k=5)
        dense_ids = [r[0] for r in dense_results]

        print(f"\n[Test Case {i}] Query: '{query}'")
        print(f"  Target: [{target_id}] {target_std.number if target_std else '?'} - {(target_std.title if target_std else '?')[:50]}...")
        
        assert target_id in bm25_ids, (
            f"BM25 failed to retrieve target ID '{target_id}' in top-5 results! "
            f"Retrieved: {bm25_ids}"
        )
        
        bm25_rank = bm25_ids.index(target_id) + 1
        dense_rank_val = dense_ids.index(target_id) + 1 if target_id in dense_ids else ">5"
        
        print(f"  --> BM25 Rank: #{bm25_rank} (Score: {bm25_results[bm25_rank-1][1]:.2f}) [PASS]")
        print(f"  --> Dense Rank: #{dense_rank_val}")
        print(f"  Top-3 BM25 Matches:")
        for r_idx, (ret_id, score) in enumerate(bm25_results[:3], 1):
            r_std = get_standard_by_id(ret_id)
            print(f"     #{r_idx}: [{ret_id}] {r_std.number if r_std else '?'} (score: {score:.2f})")

    print("\n" + "=" * 75)
    print("All BM25 index and retrieval tests passed successfully!")
    print("=" * 75)


if __name__ == "__main__":
    test_bm25_retrieval()
