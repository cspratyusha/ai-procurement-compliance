"""Make the canonical `standards-retrieval/` pipeline importable.

`standards-retrieval/` is the single source of truth for retrieval, ranking
and evaluation. Its directory name contains a hyphen, so it cannot be
imported as a Python package, and its modules import one another by bare
name (``from data_loader import ...``) assuming that directory is on
``sys.path``.

This module adds it to ``sys.path`` exactly once, so `app/` can reuse the
pipeline instead of vendoring a second copy of it.
"""

import sys
from pathlib import Path

# app/services/standards_retrieval_path.py -> repo root is three levels up.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_RETRIEVAL_ROOT = _REPO_ROOT / "standards-retrieval"


def ensure_retrieval_on_path() -> Path:
    """Add `standards-retrieval/` to sys.path if it is not already there.

    Returns the resolved path so callers can locate sibling data files.
    Idempotent and safe to call from multiple modules.
    """
    if not _RETRIEVAL_ROOT.is_dir():
        raise RuntimeError(
            f"Expected the retrieval pipeline at {_RETRIEVAL_ROOT}, but that "
            "directory does not exist. `app/` depends on `standards-retrieval/`; "
            "see README.md for the repository layout."
        )

    path_str = str(_RETRIEVAL_ROOT)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
    return _RETRIEVAL_ROOT
