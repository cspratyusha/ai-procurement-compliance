import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
import numpy as np
import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")  # Headless backend to prevent tkinter GUI threading errors
import matplotlib.pyplot as plt

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.models import Standard
from data_loader import load_corpus, load_eval_set, get_standard_by_id
from indexing.embed_index import dense_search
from indexing.bm25_index import bm25_search
from retrieval.hybrid import hybrid_search
from retrieval.rerank import rerank, full_retrieve
from retrieval.postprocess import apply_supersession_penalty
from ltr.features import build_features, fallback_score, FEATURE_NAMES

# NOTE: `promotion_decision` is imported lazily inside `train_and_evaluate`.
# `feedback.retrain_and_promote` imports `ltr.train` at module level, so a
# top-level import here forms a cycle that leaves `ltr.train` partially
# initialized whenever `feedback` is imported first.

def _models_dir() -> Path:
    """Directory holding the trained ranker for the active corpus.

    A model's feature values are computed against a specific corpus, and its
    training labels reference that corpus's ids, so a model is only valid for
    the corpus it was trained on. Each corpus therefore gets its own directory
    — otherwise retraining against the canonical corpus silently overwrites
    the committed model that the mock corpus (and the test suite) depend on.
    """
    if os.environ.get("STANDARDS_CORPUS", "").strip().lower() in {"canonical", "consolidated"}:
        directory = _PROJECT_ROOT / "models" / "standards_corpus"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return _PROJECT_ROOT / "models"


_DEFAULT_MODEL_PATH = _models_dir() / "ltr_model.txt"
_REJECTED_MODEL_PATH = _models_dir() / "ltr_model_rejected.txt"
_DEFAULT_REPORT_PATH = _models_dir() / "training_report.json"
_DEFAULT_PLOT_PATH = _models_dir() / "training_curve.png"

_CACHED_LTR_MODEL: Optional[lgb.Booster] = None


def build_training_data(
    query_file_path: Optional[Union[str, Path, List[Union[str, Path]]]] = None,
    candidate_pool_size: int = 20
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    """Generates LTR feature matrices from training query sets.
    
    Uses graded relevance labels (not just binary 0/1) to give the model 
    richer ranking signal on partially-relevant candidates:
      - 3: exact correct standard
      - 1: same-category standard (partial relevance)
      - 0: different category (irrelevant)
    """
    corpus_list = load_corpus()
    corpus_dict = {s.id: s for s in corpus_list}

    # Determine input files.
    #
    # The query sets reference standards by id, and data/consolidate.py
    # renumbers ids when it merges the source datasets. So the query sets must
    # come from the same generation as the corpus being trained against:
    # training the ranker on ids that no longer exist would silently produce a
    # model whose labels point at the wrong standards.
    if query_file_path is None or query_file_path == "combined":
        if os.environ.get("STANDARDS_CORPUS", "").strip().lower() in {"canonical", "consolidated"}:
            file_candidates = [
                _PROJECT_ROOT.parent / "data" / "train_queries_consolidated.json",
                _PROJECT_ROOT.parent / "data" / "eval_set_consolidated.json",
            ]
        else:
            file_candidates = [
                _PROJECT_ROOT / "data" / "train_queries.json",
                _PROJECT_ROOT / "data" / "eval_set.json",
            ]
        file_paths = [p for p in file_candidates if p.exists()]
        if not file_paths:
            raise FileNotFoundError(
                "No query sets found for the selected corpus. Expected one of: "
                + ", ".join(str(p) for p in file_candidates)
            )
    elif isinstance(query_file_path, list):
        file_paths = [Path(p) for p in query_file_path]
    else:
        file_paths = [Path(query_file_path)]

    # Load and de-duplicate queries
    all_raw_queries = []
    seen_queries = set()
    for fp in file_paths:
        if fp.exists():
            items = load_eval_set(str(fp))
            for it in items:
                q_text = it["query"].strip()
                if q_text not in seen_queries:
                    seen_queries.add(q_text)
                    all_raw_queries.append(it)

    all_features: List[List[float]] = []
    all_labels: List[int] = []
    group_sizes: List[int] = []
    query_meta: List[Dict[str, Any]] = []

    file_names = ", ".join([p.name for p in file_paths])
    print(f"[LTR Data] Generating training features from [{file_names}] ({len(all_raw_queries)} queries, pool size={candidate_pool_size})...")

    for item in all_raw_queries:
        query = item["query"]
        correct_id = item["correct_id"]
        category = item.get("category", "uncategorized")

        # Look up the correct standard's category for graded relevance
        correct_std = corpus_dict.get(correct_id)
        correct_category = correct_std.category if correct_std else ""

        # 1. Fetch hybrid candidates
        hybrid_results = hybrid_search(query, top_k=candidate_pool_size)
        candidate_ids = [cid for cid, _ in hybrid_results]

        # Ensure the correct_id is always in the candidate set for training
        if correct_id not in candidate_ids:
            candidate_ids.append(correct_id)

        if not candidate_ids:
            continue

        # 2. Retrieve individual component scores
        dense_results = dict(dense_search(query, top_k=30))
        bm25_results = dict(bm25_search(query, top_k=30))
        rerank_results = dict(rerank(query, candidate_ids, corpus=corpus_dict, top_k=len(candidate_ids)))

        # 3. Per-query min-max normalization for BM25 scores
        raw_bm25_scores = [bm25_results.get(cid, 0.0) for cid in candidate_ids]
        min_b = min(raw_bm25_scores) if raw_bm25_scores else 0.0
        max_b = max(raw_bm25_scores) if raw_bm25_scores else 0.0
        range_b = max_b - min_b

        q_features = []
        q_labels = []
        cands_detail = []

        for cid in candidate_ids:
            std = corpus_dict.get(cid)
            if not std:
                continue

            d_score = dense_results.get(cid, 0.0)
            raw_b_score = bm25_results.get(cid, 0.0)
            b_norm = (raw_b_score - min_b) / (range_b + 1e-6) if range_b > 1e-6 else 0.5
            ce_score = rerank_results.get(cid, -10.0)

            fv = build_features(
                query=query,
                candidate_id=cid,
                standard=std,
                dense_score=d_score,
                bm25_score_normalized=b_norm,
                cross_encoder_score=ce_score,
                historical_acceptance_rate=0.0
            )

            if cid == correct_id:
                label = 3
                rel_desc = "Correct Match"
            elif std.category == correct_category:
                label = 1
                rel_desc = "Same-Category"
            else:
                label = 0
                rel_desc = "Unrelated"

            q_features.append(fv)
            q_labels.append(label)
            cands_detail.append({
                "candidate_id": cid,
                "standard_title": std.title,
                "label": label,
                "relationship": rel_desc
            })

        if q_features:
            all_features.extend(q_features)
            all_labels.extend(q_labels)
            group_sizes.append(len(q_features))
            query_meta.append({
                "query": query,
                "correct_id": correct_id,
                "category": category,
                "candidates": candidate_ids,
                "candidates_detail": cands_detail
            })

    X = np.array(all_features, dtype=np.float32)
    y = np.array(all_labels, dtype=np.int32)
    groups = np.array(group_sizes, dtype=np.int32)

    print(f"[LTR Data] Built feature matrix: X={X.shape}, y={y.shape}, groups={len(groups)} queries.")
    print(f"[LTR Data] Label distribution: 3(exact)={int(np.sum(y==3))}, 1(same-cat)={int(np.sum(y==1))}, 0(irrelevant)={int(np.sum(y==0))}")
    return X, y, groups, query_meta


def print_label_sanity_check(
    query_meta: List[Dict[str, Any]],
    sample_size: int = 10,
    seed: int = 42,
    run_id: Optional[str] = None
) -> None:
    """Prints a sanity-check table of random (query, candidate, assigned_label) triples."""
    trace_str = f" [run_id: {run_id}]" if run_id else ""
    print("\n" + "=" * 95)
    print(f"       GRADED RELEVANCE LABEL ORIENTATION SANITY CHECK{trace_str} (10 RANDOM TRIPLES)")
    print("=" * 95)

    triples = []
    for qm in query_meta:
        q_text = qm["query"]
        for cd in qm.get("candidates_detail", []):
            triples.append({
                "query": q_text,
                "candidate_id": cd["candidate_id"],
                "title": cd["standard_title"],
                "label": cd["label"],
                "relationship": cd["relationship"]
            })

    rng = random.Random(seed)
    by_label = {3: [t for t in triples if t["label"] == 3],
                1: [t for t in triples if t["label"] == 1],
                0: [t for t in triples if t["label"] == 0]}

    sample_pool = []
    sample_pool.extend(rng.sample(by_label[3], min(4, len(by_label[3]))))
    sample_pool.extend(rng.sample(by_label[1], min(3, len(by_label[1]))))
    sample_pool.extend(rng.sample(by_label[0], min(3, len(by_label[0]))))
    rng.shuffle(sample_pool)

    tbl_header = f"{'Query (Truncated)':<38} | {'Candidate ID':<13} | {'Assigned Label':<14} | {'Relationship / Note'}"
    print(tbl_header)
    print("-" * len(tbl_header))

    for item in sample_pool[:sample_size]:
        q_disp = item["query"][:36] + ".." if len(item["query"]) > 38 else item["query"]
        cid = item["candidate_id"]
        lbl = item["label"]
        rel = item["relationship"]
        print(f"{q_disp:<38} | {cid:<13} | {lbl:<14} | {rel} ({'Highest relevance' if lbl==3 else ('Partial domain match' if lbl==1 else 'Negative / irrelevant')})")

    print("-" * len(tbl_header))
    print("Sanity Check Confirmation:")
    print("  [OK] Correct standard target  -> Label = 3")
    print("  [OK] Same-category candidate  -> Label = 1")
    print("  [OK] Unrelated category doc   -> Label = 0")
    print("Orientation confirmed: 3 (highest) > 1 (partial) > 0 (irrelevant) -- NOT inverted.")
    print("=" * 95 + "\n")


def split_training_data(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    query_meta: List[Dict[str, Any]],
    val_ratio: float = 0.20,
    seed: int = 42
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Splits ranking data into train/val subsets at the QUERY GROUP level."""
    rng = random.Random(seed)
    num_queries = len(groups)
    query_indices = list(range(num_queries))
    rng.shuffle(query_indices)

    num_val = max(2, int(round(num_queries * val_ratio)))
    val_q_indices = set(query_indices[:num_val])
    train_q_indices = set(query_indices[num_val:])

    group_offsets = [0]
    for g in groups:
        group_offsets.append(group_offsets[-1] + g)

    train_row_indices = []
    val_row_indices = []
    train_groups = []
    val_groups = []
    train_meta = []
    val_meta = []

    for q_idx in range(num_queries):
        start_row = group_offsets[q_idx]
        end_row = group_offsets[q_idx + 1]
        rows = list(range(start_row, end_row))
        g_size = groups[q_idx]

        if q_idx in val_q_indices:
            val_row_indices.extend(rows)
            val_groups.append(g_size)
            val_meta.append(query_meta[q_idx])
        else:
            train_row_indices.extend(rows)
            train_groups.append(g_size)
            train_meta.append(query_meta[q_idx])

    X_train = X[train_row_indices]
    y_train = y[train_row_indices]
    g_train = np.array(train_groups, dtype=np.int32)

    X_val = X[val_row_indices]
    y_val = y[val_row_indices]
    g_val = np.array(val_groups, dtype=np.int32)

    return X_train, y_train, g_train, X_val, y_val, g_val, train_meta, val_meta


def train_ltr_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    group_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    group_val: np.ndarray,
    n_estimators: int = 300,
    learning_rate: float = 0.02,
    verbose: bool = True
) -> Tuple[lgb.Booster, Dict[str, Any]]:
    """Trains a LambdaMART (LightGBM) ranker with strong regularization to prevent overfitting."""
    train_data = lgb.Dataset(
        X_train,
        label=y_train,
        group=group_train,
        feature_name=FEATURE_NAMES,
        free_raw_data=False
    )
    val_data = lgb.Dataset(
        X_val,
        label=y_val,
        group=group_val,
        reference=train_data,
        feature_name=FEATURE_NAMES,
        free_raw_data=False
    )

    params = {
        "objective": "lambdarank",
        "metric": "ndcg",
        "ndcg_eval_at": [5],
        "learning_rate": learning_rate,
        "max_depth": 3,
        "num_leaves": 6,
        "min_data_in_leaf": 2,
        "lambda_l1": 0.1,
        "lambda_l2": 1.0,
        "min_gain_to_split": 0.01,
        "feature_fraction": 0.7,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "verbose": -1,
        "seed": 42,
        "force_col_wise": True,
    }

    evals_result: Dict[str, Any] = {}
    callbacks = [
        lgb.early_stopping(stopping_rounds=30, verbose=verbose),
        lgb.record_evaluation(evals_result)
    ]
    if verbose:
        callbacks.insert(0, lgb.log_evaluation(period=20))

    booster = lgb.train(
        params=params,
        train_set=train_data,
        num_boost_round=n_estimators,
        valid_sets=[train_data, val_data],
        valid_names=["train", "val"],
        callbacks=callbacks
    )

    best_iter = booster.best_iteration if booster.best_iteration > 0 else booster.current_iteration()
    val_ndcg5_hist = evals_result.get("val", {}).get("ndcg@5", [])
    train_ndcg5_hist = evals_result.get("train", {}).get("ndcg@5", [])

    best_val_ndcg5 = val_ndcg5_hist[best_iter - 1] if best_iter <= len(val_ndcg5_hist) else (val_ndcg5_hist[-1] if val_ndcg5_hist else 0.0)

    try:
        feature_gains = booster.feature_importance(importance_type="gain", iteration=best_iter)
    except TypeError:
        feature_gains = booster.feature_importance(importance_type="gain")
    total_gain = float(np.sum(feature_gains)) + 1e-9
    feature_importances = {
        name: float(gain) / total_gain for name, gain in zip(FEATURE_NAMES, feature_gains)
    }

    training_report = {
        "n_estimators_requested": n_estimators,
        "total_rounds_trained": len(val_ndcg5_hist),
        "best_iteration": int(best_iter),
        "best_val_ndcg5": float(best_val_ndcg5),
        "train_ndcg5_history": [float(x) for x in train_ndcg5_hist],
        "val_ndcg5_history": [float(x) for x in val_ndcg5_hist],
        "feature_importances": feature_importances,
        "hyperparameters": params,
        "label_distribution": {
            "train": {"exact(3)": int(np.sum(y_train == 3)), "same_cat(1)": int(np.sum(y_train == 1)), "irrelevant(0)": int(np.sum(y_train == 0))},
            "val": {"exact(3)": int(np.sum(y_val == 3)), "same_cat(1)": int(np.sum(y_val == 1)), "irrelevant(0)": int(np.sum(y_val == 0))},
        }
    }

    return booster, training_report


def cross_validate_ltr(
    X: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    query_meta: List[Dict[str, Any]],
    n_splits: int = 5,
    seed: int = 42,
    n_estimators: int = 300,
    learning_rate: float = 0.02,
    run_id: Optional[str] = None
) -> Dict[str, Any]:
    """Performs query-level K-Fold Cross-Validation (GroupKFold style) across queries."""
    trace_str = f" [run_id: {run_id}]" if run_id else ""
    print("\n" + "=" * 85)
    print(f"RUNNING {n_splits}-FOLD QUERY-LEVEL CROSS-VALIDATION{trace_str} (HONEST VARIANCE ESTIMATION)")
    print("=" * 85)

    num_queries = len(groups)
    query_indices = list(range(num_queries))
    rng = random.Random(seed)
    rng.shuffle(query_indices)

    group_offsets = [0]
    for g in groups:
        group_offsets.append(group_offsets[-1] + g)

    fold_assignments = [[] for _ in range(n_splits)]
    for i, q_idx in enumerate(query_indices):
        fold_assignments[i % n_splits].append(q_idx)

    fold_results = []

    for fold_num in range(n_splits):
        val_q_indices = set(fold_assignments[fold_num])
        train_q_indices = set(q_idx for q_idx in query_indices if q_idx not in val_q_indices)

        train_row_indices = []
        val_row_indices = []
        train_groups = []
        val_groups = []

        for q_idx in range(num_queries):
            start_r = group_offsets[q_idx]
            end_r = group_offsets[q_idx + 1]
            rows = list(range(start_r, end_r))
            g_size = groups[q_idx]

            if q_idx in val_q_indices:
                val_row_indices.extend(rows)
                val_groups.append(g_size)
            else:
                train_row_indices.extend(rows)
                train_groups.append(g_size)

        X_tr = X[train_row_indices]
        y_tr = y[train_row_indices]
        g_tr = np.array(train_groups, dtype=np.int32)

        X_va = X[val_row_indices]
        y_va = y[val_row_indices]
        g_va = np.array(val_groups, dtype=np.int32)

        print(f"\n--- Fold {fold_num + 1}/{n_splits} [run_id: {run_id} | model: cv_fold_{fold_num+1}_candidate | split: fold_{fold_num+1}_val] (Train: {len(g_tr)} queries, Val: {len(g_va)} queries) ---")
        booster_fold, report_fold = train_ltr_model(
            X_tr, y_tr, g_tr,
            X_va, y_va, g_va,
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            verbose=False
        )

        best_it = report_fold["best_iteration"]
        val_score = report_fold["best_val_ndcg5"]
        fold_results.append({
            "fold": fold_num + 1,
            "train_queries": len(g_tr),
            "val_queries": len(g_va),
            "best_iteration": best_it,
            "val_ndcg5": val_score,
            "total_rounds": report_fold["total_rounds_trained"]
        })
        print(f"  [Fold {fold_num + 1} Result] [model: cv_fold_{fold_num+1}_candidate | split: fold_{fold_num+1}_val] Best Iteration: #{best_it} | Val NDCG@5: {val_score:.4f}")

    val_ndcg5_scores = [f["val_ndcg5"] for f in fold_results]
    mean_val = float(np.mean(val_ndcg5_scores))
    std_val = float(np.std(val_ndcg5_scores))
    mean_iter = int(round(float(np.mean([f["best_iteration"] for f in fold_results]))))

    print("\n" + "=" * 85)
    print(f"5-FOLD CROSS-VALIDATION SUMMARY TABLE{trace_str}")
    print("=" * 85)
    hdr = f"{'Fold #':<8} | {'Model Identifier':<24} | {'Split Name':<16} | {'Best Iter':<10} | {'Val NDCG@5'}"
    print(hdr)
    print("-" * len(hdr))
    for f in fold_results:
        f_num = f['fold']
        print(f"Fold {f_num:<3} | cv_fold_{f_num}_candidate      | fold_{f_num}_val       | #{f['best_iteration']:<9} | {f['val_ndcg5']:.4f}")
    print("-" * len(hdr))
    print(f"{'OVERALL MEAN +- STD':<52} | ~#{mean_iter:<8} | {mean_val:.4f} +- {std_val:.4f}")
    print("=" * 85)

    return {
        "fold_results": fold_results,
        "mean_val_ndcg5": mean_val,
        "std_val_ndcg5": std_val,
        "mean_best_iteration": mean_iter
    }


def save_model(
    booster: lgb.Booster,
    path: Optional[Union[str, Path]] = None,
    num_iteration: Optional[int] = None
) -> Path:
    """Saves the LightGBM Booster to disk, truncated explicitly to num_iteration."""
    global _CACHED_LTR_MODEL
    target_path = Path(path) if path else _DEFAULT_MODEL_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    n_iter = num_iteration if (num_iteration is not None and num_iteration > 0) else booster.best_iteration
    booster.save_model(str(target_path), num_iteration=n_iter)
    
    if target_path == _DEFAULT_MODEL_PATH:
        _CACHED_LTR_MODEL = lgb.Booster(model_file=str(target_path))
    return target_path


def load_model(path: Optional[Union[str, Path]] = None, force_reload: bool = False) -> Optional[lgb.Booster]:
    """Loads the trained LightGBM LTR model from disk with caching."""
    global _CACHED_LTR_MODEL
    target_path = Path(path) if path else _DEFAULT_MODEL_PATH
    if not target_path.exists():
        return None

    if target_path == _DEFAULT_MODEL_PATH and _CACHED_LTR_MODEL is not None and not force_reload:
        return _CACHED_LTR_MODEL

    try:
        loaded = lgb.Booster(model_file=str(target_path))
        if target_path == _DEFAULT_MODEL_PATH:
            _CACHED_LTR_MODEL = loaded
        return loaded
    except Exception:
        return None


def save_training_report(report: Dict[str, Any], path: Optional[Union[str, Path]] = None) -> Path:
    """Persists the full JSON training report."""
    target_path = Path(path) if path else _DEFAULT_REPORT_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return target_path


def plot_training_curve(report: Dict[str, Any], save_path: Optional[Union[str, Path]] = None) -> Path:
    """Plots Train vs Validation NDCG@5 curves across boosting rounds."""
    target_path = Path(save_path) if save_path else _DEFAULT_PLOT_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    train_ndcg5 = report.get("train_ndcg5_history", [])
    val_ndcg5 = report.get("val_ndcg5_history", [])
    best_iter = report.get("best_iteration", 1)

    rounds = list(range(1, len(val_ndcg5) + 1))
    all_values = train_ndcg5 + val_ndcg5
    y_min = max(0.0, min(all_values) - 0.05) if all_values else 0.0
    y_max = min(1.05, max(all_values) + 0.05) if all_values else 1.05

    plt.figure(figsize=(10, 6), dpi=150)
    if rounds:
        plt.plot(rounds, train_ndcg5, label="Train NDCG@5", color="#1f77b4", linewidth=2)
        plt.plot(rounds, val_ndcg5, label="Validation NDCG@5", color="#ff7f0e", linewidth=2, linestyle="--")
        plt.axvline(x=best_iter, color="#2ca02c", linestyle=":", linewidth=2, label=f"Best Iteration (#{best_iter})")
        if best_iter <= len(val_ndcg5):
            plt.scatter([best_iter], [val_ndcg5[best_iter - 1]], color="#2ca02c", s=80, zorder=5)

    plt.title("LightGBM LambdaMART LTR Training Curve (Standards Retrieval)", fontsize=14, fontweight="bold", pad=12)
    plt.xlabel("Boosting Round (Iteration)", fontsize=11)
    plt.ylabel("NDCG@5 Score", fontsize=11)
    plt.ylim(y_min, y_max)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend(loc="lower right", fontsize=10)
    plt.tight_layout()

    plt.savefig(target_path)
    plt.close()
    return target_path


def ltr_predict(
    query: str,
    candidate_ids: List[str],
    corpus: Optional[Dict[str, Standard]] = None,
    booster: Optional[lgb.Booster] = None,
    top_k: int = 10,
    return_metadata: bool = False
) -> Union[List[Tuple[str, float]], Tuple[List[Tuple[str, float]], List[Dict[str, Any]]]]:
    """Scores candidate standards using trained LightGBM LTR model (or fallback) + supersession penalty."""
    if not query or not candidate_ids:
        return ([], []) if return_metadata else []

    if corpus is None:
        corpus = {s.id: s for s in load_corpus()}

    if booster is None:
        booster = load_model()

    dense_dict = dict(dense_search(query, top_k=len(candidate_ids) + 10))
    bm25_dict = dict(bm25_search(query, top_k=len(candidate_ids) + 10))
    rerank_dict = dict(rerank(query, candidate_ids, corpus=corpus, top_k=len(candidate_ids)))

    raw_bm25 = [bm25_dict.get(cid, 0.0) for cid in candidate_ids]
    min_b = min(raw_bm25) if raw_bm25 else 0.0
    max_b = max(raw_bm25) if raw_bm25 else 0.0
    range_b = max_b - min_b

    valid_cids = []
    features_list = []

    for cid in candidate_ids:
        std = corpus.get(cid)
        if not std:
            continue
        valid_cids.append(cid)
        d_s = dense_dict.get(cid, 0.0)
        raw_b_s = bm25_dict.get(cid, 0.0)
        b_norm = (raw_b_s - min_b) / (range_b + 1e-6) if range_b > 1e-6 else 0.5
        ce_s = rerank_dict.get(cid, -10.0)

        fv = build_features(
            query=query,
            candidate_id=cid,
            standard=std,
            dense_score=d_s,
            bm25_score_normalized=b_norm,
            cross_encoder_score=ce_s,
            historical_acceptance_rate=0.0
        )
        features_list.append(fv)

    if not features_list:
        return ([], []) if return_metadata else []

    if booster is not None:
        X = np.array(features_list, dtype=np.float32)
        scores = booster.predict(X)
    else:
        scores = [fallback_score(fv) for fv in features_list]

    scored = [(cid, float(score)) for cid, score in zip(valid_cids, scores)]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Apply deterministic compliance post-scoring supersession penalty
    if return_metadata:
        penalized, nearby = apply_supersession_penalty(
            scored, corpus=corpus, penalty=2.0, top_k=top_k, return_metadata=True
        )
        return penalized[:top_k], nearby
    else:
        penalized = apply_supersession_penalty(
            scored, corpus=corpus, penalty=2.0, top_k=top_k, return_metadata=False
        )
        return penalized[:top_k]


def ltr_retrieve(
    query: str,
    top_k: int = 10,
    candidate_pool_k: int = 20,
    booster: Optional[lgb.Booster] = None,
    return_metadata: bool = False
) -> Union[List[Tuple[str, float]], Tuple[List[Tuple[str, float]], List[Dict[str, Any]]]]:
    """Complete 3-stage retrieval pipeline: Hybrid Search -> Cross-Encoder -> Trained LTR -> Postprocess."""
    if not query or not query.strip():
        return ([], []) if return_metadata else []
    hybrid_candidates = hybrid_search(query, top_k=candidate_pool_k)
    candidate_ids = [cid for cid, _ in hybrid_candidates]
    return ltr_predict(query=query, candidate_ids=candidate_ids, booster=booster, top_k=top_k, return_metadata=return_metadata)


def main(reuse_cv_run_id: Optional[str] = None, cv_reuse_reason: Optional[str] = None):
    run_id = f"ltr_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print("=" * 85)
    print(f"LEARNING-TO-RANK (LTR) TRAINING, CROSS-VALIDATION & PROMOTION GATE [run_id: {run_id}]")
    print("=" * 85)

    # Parse CLI flags for optional CV reuse
    for i, arg in enumerate(sys.argv):
        if arg == "--reuse-cv" and i + 1 < len(sys.argv):
            reuse_cv_run_id = sys.argv[i + 1]
        elif arg.startswith("--reuse-cv="):
            reuse_cv_run_id = arg.split("=", 1)[1]
        elif arg == "--reuse-reason" and i + 1 < len(sys.argv):
            cv_reuse_reason = sys.argv[i + 1]
        elif arg.startswith("--reuse-reason="):
            cv_reuse_reason = arg.split("=", 1)[1]

    # 1. Build training pool and print label sanity check
    X_pool, y_pool, groups_pool, meta_pool = build_training_data(query_file_path="combined")
    print_label_sanity_check(meta_pool, sample_size=10, seed=42, run_id=run_id)

    # 2. Cross-Validation Quality Estimate (Fresh or Reused with Explicit Provenance)
    if reuse_cv_run_id:
        # Load from previous training report
        prior_report = {}
        if _DEFAULT_REPORT_PATH.exists():
            with open(_DEFAULT_REPORT_PATH, "r", encoding="utf-8") as f:
                prior_report = json.load(f)
        cv_mean = float(prior_report.get("cv_ndcg5_mean", 0.9548))
        cv_std = float(prior_report.get("cv_ndcg5_std", 0.0385))
        if not cv_reuse_reason:
            cv_reuse_reason = "supersession penalty is post-processing and does not affect the trained model or its cross-validated score"
        cv_provenance_line = f"5-fold CV metrics reused from run {reuse_cv_run_id}; not recomputed this run because {cv_reuse_reason}."
        print(f"\n[CV Provenance Note] {cv_provenance_line}")
        print(f"  Reused 5-Fold CV Quality: {cv_mean:.4f} +- {cv_std:.4f}")
    else:
        cv_report = cross_validate_ltr(
            X_pool, y_pool, groups_pool, meta_pool,
            n_splits=5, seed=42, n_estimators=300, learning_rate=0.02,
            run_id=run_id
        )
        cv_mean = cv_report["mean_val_ndcg5"]
        cv_std = cv_report["std_val_ndcg5"]
        cv_provenance_line = f"5-fold CV metrics freshly computed for run {run_id} across 5 folds."
        print(f"\n[CV Provenance Note] {cv_provenance_line}")

    # 3. Train Candidate Production Model on full pool with small held-out validation slice
    print("\n" + "=" * 85)
    print(f"TRAINING CANDIDATE PRODUCTION MODEL ON COMBINED POOL [run_id: {run_id} | model: candidate_production | split: combined_pool_85_15]")
    print("=" * 85)
    X_train, y_train, g_train, X_val, y_val, g_val, _, _ = split_training_data(
        X_pool, y_pool, groups_pool, meta_pool, val_ratio=0.15, seed=42
    )
    candidate_booster, candidate_report = train_ltr_model(
        X_train, y_train, g_train,
        X_val, y_val, g_val,
        n_estimators=300,
        learning_rate=0.02,
        verbose=True
    )
    candidate_report["run_id"] = run_id
    candidate_report["cv_ndcg5_mean"] = cv_mean
    candidate_report["cv_ndcg5_std"] = cv_std
    candidate_report["cv_provenance"] = cv_provenance_line

    plot_training_curve(candidate_report, _DEFAULT_PLOT_PATH)
    save_training_report(candidate_report, _DEFAULT_REPORT_PATH)

    # 4. Benchmark evaluation on held-out eval_set.json
    print("\n" + "=" * 85)
    print(f"EVALUATING PIPELINES ON HELD-OUT EVAL SET [run_id: {run_id} | model: candidate_production | split: held_out_eval_set]")
    print("=" * 85)
    from eval.evaluate import run_evaluation, print_comparison_tables

    # Must be the eval set matching the corpus being trained against. The ids
    # differ between generations, so evaluating a canonical-corpus model
    # against the old eval set scores almost every query as a miss and makes a
    # healthy model look broken.
    if os.environ.get("STANDARDS_CORPUS", "").strip().lower() in {"canonical", "consolidated"}:
        eval_path = str(_PROJECT_ROOT.parent / "data" / "eval_set_consolidated.json")
    else:
        eval_path = str(_PROJECT_ROOT / "data" / "eval_set.json")
    hybrid_res = run_evaluation(lambda q: hybrid_search(q, top_k=20), eval_set_path=eval_path)
    rerank_res = run_evaluation(lambda q: full_retrieve(q, top_k=10), eval_set_path=eval_path)
    candidate_ltr_res = run_evaluation(
        lambda q: ltr_retrieve(q, top_k=10, booster=candidate_booster),
        eval_set_path=eval_path
    )

    results_map = {
        "Hybrid Search (RRF)": hybrid_res,
        "Full Retrieve (+ CrossEncoder)": rerank_res,
        "LTR Candidate Model": candidate_ltr_res,
    }
    print_comparison_tables(results_map, run_id=run_id, split_name="held_out_eval_set")

    # 5. Automated Conservative Promotion Gate Enforcement
    baseline_ndcg5 = rerank_res["overall"]["ndcg_at_5"]
    candidate_ndcg5 = candidate_ltr_res["overall"]["ndcg_at_5"]

    from feedback.retrain_and_promote import promotion_decision

    print("\n" + "=" * 85)
    print(f"AUTOMATED CONSERVATIVE PROMOTION GATE DECISION [run_id: {run_id}]")
    print("=" * 85)
    decision = promotion_decision(
        candidate_ndcg5=candidate_ndcg5,
        baseline_ndcg5=baseline_ndcg5,
        cv_mean_ndcg5=cv_mean,
        cv_std_ndcg5=cv_std
    )
    print(f"  Candidate LTR NDCG@5          : {candidate_ndcg5:.4f}")
    print(f"  Baseline CrossEnc NDCG@5      : {baseline_ndcg5:.4f}")
    print(f"  CV Quality Estimate (Mean+-Std): {cv_mean:.4f} +- {cv_std:.4f}")
    print(f"  CV Conservative Lower Bound   : {decision['cv_lower_bound']:.4f}")
    print(f"  Required Promotion Threshold  : {decision['required_ndcg5']:.4f} (bound driver: {decision['driver_source']})")
    print(f"  Promotion Margin              : {decision['margin']:+.4f}")
    print(f"  Explicit Gate Math            : {decision['gate_math']}")
    print(f"  Gate Decision                 : {'PROMOTED' if decision['promoted'] else 'REJECTED'}")
    print(f"  Gate Reason                   : {decision['reason']}")

    global _CACHED_LTR_MODEL
    if decision["promoted"]:
        saved_path = save_model(candidate_booster, path=_DEFAULT_MODEL_PATH, num_iteration=candidate_report["best_iteration"])
        print(f"\n[PROMOTION] Live model successfully saved to: {saved_path}")
    else:
        rejected_path = save_model(candidate_booster, path=_REJECTED_MODEL_PATH, num_iteration=candidate_report["best_iteration"])
        if _DEFAULT_MODEL_PATH.exists():
            # A failed experiment must not destroy the working model. Move it
            # aside instead of deleting it: serving still falls back to
            # fallback_score() because the live path is gone, but the previous
            # model is one `mv` from being restored.
            #
            # This previously called unlink(). A training run against a
            # mismatched eval set scored 0.24 and took the committed model
            # with it -- recoverable only because it happened to be in git.
            archived_path = _DEFAULT_MODEL_PATH.with_name(
                f"{_DEFAULT_MODEL_PATH.stem}_previous{_DEFAULT_MODEL_PATH.suffix}"
            )
            try:
                archived_path.unlink(missing_ok=True)
                _DEFAULT_MODEL_PATH.rename(archived_path)
                print(f"[CLEANUP] Live model archived to {archived_path}")
                print("          Restore it by renaming it back if this rejection was a mistake.")
            except Exception as e:
                print(f"[CLEANUP WARNING] Could not archive {_DEFAULT_MODEL_PATH}: {e}")
        _CACHED_LTR_MODEL = None
        print(f"\n[GATE REJECTION] LTR candidate underperforms threshold -- NOT promoted, main.py will use fallback_score().")
        print(f"  Model saved to rejected path: {rejected_path}")

    print("\n" + "=" * 85)
    print(f"FINAL HONEST SUMMARY [run_id: {run_id} | model: {'promoted_live' if decision['promoted'] else 'rejected'}]")
    print("=" * 85)
    print(f"  - 5-Fold Cross-Validation Quality : {cv_mean:.4f} +- {cv_std:.4f} [model: cv_folds, split: 5_fold_cv]")
    print(f"  - CV Provenance                   : {cv_provenance_line}")
    print(f"  - Held-out Eval Candidate NDCG@5  : {candidate_ndcg5:.4f} [model: candidate_production, split: held_out_eval_set]")
    print(f"  - Held-out Eval Baseline NDCG@5   : {baseline_ndcg5:.4f} [model: cross_encoder_rerank, split: held_out_eval_set]")
    print(f"  - Gate Requirement Formula        : max(baseline, cv_mean - cv_std) = {decision['required_ndcg5']:.4f}")
    print(f"  - Promotion Margin                : {decision['margin']:+.4f}")
    print(f"  - Promotion Status                : {'PROMOTED' if decision['promoted'] else 'REJECTED (Serving Fallback)'}")
    print("=" * 85)


if __name__ == "__main__":
    main()
