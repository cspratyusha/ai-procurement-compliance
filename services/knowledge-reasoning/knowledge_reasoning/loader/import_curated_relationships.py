"""One-command importer for hand-curated cross-reference data, in the
exact shape of Teammate 1's real `data/raw/relationships.json`.

Context: integration Stage C measured the real corpus's graph as very
sparse (most standards have zero outgoing structural edges — see
`fixtures/sparse_real_topology/`). Fixing that corpus gap for real is a
data-curation problem, not a code problem, and the user is handling it
with the team directly. This tool exists only so a hand-curated addendum
file — written by a domain expert, in the exact format Teammate 1's own
pipeline already uses — can be loaded into this service's Postgres in one
command, without needing Teammate 1's `scripts/ingest.py` or a merge of
their repo. It does not generate, infer, or validate the cross-references
themselves; it only loads rows that are already believed correct.

Input shape (confirmed against the real file on `main`, read-only, never
copied into this repo): a JSON array of objects, each exactly
    {"source_id": "std_017", "target_id": "std_001", "type": "SUPERSEDED_BY"}

`source_id`/`target_id` are Teammate 1's real `standards.id` primary keys
(the same values `data/raw/standards.json`'s "id" field uses) — NOT IS
numbers, and NOT this codebase's own fixture convention of using the IS
number as `id` (see `loader/fixture_loader.py`). `type` is already the raw
upper-case relationship name (the `RelSpec.name` convention, e.g.
"NORMATIVE_REFERENCE"), not a schema_map key — curators are expected to
use the same vocabulary the real file already does.

A row whose `source_id`/`target_id` isn't an existing `standards.id` in
the target database is skipped and reported (never crashes the import —
same dangling-reference policy as `fixture_loader.load_into_postgres`). A
row whose `type` has no `config/schema_map.py` mapping is still written
(the fallback bucket, decision 3/Stage E.4) — it will read back as
`EdgeType.RELATED_UNCLASSIFIED`, and is reported so it isn't missed;
run `report_relationship_types.py --backend postgres` any time for the
full picture.

Idempotent: `ON CONFLICT (source_id, target_id, type) DO NOTHING`, so
re-running against a growing curated file is always safe.

Usage:
    python -m knowledge_reasoning.loader.import_curated_relationships path/to/relationships.json
    python -m knowledge_reasoning.loader.import_curated_relationships path/to/relationships.json --dsn postgresql://...
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from knowledge_reasoning.config.schema_map import SchemaMap, load_schema_map
from knowledge_reasoning.config.settings import load_settings
from knowledge_reasoning.db import queries as db_queries

logger = logging.getLogger(__name__)


class CurationImportError(RuntimeError):
    """The input file itself is malformed — wrong top-level type, or a row
    missing one of the three required fields. Distinct from an individual
    dangling reference, which is reported and skipped, not raised."""


@dataclass
class CurationImportReport:
    rows_read: int = 0
    rows_written: int = 0
    rows_dropped_dangling: list[tuple[str, str, str]] = field(default_factory=list)
    unmapped_types_seen: dict[str, int] = field(default_factory=dict)


def _validate_row(row: object, index: int) -> tuple[str, str, str]:
    if not isinstance(row, dict):
        raise CurationImportError(f"row {index}: expected an object, got {type(row).__name__}")
    for key in ("source_id", "target_id", "type"):
        if not isinstance(row.get(key), str) or not row[key]:
            raise CurationImportError(
                f"row {index}: missing or invalid {key!r} — expected the exact "
                f'data/raw/relationships.json shape: {{"source_id": ..., '
                f'"target_id": ..., "type": ...}}'
            )
    return row["source_id"], row["target_id"], row["type"]


def load_curated_relationships_file(path: Path) -> list[tuple[str, str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise CurationImportError(
            f"{path}: expected a JSON array (data/raw/relationships.json "
            f"shape), got {type(raw).__name__}"
        )
    return [_validate_row(row, i) for i, row in enumerate(raw)]


def import_curated_relationships(
    conn: psycopg.Connection, schema: SchemaMap, rows: list[tuple[str, str, str]]
) -> CurationImportReport:
    report = CurationImportReport(rows_read=len(rows))
    upsert = db_queries.build_upsert_standard_relationship_query(schema)
    known_names = {spec.name for spec in schema.relationship_types.values()}
    table = schema.table("standards")
    id_col = schema.column("standards", "id")

    with conn.cursor() as cur:
        cur.execute(f"SELECT {id_col} FROM {table}")
        existing_ids = {r[0] for r in cur.fetchall()}

        for source_id, target_id, rel_type in rows:
            if source_id not in existing_ids or target_id not in existing_ids:
                report.rows_dropped_dangling.append((rel_type, source_id, target_id))
                logger.warning(
                    "Skipping curated relationship %r (%s -> %s) — one or both "
                    "endpoints are not an existing standards.id in this database.",
                    rel_type,
                    source_id,
                    target_id,
                )
                continue
            if rel_type not in known_names:
                report.unmapped_types_seen[rel_type] = (
                    report.unmapped_types_seen.get(rel_type, 0) + 1
                )
                logger.warning(
                    "Curated relationship type %r (%s -> %s) has no schema_map "
                    "mapping — writing it anyway; it will surface as "
                    "RELATED_UNCLASSIFIED, not dropped.",
                    rel_type,
                    source_id,
                    target_id,
                )
            cur.execute(
                upsert, {"source_id": source_id, "target_id": target_id, "type": rel_type}
            )
            report.rows_written += 1

    conn.commit()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", type=Path, help="path to a relationships.json-shaped file")
    parser.add_argument("--dsn", default=None, help="defaults to KR_POSTGRES_DSN")
    args = parser.parse_args()

    settings = load_settings()
    dsn = args.dsn or settings.postgres_dsn
    if not dsn:
        print("No Postgres DSN available — pass --dsn or set KR_POSTGRES_DSN.", file=sys.stderr)
        return 1
    schema = load_schema_map(settings.schema_map_path)

    try:
        rows = load_curated_relationships_file(args.path)
    except CurationImportError as exc:
        print(f"Invalid input file: {exc}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read {args.path}: {exc}", file=sys.stderr)
        return 1

    with psycopg.connect(dsn) as conn:
        report = import_curated_relationships(conn, schema, rows)

    print(f"Read {report.rows_read} row(s), wrote {report.rows_written}.")
    if report.rows_dropped_dangling:
        print(
            f"\n{len(report.rows_dropped_dangling)} row(s) skipped — endpoint not "
            f"found in standards table:"
        )
        for rel_type, source_id, target_id in report.rows_dropped_dangling:
            print(f"  {rel_type}: {source_id} -> {target_id}")
    if report.unmapped_types_seen:
        total = sum(report.unmapped_types_seen.values())
        print(
            f"\n{total} row(s) used a relationship type with no schema_map "
            f"mapping (will read back as RELATED_UNCLASSIFIED):"
        )
        for rel_type, count in sorted(report.unmapped_types_seen.items()):
            print(f"  {rel_type}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
