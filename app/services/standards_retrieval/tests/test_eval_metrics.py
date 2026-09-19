import math
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.evaluate import precision_at_k, recall_at_k, ndcg_at_k


def test_metric_functions_correctness():
    print("=" * 70)
    print("TESTING EVALUATION METRIC FUNCTIONS ON HAND-CRAFTED EXAMPLES")
    print("=" * 70)

    # Hand-constructed sample: 5 retrieved IDs, target is at Rank #3
    ranked_case_rank3 = ["DOC_A", "DOC_B", "DOC_TARGET", "DOC_D", "DOC_E"]
    target = "DOC_TARGET"

    # 1. Precision@1 (Target is at rank 3, so P@1 must be 0.0)
    p1 = precision_at_k(ranked_case_rank3, target, k=1)
    assert p1 == 0.0, f"Expected P@1=0.0 for rank 3, got {p1}"
    print(f"[Pass] Rank #3 -> Precision@1: {p1:.4f} == 0.0")

    # 2. Precision@5 and Recall@5 (Target is at rank 3, which is <= 5, so both are 1.0)
    p5 = precision_at_k(ranked_case_rank3, target, k=5)
    r5 = recall_at_k(ranked_case_rank3, target, k=5)
    assert p5 == 1.0, f"Expected P@5=1.0 for rank 3, got {p5}"
    assert r5 == 1.0, f"Expected Recall@5=1.0 for rank 3, got {r5}"
    print(f"[Pass] Rank #3 -> Precision@5: {p5:.4f} == 1.0 | Recall@5: {r5:.4f} == 1.0")

    # 3. NDCG@5 calculation by hand:
    # Rank 3 -> DCG = 1 / log2(3 + 1) = 1 / log2(4) = 1 / 2.0 = 0.5000
    # IDCG = 1 / log2(1 + 1) = 1 / 1.0 = 1.0
    # NDCG@5 = 0.5000 / 1.0 = 0.5000
    ndcg5_rank3 = ndcg_at_k(ranked_case_rank3, target, k=5)
    expected_ndcg5_rank3 = 0.5000
    assert abs(ndcg5_rank3 - expected_ndcg5_rank3) < 1e-6, (
        f"Expected NDCG@5={expected_ndcg5_rank3}, got {ndcg5_rank3}"
    )
    print(f"[Pass] Rank #3 -> NDCG@5: {ndcg5_rank3:.4f} == {expected_ndcg5_rank3:.4f} (1 / log2(4))")

    # 4. Target at Rank #1
    ranked_case_rank1 = ["DOC_TARGET", "DOC_A", "DOC_B", "DOC_C", "DOC_D"]
    p1_top = precision_at_k(ranked_case_rank1, target, k=1)
    ndcg5_top = ndcg_at_k(ranked_case_rank1, target, k=5)
    assert p1_top == 1.0, f"Expected P@1=1.0 for rank 1, got {p1_top}"
    assert abs(ndcg5_top - 1.0) < 1e-6, f"Expected NDCG@5=1.0 for rank 1, got {ndcg5_top}"
    print(f"[Pass] Rank #1 -> Precision@1: {p1_top:.4f} == 1.0 | NDCG@5: {ndcg5_top:.4f} == 1.0")

    # 5. Target outside Top-5 (e.g. Rank #6 or unretrieved)
    ranked_case_rank6 = ["DOC_A", "DOC_B", "DOC_C", "DOC_D", "DOC_E", "DOC_TARGET"]
    p5_miss = precision_at_k(ranked_case_rank6, target, k=5)
    r5_miss = recall_at_k(ranked_case_rank6, target, k=5)
    ndcg5_miss = ndcg_at_k(ranked_case_rank6, target, k=5)
    assert p5_miss == 0.0, f"Expected P@5=0.0 for rank 6, got {p5_miss}"
    assert r5_miss == 0.0, f"Expected Recall@5=0.0 for rank 6, got {r5_miss}"
    assert ndcg5_miss == 0.0, f"Expected NDCG@5=0.0 for rank 6, got {ndcg5_miss}"
    print(f"[Pass] Rank #6 -> Precision@5: {p5_miss:.4f} == 0.0 | Recall@5: {r5_miss:.4f} == 0.0 | NDCG@5: {ndcg5_miss:.4f} == 0.0")

    # 6. Edge cases (empty lists, invalid k)
    assert precision_at_k([], target, k=5) == 0.0
    assert recall_at_k([], target, k=5) == 0.0
    assert ndcg_at_k([], target, k=5) == 0.0
    assert ndcg_at_k(ranked_case_rank1, target, k=0) == 0.0
    print("[Pass] Handled edge cases (empty lists, zero k).")

    print("\n" + "=" * 70)
    print("All evaluation metric function unit tests passed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    test_metric_functions_correctness()
