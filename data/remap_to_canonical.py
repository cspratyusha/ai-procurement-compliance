"""Remap the training and evaluation sets onto the canonical corpus ids.

`data/consolidate.py` renumbers standards when it merges the three source
datasets, so `IS-ELEC-001` in the old 30-standard `mock_corpus.json` is not
necessarily `IS-ELEC-001` in `data/standards_corpus.json`. The training and
eval sets reference standards by id, so they have to be remapped before the
ranker can be retrained against the consolidated corpus.

The mapping goes through the **IS number**, which is stable across the
renumbering, rather than through position or name similarity.

Every remapped record keeps a `correct_number` field so that any future
renumbering can be redone from the number rather than from an id that may
since have moved.

Run with::

    python data/remap_to_canonical.py --check   # report only
    python data/remap_to_canonical.py           # write the remapped files
"""

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

OLD_CORPUS = _REPO_ROOT / "standards-retrieval" / "data" / "mock_corpus.json"
NEW_CORPUS = _REPO_ROOT / "data" / "standards_corpus.json"

# (source, destination) pairs.
JOBS = [
    (
        _REPO_ROOT / "standards-retrieval" / "data" / "eval_set.json",
        _REPO_ROOT / "data" / "eval_set_consolidated.json",
    ),
    (
        _REPO_ROOT / "standards-retrieval" / "data" / "train_queries.json",
        _REPO_ROOT / "data" / "train_queries_consolidated.json",
    ),
]


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_id_map() -> dict:
    """old id -> new id, joined on the IS number."""
    old_id_to_number = {s["id"]: s["number"] for s in _load(OLD_CORPUS)}
    new_number_to_id = {s["number"]: s["id"] for s in _load(NEW_CORPUS)}

    mapping = {}
    unmapped = []
    for old_id, number in old_id_to_number.items():
        new_id = new_number_to_id.get(number)
        if new_id is None:
            unmapped.append((old_id, number))
        else:
            mapping[old_id] = new_id

    if unmapped:
        raise SystemExit(
            "These standards exist in the old corpus but not the canonical one, "
            "so the remap would silently drop them:\n"
            + "\n".join(f"  {oid}  {num}" for oid, num in unmapped)
        )
    return mapping


def remap_record(record: dict, id_map: dict, number_of: dict) -> dict:
    """Rewrite every id-valued field, recording the IS number alongside."""
    out = dict(record)
    old_id = record.get("correct_id")
    if old_id:
        out["correct_id"] = id_map[old_id]
        out["correct_number"] = number_of[old_id]

    # Some training records carry graded relevance lists.
    for key in ("relevant_ids", "candidates", "negatives"):
        value = record.get(key)
        if isinstance(value, list):
            out[key] = [
                id_map.get(v, v) if isinstance(v, str)
                else ({**v, "id": id_map.get(v["id"], v["id"])} if isinstance(v, dict) and "id" in v else v)
                for v in value
            ]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only; write nothing")
    args = parser.parse_args()

    id_map = build_id_map()
    number_of = {s["id"]: s["number"] for s in _load(OLD_CORPUS)}
    print(f"id map: {len(id_map)} standards remapped by IS number")

    for source, destination in JOBS:
        records = _load(source)
        remapped = [remap_record(r, id_map, number_of) for r in records]

        changed = sum(
            1 for a, b in zip(records, remapped) if a.get("correct_id") != b.get("correct_id")
        )
        print(
            f"  {source.name:<22} {len(records):>3} records, "
            f"{changed} ids changed -> {destination.relative_to(_REPO_ROOT)}"
        )

        if not args.check:
            destination.write_text(
                json.dumps(remapped, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    if args.check:
        print("(--check: nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
