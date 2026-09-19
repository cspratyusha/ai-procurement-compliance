"""Scheduled Retraining & Promotion Pipeline for Standards-Retrieval (Part 6, Stage D).

This module implements the complete closed loop:
    Logged Interactions -> Retrained LTR Model -> Rigorous Evaluation -> Promotion Gate.

Design & Safety Guarantees:
---------------------------
1. Candidate Isolation: Candidate models are always trained and written to candidate_model_path
   (e.g., models/ltr_model_candidate.txt) — NEVER directly overwriting the live production model.
2. Cold-Start / Insufficient Data Guard: If there are fewer than min_queries (default 10)
   distinct queries in the training data, the cycle aborts early to prevent near-empty logs
   from producing a degenerate model.
3. Fair Held-Out Evaluation: Both candidate and currently deployed models are evaluated
   on the exact same benchmark (data/eval_set.json) using NDCG@5.
4. Promotion Gate (Zero Silent Regressions):
   - First run (no current model): Automatic promotion.
   - Subsequent runs: Candidate must achieve candidate_ndcg5 >= current_ndcg5 (equal-or-better).
   - If candidate passes: candidate_model_path is copied over current_model_path.
   - If candidate fails: current model is left completely untouched, and candidate is discarded.
5. Persistent Audit Trail: Every run records its before/after scores, category breakdowns,
   and promotion decision to data/retraining_history.jsonl.

Production Scheduling Note:
---------------------------
In a production deployment, this closed feedback loop would be scheduled via an orchestrator
such as Airflow (DAG scheduled weekly/nightly), a cron job, or Windows Task Scheduler calling
`run_retraining_cycle()`. For demo, testing, and continuous deployment verification, running
this script directly or invoking the function programmatically provides the exact same contract.
"""
import copy
import json
import shutil
import sys
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Union, List

import numpy as np
import lightgbm as lgb

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# --- Backward Compatibility Gates (Preserved for ltr/train.py) ---
# Defined at the top of the module to eliminate circular import dependencies

def should_promote(
    candidate_ndcg5: float,
    baseline_ndcg5: float,
    cv_mean_ndcg5: Optional[float] = None,
    cv_std_ndcg5: Optional[float] = None,
    min_improvement: float = 0.0
) -> bool:
    """Legacy helper: conservative promotion criterion against CrossEncoder baseline."""
    if cv_mean_ndcg5 is not None and cv_std_ndcg5 is not None:
        cv_lower_bound = cv_mean_ndcg5 - cv_std_ndcg5
        required = max(baseline_ndcg5, cv_lower_bound)
    else:
        required = baseline_ndcg5
    return candidate_ndcg5 >= (required + min_improvement)


def promotion_decision(
    candidate_ndcg5: float,
    baseline_ndcg5: float,
    cv_mean_ndcg5: Optional[float] = None,
    cv_std_ndcg5: Optional[float] = None,
    min_improvement: float = 0.0
) -> Dict[str, Any]:
    """Legacy helper: structured promotion decision against CrossEncoder baseline."""
    if cv_mean_ndcg5 is not None and cv_std_ndcg5 is not None:
        cv_lower_bound = cv_mean_ndcg5 - cv_std_ndcg5
        required_ndcg5 = max(baseline_ndcg5, cv_lower_bound)
        driver_source = "baseline" if baseline_ndcg5 >= cv_lower_bound else "cv_lower_bound"
        gate_math_str = (
            f"Gate: candidate NDCG@5={candidate_ndcg5:.4f} vs "
            f"required=max(baseline={baseline_ndcg5:.4f}, cv_mean-std={cv_lower_bound:.4f})={required_ndcg5:.4f}"
        )
    else:
        cv_lower_bound = None
        required_ndcg5 = baseline_ndcg5
        driver_source = "baseline_only"
        gate_math_str = f"Gate: candidate NDCG@5={candidate_ndcg5:.4f} vs required=baseline={baseline_ndcg5:.4f}"

    promote = candidate_ndcg5 >= (required_ndcg5 + min_improvement)
    margin = candidate_ndcg5 - required_ndcg5

    if promote:
        reason = f"{gate_math_str} -> PROMOTED (margin {margin:+.4f}) to live model."
    else:
        reason = f"{gate_math_str} -> NOT promoted (margin {margin:+.4f}), main.py will use fallback_score()."

    return {
        "promoted": promote,
        "candidate_ndcg5": candidate_ndcg5,
        "baseline_ndcg5": baseline_ndcg5,
        "cv_mean_ndcg5": cv_mean_ndcg5,
        "cv_std_ndcg5": cv_std_ndcg5,
        "cv_lower_bound": cv_lower_bound,
        "required_ndcg5": required_ndcg5,
        "driver_source": driver_source,
        "margin": margin,
        "min_improvement": min_improvement,
        "gate_math": gate_math_str,
        "reason": reason,
    }


logger = logging.getLogger("standards-retrieval.feedback.retrain")
logging.basicConfig(level=logging.INFO)

from data_loader import load_corpus
from feedback.build_training_set import load_logs, logs_to_training_data
from ltr.train import train_ltr_model, ltr_retrieve
from eval.evaluate import run_evaluation

_DEFAULT_LOGS_PATH = _PROJECT_ROOT / "data" / "interaction_logs.jsonl"
_DEFAULT_EVAL_PATH = _PROJECT_ROOT / "data" / "eval_set.json"
_DEFAULT_CURRENT_MODEL_PATH = _PROJECT_ROOT / "models" / "ltr_model.txt"
_DEFAULT_CANDIDATE_MODEL_PATH = _PROJECT_ROOT / "models" / "ltr_model_candidate.txt"
_DEFAULT_HISTORY_PATH = _PROJECT_ROOT / "data" / "retraining_history.jsonl"


def _resolve_path(path: Union[str, Path]) -> Path:
    """Resolves path relative to project root if not absolute."""
    p = Path(path)
    return p if p.is_absolute() else _PROJECT_ROOT / p


def _json_serializable(obj: Any) -> Any:
    """Recursively converts numpy numbers and objects into JSON-serializable primitives."""
    if isinstance(obj, bool):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_serializable(x) for x in obj]
    return obj


# --- Audit Log Helper ---

def log_retraining_run(
    result: Dict[str, Any],
    history_path: Union[str, Path] = _DEFAULT_HISTORY_PATH
) -> Path:
    """Appends the retraining outcome record as a JSON line to the persistent audit log.
    
    Args:
        result: Outcome dictionary returned by run_retraining_cycle().
        history_path: Target JSONL path (defaults to data/retraining_history.jsonl).
        
    Returns:
        Resolved Path to the history file.
    """
    target = _resolve_path(history_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Compact audit entry without voluminous per-query dumps
    audit_entry = {
        "timestamp": result.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "promoted": result.get("promoted", False),
        "reason": result.get("reason", ""),
        "distinct_queries": result.get("distinct_queries", 0),
        "candidate_ndcg5": result.get("candidate_ndcg5"),
        "current_ndcg5": result.get("current_ndcg5"),
        "candidate_p1": result.get("candidate_eval", {}).get("overall", {}).get("precision_at_1") if result.get("candidate_eval") else None,
        "current_p1": result.get("current_eval", {}).get("overall", {}).get("precision_at_1") if result.get("current_eval") else None,
        "category_ndcg5": {
            "candidate": {
                cat: metrics.get("ndcg_at_5")
                for cat, metrics in result.get("candidate_eval", {}).get("by_category", {}).items()
            } if result.get("candidate_eval") else {},
            "current": {
                cat: metrics.get("ndcg_at_5")
                for cat, metrics in result.get("current_eval", {}).get("by_category", {}).items()
            } if result.get("current_eval") else {},
        }
    }

    clean_dict = _json_serializable(audit_entry)
    with open(target, "a", encoding="utf-8") as f:
        f.write(json.dumps(clean_dict, ensure_ascii=False) + "\n")

    logger.info(f"[RetrainAudit] Appended retraining outcome to '{target}'.")
    return target


# --- Retraining & Promotion Pipeline Core ---

def run_retraining_cycle(
    logs_path: str = "data/interaction_logs.jsonl",
    eval_set_path: str = "data/eval_set.json",
    current_model_path: str = "models/ltr_model.txt",
    candidate_model_path: str = "models/ltr_model_candidate.txt",
    min_queries: int = 10,
    verbose: bool = True
) -> Dict[str, Any]:
    """Executes the closed-loop retraining and promotion gate.
    
    Steps:
      1. Loads logs via load_logs() and builds (X, y, group_sizes) via logs_to_training_data().
      2. If distinct queries < min_queries (default 10), aborts early with reason='insufficient_data'.
      3. Trains candidate model via train_ltr_model(), saving to candidate_model_path.
      4. Evaluates candidate model on eval_set_path via run_evaluation(), measuring NDCG@5.
      5. Evaluates currently deployed model on eval_set_path for fair comparison.
         If no current model exists, triggers automatic promotion.
      6. Promotion Gate: if candidate NDCG@5 >= current NDCG@5 (equal-or-better), copies candidate
         over current_model_path; else leaves current in place and discards candidate.
      7. Returns structured report dictionary with scores, decision, and ISO timestamp.
      
    Args:
        logs_path: Path to interaction logs JSONL.
        eval_set_path: Path to evaluation benchmark JSON.
        current_model_path: Path to live production LTR model.
        candidate_model_path: Path for candidate LTR model artifact.
        min_queries: Minimum number of distinct query groups required to proceed with retraining.
        verbose: Whether to print progress logs.
        
    Returns:
        Dictionary containing decision outcome, NDCG@5 scores, evaluation details, and timestamp.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    logs_p = _resolve_path(logs_path)
    eval_p = _resolve_path(eval_set_path)
    curr_p = _resolve_path(current_model_path)
    cand_p = _resolve_path(candidate_model_path)

    if verbose:
        logger.info("[RetrainCycle] Starting retraining cycle...")
        logger.info(f"  Logs Path           : {logs_p}")
        logger.info(f"  Eval Set Path       : {eval_p}")
        logger.info(f"  Current Model Path  : {curr_p}")
        logger.info(f"  Candidate Model Path: {cand_p}")

    # 1. Load interaction logs
    logs = load_logs(str(logs_p), verify_leakage=True)
    if not logs:
        logger.warning("[RetrainCycle] No logs loaded. Aborting retraining.")
        return {
            "promoted": False,
            "reason": "insufficient_data",
            "distinct_queries": 0,
            "timestamp": now_iso
        }

    # Build group-structured training data
    corpus = {s.id: s for s in load_corpus()}
    X, y, group_sizes = logs_to_training_data(logs, corpus=corpus)
    num_queries = len(group_sizes)

    # 2. Distinct queries guard: abort if insufficient data
    if num_queries < min_queries:
        logger.warning(
            f"[RetrainCycle] Distinct queries count ({num_queries}) is below minimum threshold ({min_queries}). "
            "Aborting retraining to guard against degenerate models."
        )
        return {
            "promoted": False,
            "reason": "insufficient_data",
            "distinct_queries": int(num_queries),
            "timestamp": now_iso
        }

    # 3. Train candidate model on interaction data
    # Query-group level split: 80% train, 20% val (minimum 2 val groups)
    val_ratio = 0.20
    val_count = max(2, int(round(num_queries * val_ratio)))
    rng = random.Random(42)
    query_indices = list(range(num_queries))
    rng.shuffle(query_indices)
    val_q_indices = set(query_indices[:val_count])

    group_offsets = [0]
    for g in group_sizes:
        group_offsets.append(group_offsets[-1] + int(g))

    train_rows: List[int] = []
    val_rows: List[int] = []
    train_groups: List[int] = []
    val_groups: List[int] = []

    for q_idx in range(num_queries):
        start_r = group_offsets[q_idx]
        end_r = group_offsets[q_idx + 1]
        rows = list(range(start_r, end_r))
        g_sz = int(group_sizes[q_idx])

        if q_idx in val_q_indices:
            val_rows.extend(rows)
            val_groups.append(g_sz)
        else:
            train_rows.extend(rows)
            train_groups.append(g_sz)

    X_train, y_train = X[train_rows], y[train_rows]
    X_val, y_val = X[val_rows], y[val_rows]
    g_train = np.array(train_groups, dtype=np.int32)
    g_val = np.array(val_groups, dtype=np.int32)

    if verbose:
        logger.info(f"[RetrainCycle] Training candidate model ({len(g_train)} train queries, {len(g_val)} val queries)...")

    booster, _ = train_ltr_model(
        X_train, y_train, g_train,
        X_val, y_val, g_val,
        n_estimators=300,
        learning_rate=0.02,
        verbose=False
    )

    # Save to candidate model path (never overwrite current directly!)
    cand_p.parent.mkdir(parents=True, exist_ok=True)
    n_iter = booster.best_iteration if booster.best_iteration > 0 else booster.current_iteration()
    booster.save_model(str(cand_p), num_iteration=n_iter)
    if verbose:
        logger.info(f"[RetrainCycle] Candidate model saved to '{cand_p}'.")

    # 4. Evaluate candidate model on eval_set
    cand_booster = lgb.Booster(model_file=str(cand_p))
    candidate_eval = run_evaluation(
        lambda q: ltr_retrieve(q, booster=cand_booster, top_k=10),
        eval_set_path=str(eval_p)
    )
    candidate_ndcg5 = float(candidate_eval["overall"]["ndcg_at_5"])

    # 5. Evaluate currently deployed model on the same eval_set
    current_exists = curr_p.exists()
    if not current_exists:
        current_eval = None
        current_ndcg5 = None
        if verbose:
            logger.info("[RetrainCycle] No current model found on disk. First-run automatic promotion will apply.")
    else:
        curr_booster = lgb.Booster(model_file=str(curr_p))
        current_eval = run_evaluation(
            lambda q: ltr_retrieve(q, booster=curr_booster, top_k=10),
            eval_set_path=str(eval_p)
        )
        current_ndcg5 = float(current_eval["overall"]["ndcg_at_5"])

    # 6. Promotion Gate: equal-or-better (candidate_ndcg5 >= current_ndcg5)
    if not current_exists:
        promoted = True
        decision_reason = "first_run_auto_promotion"
    elif candidate_ndcg5 >= current_ndcg5:
        promoted = True
        decision_reason = (
            f"candidate_equal_or_better: candidate NDCG@5 ({candidate_ndcg5:.4f}) >= "
            f"current NDCG@5 ({current_ndcg5:.4f}) (margin: {candidate_ndcg5 - current_ndcg5:+.4f})"
        )
    else:
        promoted = False
        decision_reason = (
            f"candidate_worse: candidate NDCG@5 ({candidate_ndcg5:.4f}) < "
            f"current NDCG@5 ({current_ndcg5:.4f}) (margin: {candidate_ndcg5 - current_ndcg5:+.4f})"
        )

    # Execute promotion action
    if promoted:
        curr_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cand_p, curr_p)
        if verbose:
            logger.info(f"[RetrainCycle] Model PROMOTED: Copied candidate '{cand_p}' over live '{curr_p}'.")
    else:
        if cand_p.exists():
            try:
                cand_p.unlink()
            except Exception as e:
                logger.warning(f"[RetrainCycle] Could not remove rejected candidate file '{cand_p}': {e}")
        if verbose:
            logger.info(f"[RetrainCycle] Model REJECTED: Left current model at '{curr_p}' untouched.")

    # 7. Construct and return result dictionary
    result = {
        "promoted": promoted,
        "reason": decision_reason,
        "timestamp": now_iso,
        "distinct_queries": int(num_queries),
        "candidate_ndcg5": candidate_ndcg5,
        "current_ndcg5": current_ndcg5,
        "candidate_eval": candidate_eval,
        "current_eval": current_eval,
        "candidate_model_path": str(cand_p),
        "current_model_path": str(curr_p),
    }

    return result


def print_comparison_table(result: Dict[str, Any]) -> None:
    """Prints a clear before/after comparison table broken down by categories and gate decision."""
    print("\n" + "=" * 85)
    print("           STANDARDS RETRAINING & PROMOTION PIPELINE REPORT")
    print("=" * 85)
    print(f"Timestamp           : {result.get('timestamp')}")
    print(f"Distinct Queries    : {result.get('distinct_queries')}")
    print(f"Promotion Decision  : {'PROMOTED' if result.get('promoted') else 'REJECTED'}")
    print(f"Reason Details      : {result.get('reason')}")
    print("-" * 85)

    cand_ov = result.get("candidate_eval", {}).get("overall", {}) if result.get("candidate_eval") else {}
    curr_ov = result.get("current_eval", {}).get("overall", {}) if result.get("current_eval") else {}

    c_p1 = f"{cand_ov.get('precision_at_1', 0.0) * 100:.1f}%" if cand_ov else "N/A"
    curr_p1 = f"{curr_ov.get('precision_at_1', 0.0) * 100:.1f}%" if curr_ov else "N/A"
    c_n5 = f"{cand_ov.get('ndcg_at_5', 0.0):.4f}" if cand_ov else "N/A"
    curr_n5 = f"{curr_ov.get('ndcg_at_5', 0.0):.4f}" if curr_ov else "N/A"

    print("\n--- [1] OVERALL PERFORMANCE COMPARISON ---")
    ov_header = f"{'Metric':<25} | {'Current Model':<18} | {'Candidate Model':<18} | {'Delta':<12}"
    print(ov_header)
    print("-" * len(ov_header))

    # NDCG@5 row
    cand_ndcg = result.get("candidate_ndcg5")
    curr_ndcg = result.get("current_ndcg5")
    delta_str = f"{(cand_ndcg - curr_ndcg):+.4f}" if (cand_ndcg is not None and curr_ndcg is not None) else "N/A"
    print(f"{'NDCG@5 (Primary Gate)':<25} | {curr_n5:<18} | {c_n5:<18} | {delta_str:<12}")
    print(f"{'Precision@1 (Top-1)':<25} | {curr_p1:<18} | {c_p1:<18} | {'--':<12}")
    print("-" * len(ov_header))

    # Category breakdown
    print("\n--- [2] PERFORMANCE BREAKDOWN BY QUERY DIFFICULTY CATEGORY ---")
    cat_header = f"{'Category':<22} | {'Current NDCG@5':<18} | {'Candidate NDCG@5':<18} | {'Delta':<12}"
    print(cat_header)
    print("-" * len(cat_header))

    all_categories = ["easy", "hard_duplicate", "hard_identifier", "use_case_only"]
    cand_cats = result.get("candidate_eval", {}).get("by_category", {}) if result.get("candidate_eval") else {}
    curr_cats = result.get("current_eval", {}).get("by_category", {}) if result.get("current_eval") else {}

    for cat in all_categories:
        c_score = cand_cats.get(cat, {}).get("ndcg_at_5")
        cur_score = curr_cats.get(cat, {}).get("ndcg_at_5")

        cur_str = f"{cur_score:.4f}" if cur_score is not None else "N/A"
        cand_str = f"{c_score:.4f}" if c_score is not None else "N/A"
        d_str = f"{(c_score - cur_score):+.4f}" if (c_score is not None and cur_score is not None) else "N/A"

        print(f"{cat:<22} | {cur_str:<18} | {cand_str:<18} | {d_str:<12}")

    print("=" * 85)
    print(f"Final Decision: promoted={result.get('promoted')} -> {'Model deployed to production.' if result.get('promoted') else 'Candidate discarded, production safe.'}\n")


def main():
    """Runs a complete retraining and promotion cycle and logs the outcome."""
    print("=" * 85)
    print("     STANDARDS RETRAINING & PROMOTION PIPELINE (PART 6, STAGE D)")
    print("=" * 85)

    result = run_retraining_cycle(
        logs_path=str(_DEFAULT_LOGS_PATH),
        eval_set_path=str(_DEFAULT_EVAL_PATH),
        current_model_path=str(_DEFAULT_CURRENT_MODEL_PATH),
        candidate_model_path=str(_DEFAULT_CANDIDATE_MODEL_PATH),
        min_queries=10,
        verbose=True
    )

    # Log retraining run to persistent history
    log_retraining_run(result, history_path=_DEFAULT_HISTORY_PATH)

    # Print executive comparison report
    print_comparison_table(result)


if __name__ == "__main__":
    main()
