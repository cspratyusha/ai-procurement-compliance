"""Standards Retrieval package (Part 2 + Part 6)."""
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

# Also ensure repo root is in sys.path
_REPO_ROOT = _PKG_ROOT.parents[2] if len(_PKG_ROOT.parents) >= 3 else _PKG_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
