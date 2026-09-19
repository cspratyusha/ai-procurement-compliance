import json
import pickle
import re
from pathlib import Path
from typing import List, Tuple, Optional
from rank_bm25 import BM25Okapi

from data.models import Standard

_CACHED_BM25_INDEX: Optional[BM25Okapi] = None
_CACHED_BM25_IDS: Optional[List[str]] = None

_BASE_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_PKL_PATH = _BASE_DIR / "data" / "bm25.pkl"
_DEFAULT_IDS_PATH = _BASE_DIR / "data" / "bm25_ids.json"
_DEFAULT_TOKENS_PATH = _BASE_DIR / "data" / "bm25_tokens.json"


def tokenize(text: str) -> List[str]:
    """Deterministic, lightweight tokenizer for BM25 indexing and querying.
    
    Lowercases and splits on non-alphanumeric boundaries while preserving 
    alphanumeric sequences, digits, and standard designations (e.g. 'IS', '1554', 'IS1554', 'K9').
    """
    if not text:
        return []
    # Splits on punctuation and whitespace, preserving all alphanumeric tokens
    return [token for token in re.findall(r'[a-zA-Z0-9]+', text.lower()) if token]


def get_standard_bm25_text(standard: Standard) -> str:
    """Canonical text representation of a standard for sparse BM25 lexical indexing.
    
    Deliberately includes standard 'number' and 'keywords' in addition to title, scope, and description
    to give BM25 strong lexical matching power on exact standard numbers and rare technical terms.
    """
    keywords_text = " ".join(standard.keywords) if standard.keywords else ""
    return f"{standard.number} {standard.title} {keywords_text} {standard.scope} {standard.description}".strip()


def build_index(
    corpus: List[Standard],
    pkl_path: Optional[Path | str] = None,
    ids_path: Optional[Path | str] = None,
    tokens_path: Optional[Path | str] = None
) -> None:
    """Builds a BM25Okapi index over a corpus of Standard objects.
    
    1. Extracts lexical representation with standard numbers and keywords.
    2. Tokenizes documents.
    3. Builds rank_bm25.BM25Okapi index.
    4. Persists the pickled model, document ID mapping, and tokenized corpus to disk.
    
    Args:
        corpus: List of Standard Pydantic objects.
        pkl_path: Target path for the pickled BM25 model.
        ids_path: Target path for the ID mapping JSON.
        tokens_path: Target path for the tokenized corpus JSON.
    """
    global _CACHED_BM25_INDEX, _CACHED_BM25_IDS

    if not corpus:
        raise ValueError("Cannot build BM25 index from an empty corpus.")

    target_pkl_path = Path(pkl_path) if pkl_path else _DEFAULT_PKL_PATH
    target_ids_path = Path(ids_path) if ids_path else _DEFAULT_IDS_PATH
    target_tokens_path = Path(tokens_path) if tokens_path else _DEFAULT_TOKENS_PATH

    target_pkl_path.parent.mkdir(parents=True, exist_ok=True)
    target_ids_path.parent.mkdir(parents=True, exist_ok=True)

    doc_ids = [std.id for std in corpus]
    tokenized_corpus = [tokenize(get_standard_bm25_text(std)) for std in corpus]

    print(f"[SparseRetrieval] Building BM25Okapi index for {len(corpus)} documents...")
    bm25 = BM25Okapi(tokenized_corpus)

    # Persist pickle model
    with open(target_pkl_path, "wb") as f:
        pickle.dump(bm25, f)

    # Persist ID mapping
    with open(target_ids_path, "w", encoding="utf-8") as f:
        json.dump(doc_ids, f, indent=2)

    # Persist tokenized corpus for reference and diagnostics
    with open(target_tokens_path, "w", encoding="utf-8") as f:
        json.dump(tokenized_corpus, f, indent=2)

    # Update in-memory cache
    _CACHED_BM25_INDEX = bm25
    _CACHED_BM25_IDS = doc_ids

    print(f"[SparseRetrieval] BM25 index built with {len(doc_ids)} documents.")
    print(f"[SparseRetrieval] Saved to '{target_pkl_path}' and '{target_ids_path}'.")


def load_index(
    pkl_path: Optional[Path | str] = None,
    ids_path: Optional[Path | str] = None,
    force_reload: bool = False
) -> Tuple[BM25Okapi, List[str]]:
    """Loads the pickled BM25 index and ID mapping from disk into memory.
    
    Raises:
        FileNotFoundError: If the pickle file or ID mapping file is missing.
        ValueError: If index document count and ID mapping length do not match.
        
    Returns:
        Tuple of (BM25Okapi, list of standard IDs).
    """
    global _CACHED_BM25_INDEX, _CACHED_BM25_IDS

    if _CACHED_BM25_INDEX is not None and _CACHED_BM25_IDS is not None and not force_reload:
        return _CACHED_BM25_INDEX, _CACHED_BM25_IDS

    target_pkl_path = Path(pkl_path) if pkl_path else _DEFAULT_PKL_PATH
    target_ids_path = Path(ids_path) if ids_path else _DEFAULT_IDS_PATH

    if not target_pkl_path.exists():
        raise FileNotFoundError(
            f"BM25 index pickle not found at '{target_pkl_path}'. "
            "Run 'python -m indexing.build' or call 'bm25_index.build_index(corpus)' first."
        )

    if not target_ids_path.exists():
        raise FileNotFoundError(
            f"BM25 ID mapping file not found at '{target_ids_path}'. "
            "Run 'python -m indexing.build' or call 'bm25_index.build_index(corpus)' first."
        )

    with open(target_pkl_path, "rb") as f:
        bm25: BM25Okapi = pickle.load(f)

    with open(target_ids_path, "r", encoding="utf-8") as f:
        ids = json.load(f)

    # Validate alignment
    if len(bm25.doc_len) != len(ids):
        raise ValueError(
            f"Index corruption / mismatch: BM25 index contains {len(bm25.doc_len)} documents, "
            f"but ID mapping has {len(ids)} items."
        )

    _CACHED_BM25_INDEX = bm25
    _CACHED_BM25_IDS = ids
    return bm25, ids


def bm25_search(
    query: str,
    top_k: int = 20,
    pkl_path: Optional[Path | str] = None,
    ids_path: Optional[Path | str] = None
) -> List[Tuple[str, float]]:
    """Performs sparse lexical retrieval using BM25Okapi.
    
    1. Tokenizes query with the same deterministic tokenizer.
    2. Computes BM25 relevance scores.
    3. Returns list of (standard_id, raw_bm25_score) sorted descending.
    
    Note: Raw BM25 scores are unbounded and non-negative.
    
    Raises:
        FileNotFoundError / ValueError: If the index has not been built or is invalid.
    """
    if not query or not query.strip():
        return []

    bm25, ids = load_index(pkl_path=pkl_path, ids_path=ids_path)

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    scores = bm25.get_scores(query_tokens)

    # Pair with standard IDs and sort descending
    scored_results = [(ids[idx], float(scores[idx])) for idx in range(len(ids))]
    scored_results.sort(key=lambda x: x[1], reverse=True)

    return scored_results[:top_k]
