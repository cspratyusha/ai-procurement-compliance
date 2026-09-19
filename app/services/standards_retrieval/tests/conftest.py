import os
import sys
from pathlib import Path

os.environ.setdefault("CORPUS_SOURCE", "json")

_ROOT = Path(__file__).resolve().parent.parent
_SR_DIR = _ROOT / "app" / "services" / "standards_retrieval"

if str(_SR_DIR) not in sys.path:
    sys.path.insert(0, str(_SR_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
