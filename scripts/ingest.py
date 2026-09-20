"""Validate the demo standards corpus and rebuild its local data projections, FAISS/BM25 indices, and LTR models."""

from __future__ import annotations

import argparse
import json
import re
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

# Add project root to sys.path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SR_DIR = _REPO_ROOT / "app" / "services" / "standards_retrieval"
if str(_SR_DIR) not in sys.path:
    sys.path.insert(0, str(_SR_DIR))

from app.services.standards_retrieval.data.models import Standard
from app.services.standards_retrieval.indexing.embed_index import build_index as build_faiss_index
from app.services.standards_retrieval.indexing.bm25_index import build_index as build_bm25_index

REQUIRED_FIELDS = {
    "id", "number", "title", "scope", "description", "category",
    "version", "last_amended", "status", "keywords",
}
ALLOWED_STATUS = {"active", "superseded"}
ID_PATTERN = re.compile(r"^std_[0-9]{3,}$")


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def validate_standards(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list) or not records:
        raise ValueError("standards.json must contain a non-empty array")
    seen_ids: set[str] = set()
    seen_numbers: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"standard at index {index} must be an object")
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            raise ValueError(f"standard at index {index} is missing: {sorted(missing)}")
        if not isinstance(record["id"], str) or not ID_PATTERN.fullmatch(record["id"]):
            raise ValueError(f"invalid standard id at index {index}")
        if record["id"] in seen_ids or record["number"] in seen_numbers:
            raise ValueError(f"duplicate standard id or number at index {index}")
        if record["status"] not in ALLOWED_STATUS:
            raise ValueError(f"invalid status for {record['id']}: {record['status']}")
        try:
            date.fromisoformat(record["last_amended"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid last_amended for {record['id']}") from exc
        for field in ("number", "title", "scope", "description", "category", "version"):
            if not isinstance(record[field], str) or not record[field].strip():
                raise ValueError(f"{field} must be a non-empty string for {record['id']}")
        if (
            not isinstance(record["keywords"], list)
            or not record["keywords"]
            or not all(isinstance(keyword, str) and keyword.strip() for keyword in record["keywords"])
        ):
            raise ValueError(f"keywords must be a non-empty string array for {record['id']}")
        seen_ids.add(record["id"])
        seen_numbers.add(record["number"])
    return records


def validate_relationships(relationships: Any, ids: set[str]) -> list[dict[str, str]]:
    if not isinstance(relationships, list):
        raise ValueError("relationships.json must contain an array")
    for index, relation in enumerate(relationships):
        if (
            not isinstance(relation, dict)
            or set(relation) != {"source_id", "target_id", "type"}
            or relation["source_id"] not in ids
            or relation["target_id"] not in ids
            or not all(isinstance(value, str) and value.strip() for value in relation.values())
        ):
            raise ValueError(f"invalid relationship at index {index}")
    return relationships


def validate_certification_rules(rules: Any) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise ValueError("certification_rules.json must contain an array")
    for index, rule in enumerate(rules):
        if (
            not isinstance(rule, dict)
            or set(rule) != {"category", "scheme_type", "mandatory"}
            or not isinstance(rule["category"], str)
            or not isinstance(rule["scheme_type"], str)
            or not isinstance(rule["mandatory"], bool)
        ):
            raise ValueError(f"invalid certification rule at index {index}")
    return rules


def ingest_to_postgres(
    standards: list[dict[str, Any]],
    relationships: list[dict[str, str]],
    rules: list[dict[str, Any]],
    schema_path: Path,
    database_url: str
) -> None:
    """Writes standards, relationships, and rules to PostgreSQL."""
    try:
        import psycopg
        with psycopg.connect(database_url) as connection:
            connection.execute(schema_path.read_text(encoding="utf-8"))
            connection.execute("TRUNCATE audit_findings, interaction_logs, standard_relationships, certification_rules, standards")
            with connection.cursor() as cursor:
                cursor.executemany(
                    """INSERT INTO standards
                    (id, number, title, scope, description, category, version,
                     last_amended, status, keywords_json, superseded_by_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (
                            record["id"], record["number"], record["title"], record["scope"],
                            record["description"], record["category"], record["version"],
                            record["last_amended"], record["status"],
                            json.dumps(record["keywords"], ensure_ascii=False),
                            record.get("superseded_by_id"),
                        )
                        for record in standards
                    ],
                )
                cursor.executemany(
                    "INSERT INTO standard_relationships (source_id, target_id, type) VALUES (%s, %s, %s)",
                    [(relation["source_id"], relation["target_id"], relation["type"]) for relation in relationships],
                )
                cursor.executemany(
                    "INSERT INTO certification_rules (category, scheme_type, mandatory) VALUES (%s, %s, %s)",
                    [(rule["category"], rule["scheme_type"], rule["mandatory"]) for rule in rules],
                )
            connection.commit()
        print(f"[Stage 1/5: PostgreSQL] Ingested {len(standards)} standards, {len(relationships)} relationships, {len(rules)} rules.")
    except Exception as exc:
        print(f"[Stage 1/5: PostgreSQL] Notice: PostgreSQL write skipped ({exc}).")


def build_derived_projections(
    standards: list[dict[str, Any]],
    relationships: list[dict[str, str]],
    output_dir: Path
) -> None:
    """Builds static keyword-index.json and graph.json for downstream services."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "keyword-index.json").write_text(
        json.dumps(
            {
                record["id"]: {
                    "text": " ".join([record["number"], record["title"], record["scope"], *record["keywords"]]),
                    "category": record["category"],
                }
                for record in standards
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    (output_dir / "graph.json").write_text(
        json.dumps({"relationships": relationships}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[Stage 2/5: Derived Projections] Wrote keyword-index.json and graph.json to {output_dir}.")


def build_faiss_stage(standards_models: list[Standard], output_dir: Path) -> None:
    """Builds FAISS index with e5-base-v2 embeddings."""
    print(f"[Stage 3/5: FAISS Index] Building dense vector index for {len(standards_models)} standards...")
    build_faiss_index(
        corpus=standards_models,
        index_path=output_dir / "faiss.index",
        ids_path=output_dir / "faiss_ids.json"
    )
    # Also update service data directory
    sr_data_dir = _SR_DIR / "data"
    sr_data_dir.mkdir(parents=True, exist_ok=True)
    build_faiss_index(
        corpus=standards_models,
        index_path=sr_data_dir / "faiss.index",
        ids_path=sr_data_dir / "faiss_ids.json"
    )
    print(f"[Stage 3/5: FAISS Index] Successfully built and saved FAISS index.")


def build_bm25_stage(standards_models: list[Standard], output_dir: Path) -> None:
    """Builds BM25 index with codebase-consistent tokenizer."""
    print(f"[Stage 4/5: BM25 Index] Building sparse BM25 index for {len(standards_models)} standards...")
    build_bm25_index(
        corpus=standards_models,
        pkl_path=output_dir / "bm25.pkl",
        ids_path=output_dir / "bm25_ids.json",
        tokens_path=output_dir / "bm25_tokens.json"
    )
    # Also update service data directory
    sr_data_dir = _SR_DIR / "data"
    sr_data_dir.mkdir(parents=True, exist_ok=True)
    build_bm25_index(
        corpus=standards_models,
        pkl_path=sr_data_dir / "bm25.pkl",
        ids_path=sr_data_dir / "bm25_ids.json",
        tokens_path=sr_data_dir / "bm25_tokens.json"
    )
    print(f"[Stage 4/5: BM25 Index] Successfully built and saved BM25 index.")


def train_ltr_stage() -> None:
    """Trains the Learning-to-Rank LightGBM model from scratch."""
    print("[Stage 5/5: LTR Training] Starting LTR model training from scratch...")
    from app.services.standards_retrieval.ltr.train import main as train_ltr_main
    train_ltr_main()
    print("[Stage 5/5: LTR Training] LTR training complete.")


def rebuild(
    source_dir: Path,
    output_dir: Path,
    database_url: str,
    skip_db: bool = False,
    skip_faiss: bool = False,
    skip_bm25: bool = False,
    train_ltr: bool = False,
) -> None:
    standards_raw = validate_standards(load_json(source_dir / "standards.json"))
    ids = {record["id"] for record in standards_raw}
    relationships = validate_relationships(load_json(source_dir / "relationships.json"), ids)
    rules = validate_certification_rules(load_json(source_dir / "certification_rules.json"))
    
    schema_path = source_dir / "schema.sql"
    if not schema_path.exists():
        schema_path = source_dir.parent / "schema.sql"

    # Stage 1: PostgreSQL
    if not skip_db:
        ingest_to_postgres(standards_raw, relationships, rules, schema_path, database_url)

    # Stage 2: Derived JSON files
    build_derived_projections(standards_raw, relationships, output_dir)

    # Convert to Pydantic models for indexers
    standards_models = [Standard(**r) for r in standards_raw]

    # Stage 3: FAISS Dense Vector Index
    if not skip_faiss:
        build_faiss_stage(standards_models, output_dir)

    # Stage 4: BM25 Sparse Index
    if not skip_bm25:
        build_bm25_stage(standards_models, output_dir)

    # Stage 5: Optional LTR Training
    if train_ltr:
        train_ltr_stage()

    print(f"\n[Done] Pipeline complete. Ingested {len(standards_raw)} standards ({sum(1 for s in standards_raw if s['status'] == 'active')} active, {sum(1 for s in standards_raw if s['status'] == 'superseded')} superseded).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=_REPO_ROOT / "data" / "raw")
    parser.add_argument("--output", type=Path, default=_REPO_ROOT / "data" / "derived")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "postgresql://procurement:procurement@localhost:55432/procurement"))
    parser.add_argument("--skip-db", action="store_true", help="Skip PostgreSQL write stage")
    parser.add_argument("--skip-faiss", action="store_true", help="Skip FAISS index build")
    parser.add_argument("--skip-bm25", action="store_true", help="Skip BM25 index build")
    parser.add_argument("--train-ltr", action="store_true", help="Train LTR model on the ingested corpus")
    args = parser.parse_args()

    rebuild(
        source_dir=args.source,
        output_dir=args.output,
        database_url=args.database_url,
        skip_db=args.skip_db,
        skip_faiss=args.skip_faiss,
        skip_bm25=args.skip_bm25,
        train_ltr=args.train_ltr,
    )


if __name__ == "__main__":
    main()
