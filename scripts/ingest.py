"""Validate the demo standards corpus and rebuild its local data projections."""

from __future__ import annotations

import argparse
import json
import re
import os
from datetime import date
from pathlib import Path
from typing import Any

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


def rebuild(source_dir: Path, output_dir: Path, database_url: str) -> None:
    import psycopg

    standards = validate_standards(load_json(source_dir / "standards.json"))
    ids = {record["id"] for record in standards}
    relationships = validate_relationships(load_json(source_dir / "relationships.json"), ids)
    rules = validate_certification_rules(load_json(source_dir / "certification_rules.json"))
    schema_path = source_dir / "schema.sql"
    if not schema_path.exists():
        schema_path = source_dir.parent / "schema.sql"
    if not schema_path.exists():
        raise FileNotFoundError(f"schema.sql not found beside {source_dir}")

    with psycopg.connect(database_url) as connection:
        connection.execute(schema_path.read_text(encoding="utf-8"))
        connection.execute("TRUNCATE audit_findings, interaction_logs, standard_relationships, certification_rules, standards")
        with connection.cursor() as cursor:
            cursor.executemany(
            """INSERT INTO standards
            (id, number, title, scope, description, category, version,
             last_amended, status, keywords_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                (
                    record["id"], record["number"], record["title"], record["scope"],
                    record["description"], record["category"], record["version"],
                    record["last_amended"], record["status"],
                    json.dumps(record["keywords"], ensure_ascii=False),
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
    print(f"Ingested {len(standards)} standards, {len(relationships)} relationships and {len(rules)} certification rules.")


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repository_root / "data" / "raw")
    parser.add_argument("--output", type=Path, default=repository_root / "data" / "derived")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "postgresql://procurement:procurement@localhost:55432/procurement"))
    args = parser.parse_args()
    rebuild(args.source, args.output, args.database_url)


if __name__ == "__main__":
    main()
