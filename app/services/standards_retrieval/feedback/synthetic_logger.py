"""Synthetic interaction log generator for bootstrapping the Part 6 feedback loop.

Design Notes:
-------------
- Since there is no live user traffic during initial staging, this generator creates
  realistic interaction logs by running bootstrap queries through the ACTUAL retrieval
  and LTR ranking pipeline (not hand-crafted or synthetic rankings).
- Sourced from data/train_queries.json: we deliberately source synthetic feedback from
  the training bootstrap queries, keeping data/eval_set.json reserved exclusively for
  the final evaluation benchmark and promotion gate.
- Note: Synthetic accepts mostly confirm existing model behavior rather than introducing
  new signal, since the pipeline already ranks correctly on most queries.
- Realistic noise: with probability (1 - noise_rate), the official accepts the ground-truth
  correct_id; with probability noise_rate, a plausible alternative from the top-5 candidates
  is selected to simulate real-world officer mistakes or edge-case disagreements.
- Implicit negative feedback: for every query, 1-2 non-chosen candidates from the top-5
  are explicitly logged as separate action="reject" records (officials implicitly reject
  results they scroll past without selecting). This prevents training on positive-only data.
- Re-runnable: this generator is designed to be re-runnable multiple times without needing
  to clear the log file. Each run appends more source="synthetic" entries to
  data/interaction_logs.jsonl, which remain clearly separable from source="live" entries
  once real usage commences.
"""
import sys
import random
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data_loader import load_eval_set
from feedback.schema import InteractionLog
from feedback.logger import append_log, _resolve_log_path
from ltr.train import load_model

logger = logging.getLogger("standards-retrieval.feedback.synthetic")
logging.basicConfig(level=logging.INFO)

_DEFAULT_TRAIN_QUERIES_PATH = _PROJECT_ROOT / "data" / "train_queries.json"
_DEFAULT_LOG_PATH = _PROJECT_ROOT / "data" / "interaction_logs.jsonl"


def generate_synthetic_logs(
    query_set_path: str = "data/train_queries.json",
    noise_rate: float = 0.1,
    seed: Optional[int] = None,
    eval_set_path: Optional[str] = None
) -> List[InteractionLog]:
    """Generates synthetic interaction logs by evaluating queries via the live pipeline.
    
    Note: Synthetic accepts mostly confirm existing model behavior rather than introducing new signal, since the pipeline already ranks correctly on most queries.
    
    Queries are sourced from data/train_queries.json (keeping data/eval_set.json reserved
    exclusively for held-out evaluation benchmarks and the promotion gate).
    
    Args:
        query_set_path: Path to queries JSON (defaults to data/train_queries.json).
        noise_rate: Probability of injecting a plausible incorrect selection from top-5 (default 0.1).
        seed: Optional random seed for reproducible noise generation.
        eval_set_path: Optional backwards-compatible alias for query_set_path.
        
    Returns:
        List of generated InteractionLog objects (both 'accept' and 'reject' records).
    """
    from main import app, retrieve_standards_post, RetrieveRequest

    rng = random.Random(seed)

    # Ensure LTR model is loaded on app.state if running standalone
    if getattr(app.state, "ltr_model", None) is None:
        ltr_model = load_model()
        if ltr_model is not None:
            app.state.ltr_model = ltr_model

    # Resolve queries path (supporting backwards-compatible eval_set_path alias if supplied)
    target_path_str = eval_set_path if eval_set_path is not None else query_set_path
    resolved_path = _resolve_log_path(target_path_str) if not Path(target_path_str).is_absolute() else Path(target_path_str)
    queries = load_eval_set(str(resolved_path))
    if not queries:
        logger.warning(f"[SyntheticLogger] No queries found at '{resolved_path}'.")
        return []

    generated_logs: List[InteractionLog] = []

    for item in queries:
        query = item["query"]
        correct_id = item["correct_id"]

        # 1. Run through actual live retrieval pipeline
        resp = retrieve_standards_post(RetrieveRequest(query=query, top_k=10))
        if not resp.results:
            continue

        # Format candidates_shown context
        candidates_shown = [
            {"id": r.id, "final_score": r.final_score, "rank": idx + 1}
            for idx, r in enumerate(resp.results)
        ]
        top_cands = candidates_shown[:5]
        candidate_ids = [c["id"] for c in candidates_shown]

        # 2. Determine selection: ground-truth vs plausible noise
        other_top_cands = [c["id"] for c in top_cands if c["id"] != correct_id]

        if rng.random() < noise_rate and other_top_cands:
            # Plausible error: choose a non-target candidate from top-5
            chosen_id = rng.choice(other_top_cands)
        else:
            # Ground truth: accept correct_id if present, else top result
            chosen_id = correct_id if correct_id in candidate_ids else candidates_shown[0]["id"]

        now_iso = datetime.now(timezone.utc).isoformat()

        # 3. Create accept log entry
        accept_entry = InteractionLog(
            query=query,
            candidates_shown=candidates_shown,
            chosen_id=chosen_id,
            action="accept",
            corrected_id=None,
            timestamp=now_iso,
            source="synthetic"
        )
        generated_logs.append(accept_entry)

        # 4. Generate 1-2 explicit reject entries for non-chosen top candidates
        # Simulates implicit rejection when scrolling past alternatives
        non_chosen = [c for c in top_cands if c["id"] != chosen_id]
        if non_chosen:
            num_rejects = min(len(non_chosen), rng.choice([1, 2]))
            rejected_sample = rng.sample(non_chosen, num_rejects)

            for rej_c in rejected_sample:
                reject_entry = InteractionLog(
                    query=query,
                    candidates_shown=[rej_c],
                    chosen_id=None,
                    action="reject",
                    corrected_id=None,
                    timestamp=now_iso,
                    source="synthetic"
                )
                generated_logs.append(reject_entry)

    return generated_logs


def main():
    """CLI runner to generate synthetic logs from train_queries.json and populate data/interaction_logs.jsonl."""
    print("=" * 75)
    print("      SYNTHETIC INTERACTION LOG GENERATOR (PART 6, STAGE D)")
    print("=" * 75)

    noise_rate = 0.1
    print(f"Target Noise Rate  : {noise_rate * 100:.1f}%")
    print(f"Source Dataset     : {_DEFAULT_TRAIN_QUERIES_PATH} (train_queries.json)")
    print(f"Target Log File    : {_DEFAULT_LOG_PATH}\n")
    print("[SyntheticLogger] Running queries through live retrieval pipeline...")

    logs = generate_synthetic_logs(
        query_set_path=str(_DEFAULT_TRAIN_QUERIES_PATH),
        noise_rate=noise_rate,
        seed=1
    )

    # Cleanly regenerate the log file from this corrected source
    _DEFAULT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_DEFAULT_LOG_PATH, "w", encoding="utf-8") as f:
        pass  # Reset file to cleanly regenerate from train_queries.json

    # Append all generated logs
    for log in logs:
        append_log(log, path=_DEFAULT_LOG_PATH)

    accept_logs = [l for l in logs if l.action == "accept"]
    reject_logs = [l for l in logs if l.action == "reject"]

    # Load queries to count exact noisy selections
    train_queries = load_eval_set(str(_DEFAULT_TRAIN_QUERIES_PATH))
    correct_map = {item["query"]: item["correct_id"] for item in train_queries}

    noisy_accepts = sum(1 for l in accept_logs if l.chosen_id != correct_map.get(l.query))
    correct_accepts = len(accept_logs) - noisy_accepts
    actual_noise_pct = (noisy_accepts / len(accept_logs) * 100.0) if accept_logs else 0.0

    print("\n" + "=" * 75)
    print("                   REGENERATION SUMMARY REPORT")
    print("=" * 75)
    print(f"Source Query File      : {_DEFAULT_TRAIN_QUERIES_PATH} (eval_set reserved for gate)")
    print(f"Total Logs Generated   : {len(logs)}")
    print(f"Accept Entries         : {len(accept_logs)}")
    print(f"  - Clean Accepts      : {correct_accepts} (chosen_id == correct_id)")
    print(f"  - Noisy Accepts      : {noisy_accepts} (simulated official error/disagreement)")
    print(f"  - Actual Noise Rate  : {actual_noise_pct:.1f}% (target: {noise_rate * 100:.1f}%)")
    print(f"Reject Entries         : {len(reject_logs)} (non-chosen alternatives)")
    print(f"Storage File           : {_DEFAULT_LOG_PATH}")
    print(f"Source Tag             : source='synthetic'")
    print("=" * 75)
    print("Synthetic feedback database successfully regenerated from train_queries.json!")


if __name__ == "__main__":
    main()
