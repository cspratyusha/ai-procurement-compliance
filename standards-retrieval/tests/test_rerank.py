import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_loader import load_corpus, load_eval_set, get_standard_by_id
from indexing.embed_index import dense_search
from retrieval.hybrid import hybrid_search
from retrieval.rerank import rerank, full_retrieve, get_cross_encoder_model


def test_near_duplicate_gap_sharpening():
    print("=" * 80)
    print("TEST 1: NEAR-DUPLICATE AMBIGUITY SHARPENING (DENSE VS CROSS-ENCODER)")
    print("=" * 80)

    # Near duplicate pair 1: Flexible Panel Wiring (IS-ELEC-002) vs Fixed Conduit Wiring (IS-ELEC-001)
    query_1 = "Multi-strand flexible copper connecting wire for industrial motor control centers and automation panel switchgear wiring"
    target_id_1 = "IS-ELEC-002"
    confounder_id_1 = "IS-ELEC-001"

    # Near duplicate pair 2: OPC 53 Grade (IS-CEM-002) vs OPC 43 Grade (IS-CEM-001)
    query_2 = "High early strength 53 grade cement with 53 MPa compressive strength for precast railway sleepers and highway flyover girders"
    target_id_2 = "IS-CEM-002"
    confounder_id_2 = "IS-CEM-001"

    cases = [
        ("Electrical Cable Disambiguation", query_1, target_id_1, confounder_id_1),
        ("Cement Grade Disambiguation", query_2, target_id_2, confounder_id_2)
    ]

    for test_name, query, target_id, confounder_id in cases:
        print(f"\n--- Case: {test_name} ---")
        print(f"Query: '{query}'")
        
        # 1. Dense Search baseline
        dense_results = dense_search(query, top_k=10)
        dense_dict = dict(dense_results)
        d_target_score = dense_dict.get(target_id, 0.0)
        d_confounder_score = dense_dict.get(confounder_id, 0.0)
        d_gap = d_target_score - d_confounder_score
        
        # 2. Cross-Encoder Re-ranking
        rerank_results = full_retrieve(query, top_k=10)
        rerank_dict = dict(rerank_results)
        ce_target_score = rerank_dict.get(target_id, -99.0)
        ce_confounder_score = rerank_dict.get(confounder_id, -99.0)
        ce_gap = ce_target_score - ce_confounder_score

        target_std = get_standard_by_id(target_id)
        confounder_std = get_standard_by_id(confounder_id)

        print(f"  Target:     [{target_id}] {target_std.number if target_std else ''}")
        print(f"  Confounder: [{confounder_id}] {confounder_std.number if confounder_std else ''}")
        print(f"\n  [Dense (Cosine)]       Target: {d_target_score:.4f} | Confounder: {d_confounder_score:.4f} | Margin: {d_gap:+.4f}")
        print(f"  [Cross-Encoder Logits] Target: {ce_target_score:+.4f} | Confounder: {ce_confounder_score:+.4f} | Margin: {ce_gap:+.4f}")
        
        # Rank of target in full_retrieve
        ce_ranks = [r[0] for r in rerank_results]
        target_rank = ce_ranks.index(target_id) + 1 if target_id in ce_ranks else -1
        print(f"  Final Pipeline Rank of Target: #{target_rank}")

        assert target_rank == 1, f"Expected target '{target_id}' to rank #1 after cross-encoder re-ranking!"
        print(f"  --> [PASS] Target ranked #1 with distinct cross-encoder logit separation.")


def test_full_eval_set_precision_and_latency():
    print("\n" + "=" * 80)
    print("TEST 2: FULL EVALUATION SET RE-RANKING BENCHMARK & LATENCY")
    print("=" * 80)

    eval_data = load_eval_set()
    total = len(eval_data)
    
    # Warmup cross encoder
    get_cross_encoder_model()

    hybrid_top1_count = 0
    rerank_top1_count = 0
    latencies = []

    print(f"\n{'ID':<4} | {'Target ID':<12} | {'Hybrid Rank':<12} | {'ReRank Rank':<12} | {'Latency':<9} | {'Top ReRanked Hit'}")
    print("-" * 90)

    for i, item in enumerate(eval_data, start=1):
        query = item["query"]
        target_id = item["correct_id"]

        # Stage 1: Hybrid Search
        h_res = hybrid_search(query, top_k=20)
        h_ids = [r[0] for r in h_res]
        h_rank = h_ids.index(target_id) + 1 if target_id in h_ids else ">20"
        if h_rank == 1:
            hybrid_top1_count += 1

        # Stage 2: Re-ranking with Latency Timer
        start_t = time.time()
        r_res = rerank(query=query, candidate_ids=h_ids, top_k=10)
        elapsed_ms = (time.time() - start_t) * 1000
        latencies.append(elapsed_ms)

        r_ids = [r[0] for r in r_res]
        r_rank = r_ids.index(target_id) + 1 if target_id in r_ids else ">10"
        if r_rank == 1:
            rerank_top1_count += 1

        top_std = get_standard_by_id(r_res[0][0]) if r_res else None
        top_str = f"[{r_res[0][0]}] {top_std.number if top_std else ''}" if r_res else "None"

        print(f"Q{i:<3} | {target_id:<12} | #{str(h_rank):<11} | #{str(r_rank):<11} | {elapsed_ms:6.1f}ms  | {top_str[:35]}")

    hybrid_p1 = (hybrid_top1_count / total) * 100
    rerank_p1 = (rerank_top1_count / total) * 100
    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

    print("\n" + "=" * 60)
    print("RE-RANKING PERFORMANCE & LATENCY REPORT:")
    print(f"  Total Evaluation Queries : {total}")
    print(f"  Hybrid Search Precision@1: {hybrid_p1:.1f}% ({hybrid_top1_count}/{total})")
    print(f"  Re-Ranked Precision@1    : {rerank_p1:.1f}% ({rerank_top1_count}/{total})")
    print(f"  Average Re-Rank Latency  : {avg_latency:.2f} ms")
    print(f"  P95 Re-Rank Latency      : {p95_latency:.2f} ms")
    print("=" * 60)

    assert rerank_p1 >= hybrid_p1, "Re-ranking caused performance degradation!"
    assert avg_latency < 1000.0, f"Average latency ({avg_latency:.2f}ms) exceeded 1000ms SLA!"
    print("\nAll Re-Ranking tests and latency checks passed successfully!")


if __name__ == "__main__":
    test_near_duplicate_gap_sharpening()
    test_full_eval_set_precision_and_latency()
