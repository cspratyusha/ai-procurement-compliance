import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Any, Optional

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data_loader import load_eval_set, get_standard_by_id
from retrieval.hybrid import hybrid_search
from retrieval.rerank import full_retrieve


def precision_at_k(ranked_ids: List[str], correct_id: str, k: int) -> float:
    """Computes Precision@K for a single-relevant-document ground truth evaluation.
    
    Note: Because each query in eval_set.json specifies exactly ONE correct target standard,
    Precision@K evaluates whether that single ground-truth standard appears anywhere within
    the top-K retrieved items (Success@K / HitRate@K).
    Returns 1.0 if correct_id in ranked_ids[:k], else 0.0.
    """
    if not ranked_ids or not correct_id or k <= 0:
        return 0.0
    return 1.0 if correct_id in ranked_ids[:k] else 0.0


def recall_at_k(ranked_ids: List[str], correct_id: str, k: int) -> float:
    """Computes Recall@K for a single-relevant-document ground truth evaluation.
    
    Note: In information retrieval with a single relevant document (|Relevant| = 1),
    Recall@K = |Retrieved_K ∩ Relevant| / |Relevant| = (1 or 0) / 1 = 1.0 or 0.0.
    Hence, Recall@K mathematically coincides with Precision@K (Hit@K) in the single-item setting.
    """
    if not ranked_ids or not correct_id or k <= 0:
        return 0.0
    return 1.0 if correct_id in ranked_ids[:k] else 0.0


def ndcg_at_k(ranked_ids: List[str], correct_id: str, k: int) -> float:
    """Computes Normalized Discounted Cumulative Gain (NDCG@K) with binary relevance.
    
    Formula:
        DCG@K = sum_{i=1}^K (rel_i / log2(i + 1))
        IDCG@K = 1.0 / log2(1 + 1) = 1.0 (since exactly 1 relevant document exists)
        NDCG@K = DCG@K / IDCG@K = 1.0 / log2(rank + 1) if 1 <= rank <= K, else 0.0
        
    Args:
        ranked_ids: List of retrieved standard IDs ordered by rank.
        correct_id: Canonical target standard ID.
        k: Truncation threshold.
        
    Returns:
        NDCG score in [0.0, 1.0].
    """
    if not ranked_ids or not correct_id or k <= 0:
        return 0.0

    top_k_ids = ranked_ids[:k]
    if correct_id not in top_k_ids:
        return 0.0

    rank = top_k_ids.index(correct_id) + 1  # 1-indexed rank
    dcg = 1.0 / math.log2(rank + 1)
    idcg = 1.0 / math.log2(1 + 1)  # idcg = 1.0

    return dcg / idcg


def run_evaluation(
    retrieval_fn: Callable[[str], List[Any]],
    eval_set_path: Optional[str] = None
) -> Dict[str, Any]:
    """Runs a complete evaluation benchmark over eval_set.json with category breakdowns.
    
    Computes:
      - Precision@1 (Top-1 Accuracy)
      - Recall@5 (Top-5 Coverage)
      - NDCG@5 (Rank-Discounted Relevance Quality)
      - Category-level metrics: 'easy', 'hard_duplicate', 'hard_identifier'
      
    Args:
        retrieval_fn: Function mapping (query: str) -> list of (standard_id, score) or list of ids.
        eval_set_path: Optional custom path to evaluation JSON.
        
    Returns:
        Dictionary containing overall metrics, category breakdowns, and per-query logs.
    """
    eval_data = load_eval_set(eval_set_path)
    total_queries = len(eval_data)
    if total_queries == 0:
        raise ValueError("Evaluation set is empty.")

    query_results = []
    category_metrics = defaultdict(lambda: {"p1": [], "r5": [], "ndcg5": []})
    overall_p1 = []
    overall_r5 = []
    overall_ndcg5 = []

    for item in eval_data:
        query = item["query"]
        correct_id = item["correct_id"]
        category = item.get("category", "uncategorized")

        # Run retrieval function
        raw_results = retrieval_fn(query)
        # Handle list of tuples (id, score) or list of ids
        ranked_ids = [r[0] if isinstance(r, (tuple, list)) else r for r in raw_results]

        # Calculate metrics
        p1 = precision_at_k(ranked_ids, correct_id, k=1)
        r5 = recall_at_k(ranked_ids, correct_id, k=5)
        ndcg5 = ndcg_at_k(ranked_ids, correct_id, k=5)

        rank_str = str(ranked_ids.index(correct_id) + 1) if correct_id in ranked_ids else ">" + str(len(ranked_ids))

        overall_p1.append(p1)
        overall_r5.append(r5)
        overall_ndcg5.append(ndcg5)

        category_metrics[category]["p1"].append(p1)
        category_metrics[category]["r5"].append(r5)
        category_metrics[category]["ndcg5"].append(ndcg5)

        query_results.append({
            "query": query,
            "correct_id": correct_id,
            "category": category,
            "rank": rank_str,
            "p1": p1,
            "r5": r5,
            "ndcg5": ndcg5,
            "top_retrieved": ranked_ids[:3]
        })

    # Aggregate category scores
    category_summary = {}
    for cat, scores in category_metrics.items():
        n = len(scores["p1"])
        category_summary[cat] = {
            "count": n,
            "precision_at_1": sum(scores["p1"]) / n,
            "recall_at_5": sum(scores["r5"]) / n,
            "ndcg_at_5": sum(scores["ndcg5"]) / n
        }

    summary = {
        "total_queries": total_queries,
        "overall": {
            "precision_at_1": sum(overall_p1) / total_queries,
            "recall_at_5": sum(overall_r5) / total_queries,
            "ndcg_at_5": sum(overall_ndcg5) / total_queries
        },
        "by_category": category_summary,
        "queries": query_results
    }

    return summary


def print_comparison_tables(
    results_map: Dict[str, Dict[str, Any]],
    run_id: Optional[str] = None,
    split_name: Optional[str] = None
) -> None:
    """Formats and prints executive comparison tables across retrieval pipelines with full traceability."""
    trace_str = f" [run_id: {run_id} | split: {split_name}]" if (run_id or split_name) else ""
    print("=" * 85)
    print(f"           STANDARDS RETRIEVAL & RANKING EVALUATION REPORT{trace_str}")
    print("=" * 85)

    # 1. Overall Metrics Table
    print(f"\n--- [1] OVERALL PIPELINE BENCHMARK{trace_str} ---")
    headers = f"{'Pipeline Stage':<32} | {'P@1 (Top-1)':<14} | {'Recall@5':<14} | {'NDCG@5':<14}"
    print(headers)
    print("-" * len(headers))
    for stage_name, res in results_map.items():
        ov = res["overall"]
        p1 = f"{ov['precision_at_1'] * 100:.1f}%"
        r5 = f"{ov['recall_at_5'] * 100:.1f}%"
        n5 = f"{ov['ndcg_at_5']:.4f}"
        print(f"{stage_name:<32} | {p1:<14} | {r5:<14} | {n5:<14}")

    # 2. Category Breakdown Table
    print(f"\n--- [2] PERFORMANCE BREAKDOWN BY QUERY DIFFICULTY{trace_str} ---")
    cat_header = f"{'Category':<18} | {'Stage':<24} | {'Count':<6} | {'P@1':<10} | {'Recall@5':<10} | {'NDCG@5':<10}"
    print(cat_header)
    print("-" * len(cat_header))

    categories = ["easy", "hard_duplicate", "hard_identifier"]
    for cat in categories:
        for stage_name, res in results_map.items():
            cat_data = res["by_category"].get(cat)
            if cat_data:
                cnt = str(cat_data["count"])
                p1 = f"{cat_data['precision_at_1'] * 100:.1f}%"
                r5 = f"{cat_data['recall_at_5'] * 100:.1f}%"
                n5 = f"{cat_data['ndcg_at_5']:.4f}"
                print(f"{cat:<18} | {stage_name:<24} | {cnt:<6} | {p1:<10} | {r5:<10} | {n5:<10}")
        print("-" * len(cat_header))

    # 3. Diagnostic Per-Query Inspection
    print(f"\n--- [3] PER-QUERY DIAGNOSTIC COMPARISON{trace_str} ---")
    q_header = f"{'ID':<4} | {'Category':<16} | {'Target':<12} | " + " | ".join([f"{name[:12]:<12}" for name in results_map.keys()])
    print(q_header)
    print("-" * len(q_header))

    first_stage = list(results_map.keys())[0]
    num_queries = len(results_map[first_stage]["queries"])

    for i in range(num_queries):
        base_q = results_map[first_stage]["queries"][i]
        cat = base_q["category"]
        target = base_q["correct_id"]
        ranks = []
        for name in results_map.keys():
            r = results_map[name]["queries"][i]["rank"]
            ranks.append(f"#{r:<11}")
        print(f"Q{i+1:<3} | {cat:<16} | {target:<12} | " + " | ".join(ranks))

    print("=" * 80)


def main():
    print("[EvalHarness] Initializing retrieval engines and running benchmarks...\n")

    # Benchmark 1: Hybrid Search (RRF)
    print("[EvalHarness] Evaluating Hybrid Search (Stage B)...")
    hybrid_metrics = run_evaluation(lambda q: hybrid_search(q, top_k=20))

    # Benchmark 2: Full Retrieve with Cross-Encoder Re-Ranking (Stage D)
    print("[EvalHarness] Evaluating Full Retrieve + Cross-Encoder Re-Ranking (Stage D)...")
    rerank_metrics = run_evaluation(lambda q: full_retrieve(q, top_k=10))

    results_map = {
        "Hybrid Search (RRF)": hybrid_metrics,
        "Full Retrieve (+ CrossEncoder)": rerank_metrics,
    }

    print_comparison_tables(results_map)


if __name__ == "__main__":
    main()
