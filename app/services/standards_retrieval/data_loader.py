import json
import os
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any

try:
    from app.services.standards_retrieval.data.models import Standard
except ImportError:
    from data.models import Standard

logger = logging.getLogger(__name__)

_CORPUS_CACHE: Optional[List[Standard]] = None
_ID_MAP_CACHE: Optional[Dict[str, Standard]] = None

_BASE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BASE_DIR.parents[2] if len(_BASE_DIR.parents) >= 3 else _BASE_DIR.parent
_CANONICAL_RAW_PATH = _REPO_ROOT / "data" / "raw" / "standards.json"
_MOCK_CORPUS_PATH = _BASE_DIR / "data" / "mock_corpus.json"
_DEFAULT_EVAL_PATH = _BASE_DIR / "data" / "eval_set.json"


def _load_from_postgres(database_url: str) -> Optional[List[Standard]]:
    """Attempts to load standards directly from PostgreSQL using SQLAlchemy."""
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(database_url, connect_args={"connect_timeout": 3})
        with engine.connect() as connection:
            result = connection.execute(text("""
                SELECT id, number, title, scope, description, category, version,
                       last_amended, status, keywords_json, superseded_by_id
                FROM standards
            """))
            rows = result.mappings().all()
            if not rows:
                logger.warning("PostgreSQL standards table is empty.")
                return None

            standards = []
            for row in rows:
                kw = row["keywords_json"]
                if isinstance(kw, str):
                    try:
                        keywords_list = json.loads(kw)
                    except Exception:
                        keywords_list = [k.strip() for k in kw.split(",") if k.strip()]
                elif isinstance(kw, list):
                    keywords_list = kw
                else:
                    keywords_list = []

                standards.append(Standard(
                    id=row["id"],
                    number=row["number"],
                    title=row["title"],
                    scope=row["scope"],
                    description=row["description"],
                    category=row["category"],
                    version=row["version"],
                    last_amended=str(row["last_amended"]),
                    status=row["status"],
                    keywords=keywords_list,
                    superseded_by_id=row.get("superseded_by_id")
                ))
            logger.info(f"Loaded {len(standards)} standards from PostgreSQL ({database_url}).")
            return standards
    except Exception as exc:
        logger.warning(f"Could not load from PostgreSQL ({exc}). Falling back to JSON source.")
        return None


def _load_from_json(target_path: Path) -> List[Standard]:
    """Loads standards from a JSON file."""
    if not target_path.exists():
        # Fallback search
        alt_paths = [
            _CANONICAL_RAW_PATH,
            _MOCK_CORPUS_PATH,
            Path("data/raw/standards.json"),
            Path("data/mock_corpus.json"),
            Path("../data/raw/standards.json")
        ]
        for alt in alt_paths:
            if alt.exists():
                target_path = alt
                break
        else:
            raise FileNotFoundError(f"Corpus file not found at {target_path}")

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    standards = []
    for item in data:
        # Handle field mappings: scope_text -> scope, keywords_json -> keywords
        std_dict = dict(item)
        if "scope_text" in std_dict and "scope" not in std_dict:
            std_dict["scope"] = std_dict.pop("scope_text")
        if "keywords_json" in std_dict and "keywords" not in std_dict:
            std_dict["keywords"] = std_dict.pop("keywords_json")
        standards.append(Standard(**std_dict))
    return standards


def load_corpus(
    corpus_path: Optional[str | Path] = None,
    force_reload: bool = False
) -> List[Standard]:
    """Loads the BIS standards corpus into a list of Standard Pydantic models.
    
    Default behavior:
    1. If explicit corpus_path provided: load directly from that JSON path.
    2. Else check CORPUS_SOURCE env var (default: 'postgres'):
       - If 'postgres': attempts SQLAlchemy connection to DATABASE_URL.
       - If fails or 'json': loads from data/raw/standards.json (canonical real corpus).
    
    Args:
        corpus_path: Optional custom file path to corpus JSON (e.g. mock_corpus.json for unit tests).
        force_reload: If True, bypasses and refreshes the in-memory cache.
        
    Returns:
        List of Standard Pydantic objects.
    """
    global _CORPUS_CACHE, _ID_MAP_CACHE
    
    if _CORPUS_CACHE is not None and not force_reload and corpus_path is None:
        return _CORPUS_CACHE

    # 1. Explicit path given (e.g. for unit tests passing mock_corpus.json)
    if corpus_path is not None:
        standards = _load_from_json(Path(corpus_path))
        _CORPUS_CACHE = standards
        _ID_MAP_CACHE = {std.id: std for std in standards}
        return standards

    # 2. Environment-controlled loading
    corpus_source = os.getenv("CORPUS_SOURCE", "postgres").lower().strip()
    database_url = os.getenv("DATABASE_URL", "postgresql+psycopg://procurement:procurement@localhost:55432/procurement")

    standards = None
    if corpus_source == "postgres":
        standards = _load_from_postgres(database_url)

    if standards is None:
        # Fallback to canonical raw standards.json
        target_json = _CANONICAL_RAW_PATH if _CANONICAL_RAW_PATH.exists() else _MOCK_CORPUS_PATH
        standards = _load_from_json(target_json)

    _CORPUS_CACHE = standards
    _ID_MAP_CACHE = {std.id: std for std in standards}
    return standards


def get_standard_by_id(standard_id: str, corpus_path: Optional[str | Path] = None) -> Optional[Standard]:
    """Retrieves a single standard by its unique ID from the in-memory cache."""
    global _ID_MAP_CACHE
    if _ID_MAP_CACHE is None or standard_id not in _ID_MAP_CACHE:
        load_corpus(corpus_path=corpus_path)
    return _ID_MAP_CACHE.get(standard_id) if _ID_MAP_CACHE else None


def load_eval_set(eval_path: Optional[str | Path] = None) -> List[Dict[str, str]]:
    """Loads the evaluation dataset containing query-to-standard ground truth pairs."""
    target_path = Path(eval_path) if eval_path else _DEFAULT_EVAL_PATH
    if not target_path.exists():
        alt_paths = [
            _BASE_DIR / "data" / "eval_set.json",
            Path("data/eval_set.json"),
            _REPO_ROOT / "data" / "eval_set.json"
        ]
        for alt in alt_paths:
            if alt.exists():
                target_path = alt
                break
        else:
            raise FileNotFoundError(f"Evaluation file not found at {target_path}")

    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


def clear_cache() -> None:
    """Clears the in-memory corpus cache."""
    global _CORPUS_CACHE, _ID_MAP_CACHE
    _CORPUS_CACHE = None
    _ID_MAP_CACHE = None
