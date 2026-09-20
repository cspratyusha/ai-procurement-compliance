from datetime import datetime
from typing import List, Optional
from data.models import Standard

FEATURE_NAMES: List[str] = [
    "dense_score",
    "bm25_score_normalized",
    "cross_encoder_score",
    "recency_score",
    "category_match",
    "keyword_overlap",
    "historical_acceptance_rate",
]


def compute_recency_score(last_amended_str: str, current_year: Optional[int] = None) -> float:
    """Computes a recency decay score in [0.0, 1.0] from a standard's last_amended date.
    
    Formula: max(0.0, 1.0 - years_since_amendment / 10.0)
    A standard amended within the last year scores ~1.0; a standard not amended in >=10 years scores 0.0.
    """
    if not last_amended_str:
        return 0.5  # Neutral default

    if current_year is None:
        current_year = datetime.now().year

    try:
        dt = datetime.strptime(last_amended_str.strip(), "%Y-%m-%d")
        years_elapsed = max(0.0, float(current_year - dt.year))
        return max(0.0, 1.0 - (years_elapsed / 10.0))
    except Exception:
        # If date is unparseable or year-only
        try:
            year = int(last_amended_str.strip()[:4])
            years_elapsed = max(0.0, float(current_year - year))
            return max(0.0, 1.0 - (years_elapsed / 10.0))
        except Exception:
            return 0.5


# Category keywords mapping for rough query-domain matching
_CATEGORY_KEYWORDS = {
    "Electrical Cables & Wires": {
        "cable", "wire", "wiring", "insulated", "conductor", "voltage",
        "pvc", "xlpe", "electric", "electrical", "power", "sheathed",
        "copper", "aluminum", "halogen", "solar", "photovoltaic", "dc",
        "overhead", "underground", "submersible", "fire", "mineral",
        "aerial", "bunched", "flexible", "armored", "armoured"
    },
    "Cement & Building Materials": {
        "cement", "concrete", "opc", "ppc", "portland", "grade", "masonry",
        "mortar", "brick", "block", "aac", "aerated", "autoclaved",
        "fly", "ash", "lime", "hydrophobic", "ready", "mixed", "rmc",
        "compressive", "strength", "construction", "building", "plastering",
        "pozzolana", "calcined", "clinker"
    },
    "Steel Pipes & Fittings": {
        "pipe", "tube", "steel", "iron", "fitting", "welded", "seamless",
        "erw", "ductile", "malleable", "stainless", "boiler", "condenser",
        "heat", "exchanger", "casing", "hdpe", "polyethylene", "water",
        "sewage", "spiral", "galvanized", "threaded", "tyton", "borewell"
    }
}


def _compute_category_match(query: str, standard: Standard) -> float:
    """Computes query-category relevance based on keyword overlap with category lexicons.
    
    Returns a score in [0.0, 1.0] indicating how well the query's vocabulary 
    matches the standard's category domain keywords.
    
    Strategy: tokenize query, check overlap with the standard's category lexicon
    vs other categories' lexicons. If query terms match this category more than
    others, score is high; if ambiguous, score is moderate.
    """
    query_tokens = set(query.lower().split())
    std_category = standard.category
    
    if std_category not in _CATEGORY_KEYWORDS:
        return 0.5  # Unknown category, neutral
    
    target_lexicon = _CATEGORY_KEYWORDS[std_category]
    target_overlap = len(query_tokens & target_lexicon)
    
    if target_overlap == 0:
        return 0.2  # No overlap with expected category
    
    # Check overlap with OTHER categories
    other_max_overlap = 0
    for cat, lexicon in _CATEGORY_KEYWORDS.items():
        if cat != std_category:
            other_overlap = len(query_tokens & lexicon)
            other_max_overlap = max(other_max_overlap, other_overlap)
    
    # Relative advantage: how much more does query match this category vs best other
    if target_overlap + other_max_overlap == 0:
        return 0.5
    
    relative_score = target_overlap / (target_overlap + other_max_overlap + 1e-6)
    return min(1.0, 0.3 + 0.7 * relative_score)


def _compute_keyword_overlap(query: str, standard: Standard) -> float:
    """Computes the fraction of standard keywords that appear in the query.
    
    Returns a score in [0.0, 1.0]. This captures fine-grained term-level matching 
    beyond what BM25 encodes, because it's computed over the curated keyword list
    specifically, not the full document text.
    """
    if not standard.keywords:
        return 0.0
    
    query_lower = query.lower()
    matches = 0
    for kw in standard.keywords:
        # Check if any keyword phrase (or significant word within it) appears in query
        kw_lower = kw.lower()
        if kw_lower in query_lower:
            matches += 1
        else:
            # Check individual words from multi-word keywords
            kw_words = kw_lower.split()
            if len(kw_words) > 1:
                word_matches = sum(1 for w in kw_words if len(w) > 2 and w in query_lower)
                if word_matches >= len(kw_words) * 0.6:
                    matches += 0.5
    
    return min(1.0, matches / len(standard.keywords))


def build_features(
    query: str,
    candidate_id: str,
    standard: Standard,
    dense_score: float,
    bm25_score_normalized: float,
    cross_encoder_score: float,
    historical_acceptance_rate: float = 0.0,
    current_year: Optional[int] = None
) -> List[float]:
    """Extracts a fixed-order feature vector for a (query, candidate standard) pair.
    
    Order:
      1. dense_score: Cosine similarity from FAISS e5-base-v2 search [0.0, 1.0]
      2. bm25_score_normalized: Min-max normalized BM25 score across query candidates [0.0, 1.0]
      3. cross_encoder_score: Joint cross-attention logits from ms-marco-MiniLM-L-6-v2
      4. recency_score: Temporal decay based on last_amended date [0.0, 1.0]
      5. category_match: Query-to-standard domain keyword match score [0.0, 1.0]
      6. keyword_overlap: Fraction of standard's curated keywords found in query [0.0, 1.0]
      7. historical_acceptance_rate: Historical user acceptance rate from feedback logs (0.0 placeholder)
      
    Returns:
        List of 7 float values matching FEATURE_NAMES.
    """
    # 1. Dense score
    f_dense = float(dense_score)

    # 2. Per-query normalized BM25 score
    f_bm25 = float(bm25_score_normalized)

    # 3. Cross-encoder score
    f_cross_encoder = float(cross_encoder_score)

    # 4. Recency decay score
    f_recency = compute_recency_score(standard.last_amended, current_year=current_year)

    # 5. Category match — real computation from query tokens vs category keyword lexicons
    f_category_match = _compute_category_match(query, standard)

    # 6. Keyword overlap — fraction of standard's curated keywords found in query
    f_keyword_overlap = _compute_keyword_overlap(query, standard)

    # 7. Historical feedback acceptance rate placeholder
    # Will be populated by Part 6 feedback loop aggregator once live clicks accumulate
    f_acceptance_rate = float(historical_acceptance_rate)

    return [
        f_dense,
        f_bm25,
        f_cross_encoder,
        f_recency,
        f_category_match,
        f_keyword_overlap,
        f_acceptance_rate,
    ]


def fallback_score(features: List[float]) -> float:
    """Heuristic fallback ranker used when no trained LightGBM model is available on disk.
    
    Formula: 0.3 * dense + 0.2 * bm25_normalized + 0.5 * cross_encoder
    """
    if len(features) < 3:
        raise ValueError(f"Expected at least 3 features for fallback scoring, got {len(features)}")
    dense = features[0]
    bm25_norm = features[1]
    cross_enc = features[2]
    return 0.3 * dense + 0.2 * bm25_norm + 0.5 * cross_enc
