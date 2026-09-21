import json
import os
from pathlib import Path
from typing import Optional, Dict, List
from data.models import Standard

_CORPUS_CACHE: Optional[List[Standard]] = None
_ID_MAP_CACHE: Optional[Dict[str, Standard]] = None

_PACKAGE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_ROOT.parent

# The canonical dataset produced by data/consolidate.py: 45 standards merged
# from the three datasets that grew independently. `mock_corpus.json` (30
# standards) is the historical default and is kept because the committed LTR
# model and indexes were trained against it.
#
# STANDARDS_CORPUS selects between them, so a corpus swap is one environment
# variable rather than an edit at every load_corpus() call site:
#
#   STANDARDS_CORPUS=canonical   -> data/standards_corpus.json (45)
#   STANDARDS_CORPUS=mock        -> data/mock_corpus.json (30, default)
#   STANDARDS_CORPUS=/some/path  -> that file
_CANONICAL_CORPUS_PATH = _REPO_ROOT / "data" / "standards_corpus.json"
_EXPANDED_CORPUS_PATH = _REPO_ROOT / "data" / "standards_corpus_expanded.json"
_FULL_CORPUS_PATH = _REPO_ROOT / "data" / "standards_corpus_full.json"
_MOCK_CORPUS_PATH = _PACKAGE_ROOT / "data" / "mock_corpus.json"

_CORPUS_ALIASES = {
    "canonical": _CANONICAL_CORPUS_PATH,
    "consolidated": _CANONICAL_CORPUS_PATH,
    "expanded": _EXPANDED_CORPUS_PATH,
    "full": _FULL_CORPUS_PATH,
    "mock": _MOCK_CORPUS_PATH,
    "": _MOCK_CORPUS_PATH,
}


def _configured_corpus_path() -> Path:
    """Resolve the corpus selected by the STANDARDS_CORPUS env var."""
    raw = os.environ.get("STANDARDS_CORPUS", "").strip()
    alias = _CORPUS_ALIASES.get(raw.lower())
    if alias is not None:
        return alias

    path = Path(raw)
    if not path.is_absolute():
        path = _REPO_ROOT / path
    return path


def index_dir() -> Path:
    """Directory holding the FAISS and BM25 artifacts for the active corpus.

    Indexes are only valid for the corpus they were built from, so each corpus
    gets its own directory. Without this, building against the canonical
    corpus would overwrite the committed 30-standard indexes that the test
    suite and the shipped LTR model depend on.
    """
    corpus = _configured_corpus_path()
    if corpus == _MOCK_CORPUS_PATH:
        return _PACKAGE_ROOT / "data"

    directory = _PACKAGE_ROOT / "data" / "index" / corpus.stem
    directory.mkdir(parents=True, exist_ok=True)
    return directory


_DEFAULT_CORPUS_PATH = _configured_corpus_path()
_DEFAULT_EVAL_PATH = _PACKAGE_ROOT / "data" / "eval_set.json"


def load_corpus(corpus_path: Optional[str | Path] = None, force_reload: bool = False) -> List[Standard]:
    """Loads mock_corpus.json (or real Part 1 dataset once ready) into a list of Standard Pydantic models.
    
    Utilizes an in-memory cache to ensure repeated queries avoid re-parsing overhead.
    
    Args:
        corpus_path: Optional custom file path to corpus JSON. Defaults to data/mock_corpus.json.
        force_reload: If True, bypasses and refreshes the in-memory cache.
        
    Returns:
        List of Standard Pydantic objects.
    """
    global _CORPUS_CACHE, _ID_MAP_CACHE
    
    if _CORPUS_CACHE is not None and not force_reload and corpus_path is None:
        return _CORPUS_CACHE

    target_path = Path(corpus_path) if corpus_path else _configured_corpus_path()
    if not target_path.exists():
        # Fallback for callers running from a different working directory.
        alt_path = Path("data") / target_path.name
        if alt_path.exists():
            target_path = alt_path
        else:
            raise FileNotFoundError(
                f"Corpus file not found at {target_path} or {alt_path.resolve()}. "
                "Set STANDARDS_CORPUS to 'mock', 'canonical', or a path."
            )

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    standards = [Standard(**item) for item in data]
    
    # Update cache
    _CORPUS_CACHE = standards
    _ID_MAP_CACHE = {std.id: std for std in standards}
    
    return standards


def get_standard_by_id(standard_id: str, corpus_path: Optional[str | Path] = None) -> Optional[Standard]:
    """Retrieves a single standard by its unique ID from the in-memory cache.
    
    Args:
        standard_id: Unique standard ID, e.g., 'IS-ELEC-001'
        corpus_path: Optional path if corpus is not yet loaded.
        
    Returns:
        Standard object if found, else None.
    """
    global _ID_MAP_CACHE
    if _ID_MAP_CACHE is None:
        load_corpus(corpus_path=corpus_path)
    return _ID_MAP_CACHE.get(standard_id) if _ID_MAP_CACHE else None


def load_eval_set(eval_path: Optional[str | Path] = None) -> List[Dict[str, str]]:
    """Loads the evaluation dataset containing query-to-standard ground truth pairs.
    
    Args:
        eval_path: Optional custom path to eval_set.json. Defaults to data/eval_set.json.
        
    Returns:
        List of dicts with keys 'query' and 'correct_id'.
    """
    target_path = Path(eval_path) if eval_path else _DEFAULT_EVAL_PATH
    if not target_path.exists():
        alt_path = Path("data/eval_set.json")
        if alt_path.exists():
            target_path = alt_path
        else:
            raise FileNotFoundError(f"Evaluation file not found at {target_path} or {alt_path.resolve()}")

    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


def clear_cache() -> None:
    """Clears the in-memory corpus cache."""
    global _CORPUS_CACHE, _ID_MAP_CACHE
    _CORPUS_CACHE = None
    _ID_MAP_CACHE = None
