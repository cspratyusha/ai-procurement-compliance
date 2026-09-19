"""Post-processing and business-rule enforcement for retrieved standards.

Provides deterministic post-scoring adjustments that enforce domain correctness 
in a hybrid rule + ML architecture.

Note on deterministic vs. learned rule:
With only one or two superseded/active pairs in the mock corpus, there isn't enough 
training signal for the model to reliably learn this pattern on its own (confirmed by 
recency_score's near-zero, noisy contribution in the diagnostics) — a hard rule is far 
more reliable than hoping a 6-7 feature model with ~70 training queries discovers it, 
and this is exactly the kind of correctness-critical compliance rule a hybrid rule+ML 
system should enforce explicitly rather than leave to statistics.

final_score Contract:
final_score is a relative ranking signal bounded in range [0.0, 1.0], not a calibrated 
probability or percentage — do not display it directly as a confidence percentage 
without further calibration. final_score is only comparable within a single response, 
not across separate /retrieve calls.
"""
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Union

# Add project root to sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.models import Standard
from data_loader import load_corpus


def extract_base_standard_family(number_str: str) -> str:
    """Extracts the base standard family identifier, stripping edition years and revisions.
    
    Examples:
      'IS 1554 (Part 1):1988' -> 'IS 1554 (PART 1)'
      'IS 1554 (Part 1):2020' -> 'IS 1554 (PART 1)'
      'IS 694:2010'           -> 'IS 694'
      'IS 694 (Part 2):2016'  -> 'IS 694 (PART 2)'
    """
    if not number_str:
        return ""
    base = number_str.split(":")[0].strip()
    base = re.sub(r"\s+", " ", base).strip().upper()
    return base


def apply_supersession_penalty(
    results: Union[List[Tuple[str, float]], List[Dict[str, Any]]],
    corpus: Optional[Dict[str, Standard]] = None,
    penalty: float = 2.0,
    top_k: int = 10,
    return_metadata: bool = False
) -> Union[
    List[Tuple[str, float]],
    List[Dict[str, Any]],
    Tuple[Union[List[Tuple[str, float]], List[Dict[str, Any]]], List[Dict[str, Any]]]
]:
    """Applies a deterministic score penalty to superseded standards when an active sibling exists.
    
    Rule logic:
      If a candidate standard has status="superseded" AND a different candidate in the same 
      result set has status="active" and shares the same base standard family (e.g. 'IS 1554 (PART 1)'),
      we apply a fixed score penalty floored at 0.0:
        penalized_score = max(0.0, min(score - penalty, active_floor - 0.1))
      
      The penalized entry receives a 'superseded_by' field identifying the active sibling.
      Ties at the 0.0 floor are broken by original pre-penalty score so relative ordering
      remains deterministic.
      
      When a superseded standard would have placed in the original top_k but the penalty pushed
      it out, a summary entry {id, number, status, superseded_by} is recorded in nearby_superseded.
      
    Args:
        results: List of (standard_id, score) tuples OR list of dicts.
        corpus: Standards dictionary lookup.
        penalty: Fixed penalty margin to subtract.
        top_k: Top-k boundary for determining nearby_superseded.
        return_metadata: If True, returns (adjusted_results, nearby_superseded).
        
    Returns:
        Adjusted results list (and optionally nearby_superseded list).
    """
    if not results:
        empty_res = []
        return (empty_res, []) if return_metadata else empty_res

    if corpus is None:
        corpus = {s.id: s for s in load_corpus()}

    is_tuple = isinstance(results[0], tuple)

    # 1. Parse into uniform internal dictionaries
    parsed_items = []
    for i, item in enumerate(results):
        if is_tuple:
            cid, score = item[0], float(item[1])
            raw_obj = {"id": cid, "standard_id": cid, "score": score}
        else:
            cid = item.get("standard_id") or item.get("id")
            score = float(item.get("final_score", item.get("score", 0.0)))
            raw_obj = dict(item)
        std = corpus.get(cid)
        parsed_items.append({
            "index": i,
            "id": cid,
            "original_score": score,
            "score": score,
            "standard": std,
            "raw": raw_obj,
            "superseded_by": None
        })

    # Ensure all baseline candidate scores are bounded to non-negative range [0.0, 1.0]
    # Shifting by -min_score when min_score < 0 is a strictly order-preserving linear transformation
    # that bounds all valid candidate scores above 0.0, allowing penalized candidates to floor at 0.0
    # and cleanly rank below unrelated relevant results without any negative numbers returned.
    min_score = min((it["score"] for it in parsed_items), default=0.0)
    if min_score < 0.0:
        shift = -min_score + 0.01
        for it in parsed_items:
            it["score"] += shift
            it["original_score"] += shift

    # Rescale if max_score exceeds the 1.0 upper bound, preserving relative order and proportions
    max_score = max((it["score"] for it in parsed_items), default=1.0)
    if max_score > 1.0:
        scale = 1.0 / max_score
        for it in parsed_items:
            it["score"] *= scale
            it["original_score"] *= scale

    # Track pre-penalty top_k candidates by original score
    pre_sorted = sorted(parsed_items, key=lambda x: x["original_score"], reverse=True)
    pre_penalty_top_k_ids = set(it["id"] for it in pre_sorted[:top_k])

    # 2. Identify highest-scoring active standard per family
    active_family_leaders: Dict[str, Dict[str, Any]] = {}
    for item in parsed_items:
        std = item["standard"]
        if std and getattr(std, "status", "").lower() == "active":
            family = extract_base_standard_family(std.number)
            if family:
                if family not in active_family_leaders or item["score"] > active_family_leaders[family]["score"]:
                    active_family_leaders[family] = {
                        "id": item["id"],
                        "number": std.number,
                        "score": item["score"]
                    }

    # 3. Apply floored penalty to superseded standards with active sibling present
    for item in parsed_items:
        std = item["standard"]
        score = item["score"]
        if std and getattr(std, "status", "").lower() == "superseded":
            family = extract_base_standard_family(std.number)
            if family and family in active_family_leaders:
                leader = active_family_leaders[family]
                active_floor = leader["score"]
                item["superseded_by"] = leader["id"]

                # Floor at 0.0: never return negative scores
                # Ensure it ranks below active sibling (active_floor - 0.1) and below unrelated
                penalized_score = max(0.0, min(score - penalty, max(0.0, active_floor - 0.1)))
                item["score"] = penalized_score

    # 4. Sort descending: primary by floored score, secondary by pre-penalty score (tie-breaker at floor)
    parsed_items.sort(key=lambda x: (x["score"], x["original_score"]), reverse=True)

    # 5. Identify superseded candidates pushed out of the top_k
    # Only surface if the active sibling (superseded_by) is among the top relevant results (top-3),
    # meaning this standard family is actually relevant to the user's query.
    top_active_family_ids = set(it["id"] for it in parsed_items[:3])
    post_penalty_top_k_ids = set(it["id"] for it in parsed_items[:top_k])
    nearby_superseded = []
    for item in pre_sorted[:top_k]:
        cid = item["id"]
        if (
            cid not in post_penalty_top_k_ids
            and item["superseded_by"]
            and item["superseded_by"] in top_active_family_ids
        ):
            std = item["standard"]
            nearby_superseded.append({
                "id": cid,
                "number": std.number if std else "",
                "status": "superseded",
                "superseded_by": item["superseded_by"]
            })

    # 6. Format output (clamping strictly to [0.0, 1.0] and removing duplicate "score" field)
    if is_tuple:
        out_results = [(it["id"], max(0.0, min(1.0, round(it["score"], 4)))) for it in parsed_items]
    else:
        out_results = []
        for rank, it in enumerate(parsed_items, 1):
            d = dict(it["raw"])
            d["rank"] = rank
            d["final_score"] = max(0.0, min(1.0, round(it["score"], 4)))
            d.pop("score", None)
            if it["superseded_by"]:
                d["superseded_by"] = it["superseded_by"]
            out_results.append(d)

    if return_metadata:
        return out_results, nearby_superseded
    return out_results
