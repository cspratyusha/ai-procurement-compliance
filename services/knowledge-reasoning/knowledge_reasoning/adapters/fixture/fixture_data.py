"""Parses fixtures/*.yaml into plain Python structures.

Shared by the in-memory fixture-backed port implementations (this package)
and `loader/fixture_loader.py`, which writes the same parsed structures into
a real Neo4j/Postgres. One parser, two destinations — so "the loader takes
Teammate 1's real data unchanged, in the same format" is actually true: both
paths read exactly this shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from contracts.is_number import canonicalise_is_number

DEFAULT_FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "fixtures"


@dataclass(frozen=True)
class FixtureNode:
    is_number: str
    title: str
    scope_text: str | None
    status: str  # active | superseded | withdrawn
    edition: str | None
    category: str | None
    verified: bool
    last_amended: str | None = None  # raw ISO date string, optional in fixtures


@dataclass(frozen=True)
class FixtureEdge:
    type: str  # matches a schema_map.RELATIONSHIP_TYPES key
    from_is_number: str  # already-canonicalised where it refers to a Standard
    to_value: str  # a Standard is_number, OR a category name for belongs_to
    verified: bool
    overlap_score: float | None = None


@dataclass(frozen=True)
class FixtureAmendment:
    is_number: str
    amendment_number: str
    date_issued: date
    change_summary: str
    verified: bool


@dataclass(frozen=True)
class FixtureCertRule:
    product_category: str
    standard_is_number: str | None
    scheme: str
    mandatory: bool
    required_evidence: list[str]
    notification_reference: str | None
    effective_date: date | None
    source_url: str | None
    verified: bool


@dataclass(frozen=True)
class FixtureDomain:
    name: str
    nodes: list[FixtureNode]
    edges: list[FixtureEdge]
    amendments: list[FixtureAmendment] = field(default_factory=list)
    certification_rules: list[FixtureCertRule] = field(default_factory=list)


def _is_standard_edge_target(edge_type: str) -> bool:
    # belongs_to's `to` is a category name, not a Standard is_number — every
    # other relationship type points Standard -> Standard.
    return edge_type != "belongs_to"


def _load_yaml_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or []


def load_fixture_domain(domain_dir: Path) -> FixtureDomain:
    nodes = [
        FixtureNode(
            is_number=canonicalise_is_number(n["is_number"]),
            title=n["title"],
            scope_text=n.get("scope_text"),
            status=n["status"],
            edition=n.get("edition"),
            category=n.get("category"),
            verified=bool(n["verified"]),
            last_amended=n.get("last_amended"),
        )
        for n in _load_yaml_list(domain_dir / "nodes.yaml")
    ]

    edges = []
    for e in _load_yaml_list(domain_dir / "edges.yaml"):
        edge_type = e["type"]
        from_number = canonicalise_is_number(e["from"])
        to_value = (
            canonicalise_is_number(e["to"])
            if _is_standard_edge_target(edge_type)
            else e["to"]
        )
        edges.append(
            FixtureEdge(
                type=edge_type,
                from_is_number=from_number,
                to_value=to_value,
                verified=bool(e["verified"]),
                overlap_score=e.get("overlap_score"),
            )
        )

    amendments = [
        FixtureAmendment(
            is_number=canonicalise_is_number(a["is_number"]),
            amendment_number=a["amendment_number"],
            date_issued=a["date_issued"],
            change_summary=a["change_summary"],
            verified=bool(a["verified"]),
        )
        for a in _load_yaml_list(domain_dir / "amendments.yaml")
    ]

    certification_rules = [
        FixtureCertRule(
            product_category=c["product_category"],
            standard_is_number=(
                canonicalise_is_number(c["standard_is_number"])
                if c.get("standard_is_number")
                else None
            ),
            scheme=c["scheme"],
            mandatory=bool(c["mandatory"]),
            required_evidence=list(c.get("required_evidence") or []),
            notification_reference=c.get("notification_reference"),
            effective_date=c.get("effective_date"),
            source_url=c.get("source_url"),
            verified=bool(c["verified"]),
        )
        for c in _load_yaml_list(domain_dir / "certification_rules.yaml")
    ]

    return FixtureDomain(
        name=domain_dir.name,
        nodes=nodes,
        edges=edges,
        amendments=amendments,
        certification_rules=certification_rules,
    )


def load_all_fixture_domains(fixtures_root: Path = DEFAULT_FIXTURES_ROOT) -> list[FixtureDomain]:
    domains = []
    for entry in sorted(fixtures_root.iterdir()):
        if entry.is_dir() and (entry / "nodes.yaml").exists():
            domains.append(load_fixture_domain(entry))
    return domains
