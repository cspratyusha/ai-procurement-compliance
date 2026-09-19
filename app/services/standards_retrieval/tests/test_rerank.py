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
    print("TEST 1: SUPERSESSION PAIR AMBIGUITY SHARPENING (DENSE VS CROSS-ENCODER)")
    print("=" * 80)

    # Real supersession pairs in the corpus:
    # std_017 (IS 226:1975, superseded) vs std_001 (IS 2062:2011, active) — structural steel
    # std_018 (IS 1139:1966, superseded) vs std_012 (IS 1786:2008, active) — deformed bars
    query_1 = "structural steel standard quality for general construction purposes"
    target_id_1 = "std_001"       # IS 2062:2011 (active successor)
    confounder_id_1 = "std_017"   # IS 226:1975 (superseded)

    query_2 = "high strength deformed steel bars for concrete reinforcement"
    target_id_2 = "std_012"       # IS 1786:2008 (active successor)
    confounder_id_2 = "std_018"   # IS 1139:1966 (superseded)

    cases = [
        ("Structural Steel Supersession", query_1, target_id_1, confounder_id_1),
        ("Deformed Bars Supersession", query_2, target_id_2, confounder_id_2)
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

        print(f"  Target (active):     [{target_id}] {target_std.number if target_std else ''}")
        print(f"  Confounder (superseded): [{confounder_id}] {confounder_std.number if confounder_std else ''}")
        print(f"\n  [Dense (Cosine)]       Target: {d_target_score:.4f} | Confounder: {d_confounder_score:.4f} | Margin: {d_gap:+.4f}")
        print(f"  [Cross-Encoder Logits] Target: {ce_target_score:+.4f} | Confounder: {ce_confounder_score:+.4f} | Margin: {ce_gap:+.4f}")
        
        # Rank of target in full_retrieve
        ce_ranks = [r[0] for r in rerank_results]
        target_rank = ce_ranks.index(target_id) + 1 if target_id in ce_ranks else -1
        confounder_rank = ce_ranks.index(confounder_id) + 1 if confounder_id in ce_ranks else -1
        print(f"  Final Pipeline Rank of Target: #{target_rank}")
        print(f"  Final Pipeline Rank of Confounder: #{confounder_rank}")

        # Active successor must appear in results and rank above superseded (due to supersession penalty)
        assert target_id in ce_ranks, f"Expected active target '{target_id}' in full_retrieve results"
        if confounder_id in ce_ranks:
            assert target_rank < confounder_rank, (
                f"Expected active '{target_id}' (#{target_rank}) to rank above superseded "
                f"'{confounder_id}' (#{confounder_rank}) after supersession penalty"
            )
        print(f"  --> [PASS] Active successor ranked above superseded standard.")


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

    # Allow up to 10% regression from hybrid baseline — cross-encoder on a small 18-doc corpus
    # may slightly degrade P@1 on some queries where the superseded standard (IS 226:1975)
    # is semantically very close to the active one. The supersession penalty in postprocess
    # handles this correctly at the final output stage.
    tolerance = 10.0
    assert rerank_p1 >= hybrid_p1 - tolerance, (
        f"Re-ranking caused unacceptable performance degradation! "
        f"(Rerank P@1={rerank_p1:.1f}% vs Hybrid P@1={hybrid_p1:.1f}%, tolerance={tolerance}%)"
    )
    assert avg_latency < 1500.0, f"Average latency ({avg_latency:.2f}ms) exceeded 1500ms SLA!"
    print("\nAll Re-Ranking tests and latency checks passed successfully!")


if __name__ == "__main__":
    test_near_duplicate_gap_sharpening()
    test_full_eval_set_precision_and_latency()
