"""Feature diagnostics and SHAP contribution analysis for LTR ranking model.

Computes:
1. Full 7x7 pairwise correlation matrix across ranking features over training data.
2. Specific correlation between bm25_score_normalized and keyword_overlap (redundancy analysis).
3. Per-feature additive SHAP-style contributions via booster.predict(X, pred_contrib=True)
   for 5 specific queries with full model/split traceability:
     - Case 1: Q16-style superseded vs active pair (IS-ELEC-006 vs IS-ELEC-005) with post-penalty evaluation
     - Case 2: use_case_only query #1 (IS-ELEC-002)
     - Case 3: use_case_only query #2 (IS-STEEL-008)
     - Case 4: Q19 end-to-end verification on final promoted model (IS-ELEC-001)
     - Case 5: Q22 end-to-end verification on final promoted model (IS-CEM-001)
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data_loader import load_corpus, get_standard_by_id, load_eval_set
from ltr.features import FEATURE_NAMES, build_features
from ltr.train import build_training_data, load_model
from indexing.embed_index import dense_search
from indexing.bm25_index import bm25_search
from retrieval.rerank import rerank, full_retrieve
from retrieval.hybrid import hybrid_search
from retrieval.postprocess import apply_supersession_penalty


def compute_and_print_correlation_matrix(
    X: np.ndarray,
    feature_names: List[str],
    run_id: str,
    split_name: str = "train_queries.json"
) -> np.ndarray:
    """Computes and displays the Pearson correlation matrix across ranking features with traceability."""
    print("=" * 95)
    print(f"           RANKING FEATURE CORRELATION MATRIX [run_id: {run_id} | split: {split_name}]")
    print("=" * 95)

    n_feats = len(feature_names)
    corr = np.zeros((n_feats, n_feats), dtype=np.float32)

    stds = np.std(X, axis=0)
    for i in range(n_feats):
        for j in range(n_feats):
            if stds[i] < 1e-9 or stds[j] < 1e-9:
                corr[i, j] = 1.0 if i == j else 0.0
            else:
                c = np.corrcoef(X[:, i], X[:, j])[0, 1]
                corr[i, j] = 0.0 if np.isnan(c) else c

    col_w = 9
    header = f"{'Feature':<28} | " + " | ".join([f"{name[:8]:<{col_w}}" for name in feature_names])
    print(header)
    print("-" * len(header))

    for i, name in enumerate(feature_names):
        row_str = " | ".join([f"{corr[i, j]:+9.3f}" for j in range(n_feats)])
        print(f"{name:<28} | {row_str}")

    print("=" * 95)

    # Specific analysis between bm25_score_normalized and keyword_overlap
    bm25_idx = feature_names.index("bm25_score_normalized")
    kw_idx = feature_names.index("keyword_overlap")
    r_bm25_kw = corr[bm25_idx, kw_idx]

    print(f"\n--- SPECIFIC FEATURE REDUNDANCY ANALYSIS [run_id: {run_id} | split: {split_name}] ---")
    print(f"Correlation between 'bm25_score_normalized' and 'keyword_overlap': r = {r_bm25_kw:+.4f}")
    if r_bm25_kw > 0.8:
        print("[Diagnostic Note] High collinearity (r > 0.80) detected between BM25 normalized score")
        print("  and keyword_overlap. This confirms that keyword_overlap's near 0.0% tree gain importance")
        print("  is due to structural REDUNDANCY with BM25 (both capture lexical term match), NOT because")
        print("  keyword matching is a weak or useless feature.")
    else:
        print(f"[Diagnostic Note] Moderate correlation (r = {r_bm25_kw:+.4f}). Features carry distinct lexical facets.")

    for idx, name in enumerate(feature_names):
        if stds[idx] < 1e-9:
            print(f"[Diagnostic Note] Feature '{name}' is currently constant across training data (std=0.000).")

    return corr


def diagnose_query_contributions(
    query: str,
    target_id: str,
    case_label: str,
    run_id: str,
    confounder_id: Optional[str] = None,
    split_name: str = "held_out_eval_set"
) -> None:
    """Uses LightGBM's pred_contrib=True to extract exact per-feature additive SHAP contributions,
    and evaluates the effect of the deterministic supersession penalty.
    """
    trace_str = f"[run_id: {run_id} | model: live_promoted | split: {split_name}]"
    print("\n" + "=" * 95)
    print(f"DIAGNOSTIC CASE: {case_label} {trace_str}")
    print("=" * 95)
    print(f"Query: \"{query}\"")

    booster = load_model()
    if booster is None:
        print("[Error] No trained LTR model found at models/ltr_model.txt. Train model first via python ltr/train.py")
        return

    corpus_dict = {s.id: s for s in load_corpus()}
    target_std = corpus_dict.get(target_id)
    if not target_std:
        print(f"[Error] Missing target standard {target_id}")
        return

    # Fetch intermediate retrieval scores
    hybrid_res = hybrid_search(query, top_k=20)
    candidate_ids = [cid for cid, _ in hybrid_res]
    if target_id not in candidate_ids:
        candidate_ids.append(target_id)
    if confounder_id and confounder_id not in candidate_ids:
        candidate_ids.append(confounder_id)

    dense_dict = dict(dense_search(query, top_k=30))
    bm25_dict = dict(bm25_search(query, top_k=30))
    rerank_dict = dict(rerank(query, candidate_ids, corpus=corpus_dict, top_k=len(candidate_ids)))

    # Per-query min-max normalization for BM25
    raw_b = [bm25_dict.get(c, 0.0) for c in candidate_ids]
    min_b, max_b = min(raw_b), max(raw_b)
    range_b = max_b - min_b

    def extract_fv(std_id, std_obj):
        d_s = dense_dict.get(std_id, 0.0)
        b_raw = bm25_dict.get(std_id, 0.0)
        b_norm = (b_raw - min_b) / (range_b + 1e-6) if range_b > 1e-6 else 0.5
        ce_s = rerank_dict.get(std_id, -10.0)
        return build_features(
            query=query,
            candidate_id=std_id,
            standard=std_obj,
            dense_score=d_s,
            bm25_score_normalized=b_norm,
            cross_encoder_score=ce_s,
            historical_acceptance_rate=0.0
        ), {
            "dense": d_s,
            "bm25_raw": b_raw,
            "bm25_norm": b_norm,
            "cross_encoder": ce_s,
            "last_amended": std_obj.last_amended,
            "status": std_obj.status
        }

    fv_target, raw_target = extract_fv(target_id, target_std)

    # Score all candidates with booster
    all_fvs = []
    for cid in candidate_ids:
        std_obj = corpus_dict.get(cid)
        if std_obj:
            fv, _ = extract_fv(cid, std_obj)
            all_fvs.append((cid, fv))

    X_all = np.array([fv for _, fv in all_fvs], dtype=np.float32)
    raw_scores_all = booster.predict(X_all)
    raw_ranked = sorted(zip([cid for cid, _ in all_fvs], raw_scores_all), key=lambda x: x[1], reverse=True)

    # Apply deterministic supersession penalty post-scoring
    post_penalty_ranked = apply_supersession_penalty(raw_ranked, corpus=corpus_dict, penalty=2.0)

    raw_target_rank = next((i + 1 for i, (cid, _) in enumerate(raw_ranked) if cid == target_id), len(candidate_ids))
    post_target_rank = next((i + 1 for i, (cid, _) in enumerate(post_penalty_ranked) if cid == target_id), len(candidate_ids))

    if not confounder_id:
        if raw_ranked[0][0] == target_id and len(raw_ranked) > 1:
            confounder_id = raw_ranked[1][0]
        else:
            confounder_id = raw_ranked[0][0]

    confounder_std = corpus_dict.get(confounder_id)
    if not confounder_std:
        print(f"[Error] Missing confounder standard {confounder_id}")
        return

    fv_confounder, raw_confounder = extract_fv(confounder_id, confounder_std)

    X_pair = np.array([fv_target, fv_confounder], dtype=np.float32)
    contribs = booster.predict(X_pair, pred_contrib=True)

    t_contrib = contribs[0]
    c_contrib = contribs[1]
    base_val = t_contrib[-1]

    t_total = np.sum(t_contrib)
    c_total = np.sum(c_contrib)

    raw_conf_rank = next((i + 1 for i, (cid, _) in enumerate(raw_ranked) if cid == confounder_id), ">20")
    post_conf_rank = next((i + 1 for i, (cid, _) in enumerate(post_penalty_ranked) if cid == confounder_id), ">20")

    print(f"\nTarget Document:     [{target_id}] {target_std.number} (Status: {raw_target['status']}, Amended: {raw_target['last_amended']})")
    print(f"  -> Raw ML Score: {t_total:+.4f} (Rank #{raw_target_rank}) | Post-Penalty Rank: #{post_target_rank}")
    print(f"Confounder Document: [{confounder_id}] {confounder_std.number} (Status: {raw_confounder['status']}, Amended: {raw_confounder['last_amended']})")
    print(f"  -> Raw ML Score: {c_total:+.4f} (Rank #{raw_conf_rank}) | Post-Penalty Rank: #{post_conf_rank}\n")

    tbl_header = f"{'Feature Name':<28} | {'Target Val':<11} | {'Target Contrib':<14} | {'Conf Val':<11} | {'Conf Contrib':<14} | {'Contrib Delta':<14}"
    print(tbl_header)
    print("-" * len(tbl_header))

    delta_contributions = []
    for idx, name in enumerate(FEATURE_NAMES):
        t_val = f"{fv_target[idx]:.4f}"
        t_c = f"{t_contrib[idx]:+10.4f}"
        c_val = f"{fv_confounder[idx]:.4f}"
        c_c = f"{c_contrib[idx]:+10.4f}"
        delta = t_contrib[idx] - c_contrib[idx]
        delta_str = f"{delta:+12.4f}"
        delta_contributions.append((name, delta, t_contrib[idx], c_contrib[idx], fv_target[idx], fv_confounder[idx]))
        print(f"{name:<28} | {t_val:<11} | {t_c:<14} | {c_val:<11} | {c_c:<14} | {delta_str}")

    print("-" * len(tbl_header))
    print(f"{'Base Value (Model Bias)':<28} | {'-':<11} | {base_val:+10.4f}     | {'-':<11} | {base_val:+10.4f}     | {'+0.0000':>14}")
    print(f"{'RAW MODEL SCORE':<28} | {'-':<11} | {t_total:+10.4f}     | {'-':<11} | {c_total:+10.4f}     | {t_total - c_total:+14.4f}")
    print("=" * 95)

    delta_contributions.sort(key=lambda x: abs(x[1]), reverse=True)
    top_driver = delta_contributions[0]
    second_driver = delta_contributions[1]

    print("Primary Pre-Penalty Prediction Drivers:")
    print(f"  1. '{top_driver[0]}': Delta = {top_driver[1]:+.4f} (Target val={top_driver[4]:.3f} vs Conf val={top_driver[5]:.3f})")
    print(f"  2. '{second_driver[0]}': Delta = {second_driver[1]:+.4f} (Target val={second_driver[4]:.3f} vs Conf val={second_driver[5]:.3f})")

    # Evaluate resolution
    if post_target_rank < post_conf_rank:
        if raw_target_rank < raw_conf_rank:
            print(f"[Resolution Status] Target '{target_id}' correctly outranks '{confounder_id}' naturally via ML model (Rank #{post_target_rank} vs #{post_conf_rank}).")
        else:
            print(f"[Resolution Status] SUCCESS: Deterministic supersession penalty successfully flipped ranking! Target '{target_id}' now ranks #{post_target_rank} ahead of superseded '{confounder_id}' (Rank #{post_conf_rank}).")
    else:
        print(f"[Resolution Status] ALERT: Confounder '{confounder_id}' still ahead (Rank #{post_conf_rank} vs #{post_target_rank}). Penalty was insufficient against BM25 delta.")


def run_all_diagnostics():
    run_id = f"diag_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print("\n" + "=" * 95)
    print(f"RUNNING COMPREHENSIVE LTR FEATURE & CONTRIBUTION DIAGNOSTICS [run_id: {run_id}]")
    print(f"Active Model Artifact: models/ltr_model.txt")
    print("=" * 95)

    # 1. Feature Correlation Matrix over training data
    X, y, groups, meta = build_training_data("data/train_queries.json")
    compute_and_print_correlation_matrix(X, FEATURE_NAMES, run_id=run_id, split_name="train_queries.json")

    # 2. Per-feature SHAP contributions for 5 specific eval queries
    print("\n" + "#" * 95)
    print(f"# EVAL QUERY SHAP CONTRIBUTION BREAKDOWNS [run_id: {run_id} | model: live_promoted]")
    print("#" * 95)

    # Case 1: Q16-style superseded/active pair
    diagnose_query_contributions(
        query="IS 1554 Part 1 heavy duty industrial power cables",
        target_id="IS-ELEC-006",
        case_label="Case 1: Q16-Style Superseded vs Active Pair",
        confounder_id="IS-ELEC-005",
        run_id=run_id
    )

    # Case 2: use_case_only query #1
    diagnose_query_contributions(
        query="A textile mill owner needs to buy cables that connect motors in an enclosed control room with lots of bending",
        target_id="IS-ELEC-002",
        case_label="Case 2: Use-Case Only Query (Factory Motor Cables - Target IS-ELEC-002)",
        run_id=run_id
    )

    # Case 3: use_case_only query #2
    diagnose_query_contributions(
        query="A pharmaceutical company needs hygienic corrosion proof tubes for their sterile injectable medicine production line",
        target_id="IS-STEEL-008",
        case_label="Case 3: Use-Case Only Query (Pharma Hygienic Tubes - Target IS-STEEL-008)",
        run_id=run_id
    )

    # Case 4: Q19 end-to-end verification on final promoted model
    diagnose_query_contributions(
        query="Our school campus is getting a new kitchen and we need the right wiring that goes inside the walls permanently",
        target_id="IS-ELEC-001",
        case_label="Case 4: Q19 School Kitchen Wiring (Target IS-ELEC-001)",
        run_id=run_id
    )

    # Case 5: Q22 end-to-end verification on final promoted model
    diagnose_query_contributions(
        query="We are constructing a basic affordable housing colony and need a simple reliable binding material for walls",
        target_id="IS-CEM-001",
        case_label="Case 5: Q22 Affordable Housing Wall Binding (Target IS-CEM-001)",
        run_id=run_id
    )


if __name__ == "__main__":
    run_all_diagnostics()
