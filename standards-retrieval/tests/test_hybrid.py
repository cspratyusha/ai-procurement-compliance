import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_loader import load_corpus, load_eval_set, get_standard_by_id
from indexing.embed_index import dense_search
from indexing.bm25_index import bm25_search
from retrieval.hybrid import rrf_merge, hybrid_search, DEFAULT_RRF_K


def test_union_behavior():
    print("\n--- [Test 1] Guard: Union vs Intersection in RRF ---")
    # Simulate synthetic result lists where items appear in only one list
    dense_mock = [("DOC-A", 0.95), ("DOC-B", 0.85)]  # DOC-A is rank 1, DOC-B is rank 2
    bm25_mock = [("DOC-C", 30.0), ("DOC-A", 20.0)]   # DOC-C is rank 1, DOC-A is rank 2

    merged = rrf_merge(dense_mock, bm25_mock, k=60, top_k=10)
    merged_dict = dict(merged)

    print(f"Dense Mock: {dense_mock}")
    print(f"BM25 Mock:  {bm25_mock}")
    print(f"Merged RRF: {merged}")

    # DOC-B appears ONLY in dense, DOC-C appears ONLY in BM25, DOC-A in both
    assert "DOC-B" in merged_dict, "DOC-B (dense-only) was incorrectly dropped from RRF merge!"
    assert "DOC-C" in merged_dict, "DOC-C (bm25-only) was incorrectly dropped from RRF merge!"
    assert "DOC-A" in merged_dict, "DOC-A (present in both) missing from RRF merge!"

    # DOC-A has rank 1 in dense (1/61) + rank 2 in bm25 (1/62) -> highest score
    expected_doc_a = (1.0 / 61.0) + (1.0 / 62.0)
    assert abs(merged_dict["DOC-A"] - expected_doc_a) < 1e-6
    assert merged[0][0] == "DOC-A", f"Expected DOC-A to rank #1, got {merged[0][0]}"

    print("  [PASS] Union behavior confirmed: Single-system hits are preserved and scored correctly.")


def test_disagreement_cases():
    print("\n--- [Test 2] Evaluating Disagreement / Divergence Cases ---")
    eval_data = load_eval_set()

    # Test cases that highlight different strengths
    # Case A: Exact standard number query where BM25 has distinct lexical signal
    case_num = next(c for c in eval_data if "IS 1554" in c["query"])
    # Case B: Complex natural language description
    case_desc = eval_data[1]  # Multi-strand flexible copper connecting wire
    # Case C: Technical compound terms
    case_tech = next(c for c in eval_data if "Tyton" in c["query"])

    test_cases = [case_num, case_desc, case_tech]

    for case in test_cases:
        query = case["query"]
        target_id = case["correct_id"]
        target_std = get_standard_by_id(target_id)

        dense_res = dense_search(query, top_k=10)
        bm25_res = bm25_search(query, top_k=10)
        fused_res = hybrid_search(query, top_k=10)

        d_ids = [r[0] for r in dense_res]
        b_ids = [r[0] for r in bm25_res]
        f_ids = [r[0] for r in fused_res]

        d_rank = d_ids.index(target_id) + 1 if target_id in d_ids else ">10"
        b_rank = b_ids.index(target_id) + 1 if target_id in b_ids else ">10"
        f_rank = f_ids.index(target_id) + 1 if target_id in f_ids else ">10"

        print(f"\nQuery: '{query[:65]}...'")
        print(f"  Target: [{target_id}] {target_std.number if target_std else ''}")
        print(f"  Dense Rank:  #{d_rank}")
        print(f"  BM25 Rank:   #{b_rank}")
        print(f"  Hybrid Rank: #{f_rank} (Score: {fused_res[f_rank-1][1]:.5f} if f_rank != '>10' else 0)")

        assert target_id in f_ids, f"Hybrid search failed to retain target '{target_id}' in top-10!"
        print(f"  [PASS] Target retained in Hybrid top-{len(f_ids)}.")


def test_full_eval_set_recall():
    print("\n--- [Test 3] Full Evaluation Set Recall Gut Check ---")
    eval_data = load_eval_set()
    total = len(eval_data)

    hits_top1 = 0
    hits_top3 = 0
    hits_top5 = 0
    hits_top20 = 0

    print(f"Running {total} queries from eval_set.json through hybrid_search()...\n")
    print(f"{'ID':<4} | {'Target ID':<12} | {'Dense':<7} | {'BM25':<7} | {'Hybrid':<7} | {'Query Snippet'}")
    print("-" * 80)

    for i, item in enumerate(eval_data, start=1):
        query = item["query"]
        target_id = item["correct_id"]

        d_res = dense_search(query, top_k=20)
        b_res = bm25_search(query, top_k=20)
        h_res = hybrid_search(query, top_k=20)

        d_ids = [r[0] for r in d_res]
        b_ids = [r[0] for r in b_res]
        h_ids = [r[0] for r in h_res]

        d_r = str(d_ids.index(target_id) + 1) if target_id in d_ids else ">20"
        b_r = str(b_ids.index(target_id) + 1) if target_id in b_ids else ">20"
        h_r = str(h_ids.index(target_id) + 1) if target_id in h_ids else ">20"

        if target_id in h_ids:
            rank = h_ids.index(target_id) + 1
            if rank == 1:
                hits_top1 += 1
            if rank <= 3:
                hits_top3 += 1
            if rank <= 5:
                hits_top5 += 1
            if rank <= 20:
                hits_top20 += 1

        snippet = (query[:38] + "...") if len(query) > 38 else query
        print(f"Q{i:<3} | {target_id:<12} | #{d_r:<6} | #{b_r:<6} | #{h_r:<6} | {snippet}")

    recall_top1 = (hits_top1 / total) * 100
    recall_top3 = (hits_top3 / total) * 100
    recall_top5 = (hits_top5 / total) * 100
    recall_top20 = (hits_top20 / total) * 100

    print("\n" + "=" * 55)
    print("HYBRID SEARCH RECALL METRICS SUMMARY:")
    print(f"  Total Diagnostic Queries : {total}")
    print(f"  Recall@1                 : {recall_top1:.1f}% ({hits_top1}/{total})")
    print(f"  Recall@3                 : {recall_top3:.1f}% ({hits_top3}/{total})")
    print(f"  Recall@5                 : {recall_top5:.1f}% ({hits_top5}/{total})")
    print(f"  Recall@20                : {recall_top20:.1f}% ({hits_top20}/{total})")
    print("=" * 55)

    assert recall_top20 == 100.0, f"Expected 100% Recall@20 on mock corpus, got {recall_top20:.1f}%"
    print("\nAll Hybrid Retrieval (RRF) tests passed successfully!")


if __name__ == "__main__":
    test_union_behavior()
    test_disagreement_cases()
    test_full_eval_set_recall()
