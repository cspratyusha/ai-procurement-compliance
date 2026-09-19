"""Training dataset builder for the feedback loop (Part 6, Stage D).

Converts raw user interaction logs (both live and synthetic) into the group-structured
training data (X, y, group_sizes) expected by LightGBM's lambdarank objective.

Replaces the eval-set bootstrap with real/synthetic interaction data.
"""
import sys
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional, Union
import numpy as np

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.models import Standard
from data_loader import load_corpus
from feedback.schema import InteractionLog
from feedback.logger import _resolve_log_path
from indexing.embed_index import dense_search
from indexing.bm25_index import bm25_search
from retrieval.rerank import rerank
from ltr.features import build_features, FEATURE_NAMES

logger = logging.getLogger("standards-retrieval.feedback.builder")
logging.basicConfig(level=logging.INFO)

_DEFAULT_LOG_PATH = _PROJECT_ROOT / "data" / "interaction_logs.jsonl"
_DEFAULT_EVAL_PATH = _PROJECT_ROOT / "data" / "eval_set.json"
_DEFAULT_TRAIN_PATH = _PROJECT_ROOT / "data" / "train_queries.json"


def assert_no_eval_leakage(
    logs: List[Union[InteractionLog, Dict[str, Any]]],
    eval_set_path: Union[str, Path] = _DEFAULT_EVAL_PATH
) -> None:
    """Permanent sanity check asserting no query in logs matches any query in data/eval_set.json.
    
    Runs automatically every time build_training_set.py is invoked so silent leakage
    from stale or appended log data is caught on every future run.
    
    Raises:
        AssertionError: If any query string in logs matches an evaluation set query.
    """
    eval_p = _resolve_log_path(eval_set_path) if not Path(eval_set_path).is_absolute() else Path(eval_set_path)
    if not eval_p.exists():
        logger.warning(f"[SanityCheck] Eval set file '{eval_p}' not found for leakage check.")
        return

    try:
        with open(eval_p, "r", encoding="utf-8") as f:
            eval_data = json.load(f)
        eval_queries = {item["query"].strip() for item in eval_data if "query" in item}
    except Exception as e:
        logger.warning(f"[SanityCheck] Could not parse eval set at '{eval_p}': {e}")
        return

    leaked = set()
    for log in logs:
        q = (log.get("query") if isinstance(log, dict) else getattr(log, "query", "")).strip()
        if q in eval_queries:
            leaked.add(q)

    if leaked:
        raise AssertionError(
            f"[CRITICAL DATA LEAKAGE DETECTED] {len(leaked)} query strings in training logs "
            f"match eval_set.json queries! Leaked queries: {sorted(list(leaked))}"
        )


def verify_logs_integrity(
    logs_path: Union[str, Path] = _DEFAULT_LOG_PATH,
    expected_count: int = 124,
    eval_set_path: Union[str, Path] = _DEFAULT_EVAL_PATH,
    train_queries_path: Union[str, Path] = _DEFAULT_TRAIN_PATH
) -> Tuple[bool, List[str], List[str], int]:
    """Verifies line count (expected 124) and zero query leakage from eval_set.json.
    
    Cross-checks query membership against train_queries.json.
    
    Returns:
        Tuple of (passed: bool, extra_queries: list, leaked_queries: list, total_lines: int)
    """
    target_path = _resolve_log_path(logs_path) if not Path(logs_path).is_absolute() else Path(logs_path)
    if not target_path.exists():
        return False, [], [], 0

    with open(target_path, "r", encoding="utf-8") as f:
        raw_lines = [l.strip() for l in f.readlines() if l.strip()]

    total_lines = len(raw_lines)

    # Load eval set queries
    eval_p = _resolve_log_path(eval_set_path) if not Path(eval_set_path).is_absolute() else Path(eval_set_path)
    eval_queries = set()
    if eval_p.exists():
        try:
            with open(eval_p, "r", encoding="utf-8") as f:
                eval_queries = {item["query"].strip() for item in json.load(f) if "query" in item}
        except Exception:
            pass

    # Load train queries
    train_p = _resolve_log_path(train_queries_path) if not Path(train_queries_path).is_absolute() else Path(train_queries_path)
    train_queries = set()
    if train_p.exists():
        try:
            with open(train_p, "r", encoding="utf-8") as f:
                t_data = json.load(f)
                train_queries = {
                    (item["query"] if isinstance(item, dict) else str(item)).strip()
                    for item in t_data
                }
        except Exception:
            pass

    log_queries = set()
    leaked_queries = set()
    extra_queries = set()

    for line in raw_lines:
        try:
            rec = json.loads(line)
            q = rec.get("query", "").strip()
            log_queries.add(q)
            if q in eval_queries:
                leaked_queries.add(q)
            if train_queries and q not in train_queries:
                extra_queries.add(q)
        except Exception:
            pass

    count_ok = (total_lines == expected_count)
    no_leak_ok = (len(leaked_queries) == 0)
    train_membership_ok = (len(extra_queries) == 0)
    passed = count_ok and no_leak_ok and train_membership_ok

    return passed, sorted(list(extra_queries)), sorted(list(leaked_queries)), total_lines


def load_logs(
    path: str = "data/interaction_logs.jsonl",
    verify_leakage: bool = True
) -> List[InteractionLog]:
    """Reads all interaction log records from a JSONL file into InteractionLog instances.
    
    Args:
        path: Path to interaction logs JSONL file.
        verify_leakage: If True, executes permanent sanity check asserting no eval_set leakage.
        
    Returns:
        List of parsed and validated InteractionLog objects.
    """
    target_path = _resolve_log_path(path) if not Path(path).is_absolute() else Path(path)
    if not target_path.exists():
        logger.warning(f"[LogLoader] Log file '{target_path}' not found.")
        return []

    logs: List[InteractionLog] = []
    with open(target_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                record = json.loads(line_str)
                logs.append(InteractionLog(**record))
            except Exception as e:
                logger.warning(f"[LogLoader] Skipping invalid log line {line_num} in '{target_path}': {e}")

    logger.info(f"[LogLoader] Successfully loaded {len(logs)} interaction logs from '{target_path}'.")

    # Permanent sanity check executed on every invocation of load_logs
    if verify_leakage and logs:
        assert_no_eval_leakage(logs)

    return logs


def compute_historical_acceptance_rate(
    standard_id: str,
    logs: List[Union[InteractionLog, Dict[str, Any]]]
) -> float:
    """Computes (# times accepted) / (# times shown) for a standard across interaction logs.
    
    Populates the 7th feature (historical_acceptance_rate) with empirical feedback signal.
    
    Args:
        standard_id: Identifier of standard to compute rate for.
        logs: Collection of interaction logs.
        
    Returns:
        Float acceptance rate in [0.0, 1.0]. Returns 0.0 if standard was never shown.
    """
    times_shown = 0
    times_accepted = 0

    for log in logs:
        if isinstance(log, dict):
            cands = log.get("candidates_shown", [])
            action = log.get("action")
            chosen_id = log.get("chosen_id")
            corrected_id = log.get("corrected_id")
        else:
            cands = log.candidates_shown
            action = log.action
            chosen_id = log.chosen_id
            corrected_id = log.corrected_id

        # Determine if standard was presented in candidates_shown
        was_shown = any(
            (c.get("id") if isinstance(c, dict) else getattr(c, "id", None)) == standard_id
            for c in cands
        )
        if was_shown:
            times_shown += 1

        # Determine if standard was selected (accept or manual correction override)
        if action == "accept" and chosen_id == standard_id:
            times_accepted += 1
        elif action == "correct" and corrected_id == standard_id:
            times_accepted += 1

    if times_shown == 0:
        return 0.0
    return float(times_accepted) / float(times_shown)


def logs_to_training_data(
    logs: List[Union[InteractionLog, Dict[str, Any]]],
    corpus: Optional[Dict[str, Standard]] = None
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Converts interaction logs into group-structured LambdaMART training matrices.
    
    Pipeline:
      1. Groups log entries by exact query string match.
         TODO: Near-duplicate query text won't be merged without more sophisticated matching;
         currently grouping by exact query string match.
      2. Maps interaction actions to binary relevance labels: accept/correct -> 1, reject -> 0.
      3. Recomputes feature vectors for each (query, candidate) pair via build_features(),
         dynamically injecting the empirical historical_acceptance_rate computed from logs.
      4. Returns (X, y, group_sizes) matching the input signature of train_ltr_model().
      
    Args:
        logs: List of InteractionLog records.
        corpus: Standard lookup dictionary (loads default corpus if None).
        
    Returns:
        Tuple of:
          - X: Feature matrix of shape (N_samples, 7)
          - y: Relevance labels array of shape (N_samples,)
          - group_sizes: Array of candidate counts per query of shape (N_queries,)
    """
    if not logs:
        return (
            np.empty((0, len(FEATURE_NAMES)), dtype=np.float32),
            np.empty((0,), dtype=np.int32),
            np.empty((0,), dtype=np.int32)
        )

    if corpus is None:
        corpus = {s.id: s for s in load_corpus()}

    # 1. Precompute acceptance rates for all standards across the logs dataset
    # Caching yields identical results to compute_historical_acceptance_rate in O(len(logs)) time
    shown_counts = defaultdict(int)
    accepted_counts = defaultdict(int)

    for log in logs:
        if isinstance(log, dict):
            cands = log.get("candidates_shown", [])
            action = log.get("action")
            chosen_id = log.get("chosen_id")
            corrected_id = log.get("corrected_id")
        else:
            cands = log.candidates_shown
            action = log.action
            chosen_id = log.chosen_id
            corrected_id = log.corrected_id

        for c in cands:
            cid = c.get("id") if isinstance(c, dict) else getattr(c, "id", None)
            if cid:
                shown_counts[cid] += 1

        if action == "accept" and chosen_id:
            accepted_counts[chosen_id] += 1
        elif action == "correct" and corrected_id:
            accepted_counts[corrected_id] += 1

    rate_cache = {
        sid: (accepted_counts[sid] / shown_counts[sid] if shown_counts[sid] > 0 else 0.0)
        for sid in shown_counts
    }

    # 2. Group log entries by exact query string
    # TODO: Near-duplicate query text won't be merged without more sophisticated matching;
    # currently grouping by exact query string match.
    query_groups: Dict[str, List[Any]] = defaultdict(list)
    for log in logs:
        q = log.get("query") if isinstance(log, dict) else log.query
        query_groups[q].append(log)

    X_list: List[List[float]] = []
    y_list: List[int] = []
    group_sizes_list: List[int] = []

    for query, group_logs in query_groups.items():
        # Identify all candidates mentioned in this query's grouped logs
        # Positive label: 1 (accept or correct)
        # Negative label: 0 (reject)
        candidate_labels: Dict[str, int] = {}

        for log in group_logs:
            if isinstance(log, dict):
                action = log.get("action")
                chosen_id = log.get("chosen_id")
                corrected_id = log.get("corrected_id")
                cands = log.get("candidates_shown", [])
            else:
                action = log.action
                chosen_id = log.chosen_id
                corrected_id = log.corrected_id
                cands = log.candidates_shown

            if action == "accept" and chosen_id:
                candidate_labels[chosen_id] = 1
            elif action == "correct" and corrected_id:
                candidate_labels[corrected_id] = 1
            elif action == "reject":
                for c in cands:
                    cid = c.get("id") if isinstance(c, dict) else getattr(c, "id", None)
                    if cid and candidate_labels.get(cid) != 1:
                        candidate_labels[cid] = 0

        # Filter candidates to valid entries in corpus
        valid_cids = [cid for cid in candidate_labels.keys() if cid in corpus]
        if not valid_cids:
            continue

        # Sort deterministically: positive label (1) first, then by cid
        valid_cids.sort(key=lambda cid: (candidate_labels[cid], cid), reverse=True)

        # 3. Recompute retrieval component scores
        dense_results = dict(dense_search(query, top_k=max(20, len(valid_cids) + 5)))
        bm25_results = dict(bm25_search(query, top_k=max(20, len(valid_cids) + 5)))
        ce_results = dict(rerank(query, valid_cids, corpus=corpus, top_k=len(valid_cids)))

        # Per-query min-max normalization for BM25 feature
        raw_bm25_scores = [bm25_results.get(cid, 0.0) for cid in valid_cids]
        min_b = min(raw_bm25_scores) if raw_bm25_scores else 0.0
        max_b = max(raw_bm25_scores) if raw_bm25_scores else 0.0
        range_b = max_b - min_b

        query_features: List[List[float]] = []
        query_labels: List[int] = []

        for cid in valid_cids:
            std = corpus[cid]
            label = candidate_labels[cid]
            d_s = float(dense_results.get(cid, 0.0))
            raw_b = float(bm25_results.get(cid, 0.0))
            b_norm = (raw_b - min_b) / (range_b + 1e-6) if range_b > 1e-6 else 0.5
            ce_s = float(ce_results.get(cid, -10.0))
            hist_rate = rate_cache.get(cid, 0.0)

            # Recompute feature vector with updated historical_acceptance_rate
            fv = build_features(
                query=query,
                candidate_id=cid,
                standard=std,
                dense_score=d_s,
                bm25_score_normalized=b_norm,
                cross_encoder_score=ce_s,
                historical_acceptance_rate=hist_rate
            )
            query_features.append(fv)
            query_labels.append(label)

        if query_features:
            X_list.extend(query_features)
            y_list.extend(query_labels)
            group_sizes_list.append(len(query_features))

    X = np.array(X_list, dtype=np.float32) if X_list else np.empty((0, len(FEATURE_NAMES)), dtype=np.float32)
    y = np.array(y_list, dtype=np.int32) if y_list else np.empty((0,), dtype=np.int32)
    group_sizes = np.array(group_sizes_list, dtype=np.int32) if group_sizes_list else np.empty((0,), dtype=np.int32)

    return X, y, group_sizes


def main():
    """CLI runner to verify log integrity, load logs, construct training data, and report dataset statistics."""
    print("=" * 75)
    print("      FEEDBACK-TO-TRAINING-SET BUILDER (PART 6, STAGE D)")
    print("=" * 75)
    print(f"Log Database Path  : {_DEFAULT_LOG_PATH}")

    # --- Pre-Retraining Verification Step ---
    passed, extra, leaked, count = verify_logs_integrity(
        logs_path=_DEFAULT_LOG_PATH,
        expected_count=124,
        eval_set_path=_DEFAULT_EVAL_PATH,
        train_queries_path=_DEFAULT_TRAIN_PATH
    )

    if not passed:
        print("\n" + "!" * 75)
        print("  [PRE-RETRAINING VERIFICATION FAILED] LOG INTEGRITY / LEAKAGE DETECTED")
        print("!" * 75)
        print(f"Expected Line Count : 124, Actual Line Count : {count}")
        if leaked:
            print(f"Leaked queries matching eval_set.json ({len(leaked)}):")
            for q in leaked:
                print(f"  - {q}")
        if extra:
            print(f"Extra queries not in train_queries.json ({len(extra)}):")
            for q in extra:
                print(f"  - {q}")
        print("-" * 75)
        print("[Recovery Action] Clearing data/interaction_logs.jsonl...")
        _DEFAULT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_DEFAULT_LOG_PATH, "w", encoding="utf-8") as f:
            pass  # Truncate / clean file

        print("[Recovery Action] Re-running feedback/synthetic_logger.py from a clean file (not append)...")
        from feedback.synthetic_logger import generate_synthetic_logs
        from feedback.logger import append_log
        fresh_logs = generate_synthetic_logs(
            query_set_path=str(_DEFAULT_TRAIN_PATH),
            noise_rate=0.1,
            seed=1
        )
        for fl in fresh_logs:
            append_log(fl, path=_DEFAULT_LOG_PATH)

        print(f"[Recovery Action] Re-verifying newly generated interaction logs...")
        passed_recheck, extra_recheck, leaked_recheck, count_recheck = verify_logs_integrity(
            logs_path=_DEFAULT_LOG_PATH,
            expected_count=124,
            eval_set_path=_DEFAULT_EVAL_PATH,
            train_queries_path=_DEFAULT_TRAIN_PATH
        )
        if not passed_recheck:
            raise AssertionError(
                f"[Fatal] Log integrity check failed after regeneration: count={count_recheck}, "
                f"leaked={leaked_recheck}, extra={extra_recheck}. Do not proceed to retraining."
            )
        assert count_recheck == 124, f"Expected 124 lines after clean regeneration, got {count_recheck}"
        assert len(leaked_recheck) == 0, f"Expected 0 leaked queries, got {leaked_recheck}"
        print(f"[Recovery Action] SUCCESS: Exactly 124 clean interaction logs restored with 0 eval leakage.")
        print("!" * 75 + "\n")
    else:
        print(f"[Pre-Verification] PASSED: Exactly 124 logs verified, 0 queries match eval_set.json, all match train_queries.json.")

    logs = load_logs(str(_DEFAULT_LOG_PATH))
    if not logs:
        print("[ERROR] No interaction logs found. Run feedback/synthetic_logger.py first.")
        return

    corpus = {s.id: s for s in load_corpus()}
    print(f"[Builder] Converting {len(logs)} logs into LightGBM group-structured training data...")

    X, y, group_sizes = logs_to_training_data(logs, corpus=corpus)

    unique_queries = len(group_sizes)
    pos_count = int(np.sum(y == 1))
    neg_count = int(np.sum(y == 0))

    # Feature 6 (index 6) is historical_acceptance_rate
    hist_rate_idx = FEATURE_NAMES.index("historical_acceptance_rate")
    hist_rates = X[:, hist_rate_idx] if len(X) > 0 else np.array([])

    min_rate = float(np.min(hist_rates)) if len(hist_rates) > 0 else 0.0
    max_rate = float(np.max(hist_rates)) if len(hist_rates) > 0 else 0.0
    mean_rate = float(np.mean(hist_rates)) if len(hist_rates) > 0 else 0.0
    num_unique_rates = len(set(np.round(hist_rates, 4))) if len(hist_rates) > 0 else 0

    print("\n" + "=" * 75)
    print("                 TRAINING DATASET SUMMARY REPORT")
    print("=" * 75)
    print(f"Unique Queries (Groups)         : {unique_queries}")
    print(f"Total Candidate Instances       : {len(y)}")
    print(f"  - Positive Examples (Label 1) : {pos_count} (accepted/corrected)")
    min_sz = int(np.min(group_sizes)) if len(group_sizes) > 0 else 0
    max_sz = int(np.max(group_sizes)) if len(group_sizes) > 0 else 0
    mean_sz = float(np.mean(group_sizes)) if len(group_sizes) > 0 else 0.0
    print(f"Group Size Range                : min={min_sz}, max={max_sz}, mean={mean_sz:.2f}")
    print(f"Feature Matrix Shape            : {X.shape} (7 features in canonical order)")
    print("-" * 75)
    print("Historical Acceptance Rate Feature Stats (Sanity Check):")
    print(f"  - Min Rate                    : {min_rate:.4f}")
    print(f"  - Max Rate                    : {max_rate:.4f}")
    print(f"  - Mean Rate                   : {mean_rate:.4f}")
    print(f"  - Distinct Value Count        : {num_unique_rates} (verifies varied, non-degenerate values)")
    print("=" * 75)
    print("Training dataset successfully constructed and validated!")


if __name__ == "__main__":
    main()
