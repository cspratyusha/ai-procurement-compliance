"""The single place graph/db schema names and shapes are configured.

`graph/queries.py` and `db/queries.py` are the only modules permitted to
contain Cypher/SQL, and both build every query by interpolating names out of
this module — never a hardcoded label, relationship type, table, or column
name anywhere else in the codebase. When Teammate 1's real schema differs
from what's guessed here, this file (or `schema_map.yaml`) is the only thing
that needs to change.

Direction matters as much as the name
--------------------------------------
`SUPERSEDES` and `SUPERSEDED_BY` are not a naming difference — they assert
opposite facts. A relationship-type entry that carries only a name and lets
the reader assume a direction is a latent bug: the day the name is swapped
for a same-named-but-reversed edge, traversal silently inverts (e.g. the
freshness checker starts reporting current standards as withdrawn) with no
error raised anywhere. So every relationship in this map is a `RelSpec`
carrying both a name and an explicit direction, and `tests/test_schema_contract.py`
asserts direction behaviourally (not just "the relationship type exists"),
using a known superseded/superseding pair seeded into the fixture.

Identifier safety
------------------
Every label, relationship type, table, and column name here is interpolated
directly into Cypher/SQL strings (never as a bound query parameter — Cypher
does not allow binding schema names as parameters). That makes each of these
values a structural part of the query, not user data — but it is still an
injection surface if a malformed or malicious value ever reached this map
(e.g. from a YAML override). Every value is validated against a strict
identifier pattern at load time, in `validate()`, called once at process
startup by `load_schema_map()` — never lazily at query time, so a bad config
fails loudly before anything talks to a database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

Direction = Literal["outgoing", "incoming", "either"]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VALID_DIRECTIONS = {"outgoing", "incoming", "either"}


class SchemaMapError(ValueError):
    """A schema map (default or YAML-loaded) failed validation at load time."""


@dataclass(frozen=True)
class RelSpec:
    """A relationship type plus its direction, relative to the seed node in
    an expansion traversal: 'outgoing' means `(seed)-[:NAME]->(neighbour)`,
    'incoming' means `(neighbour)-[:NAME]->(seed)`, 'either' means the
    relationship is semantically symmetric and matched undirected.
    """

    name: str
    direction: Direction

    def __post_init__(self) -> None:
        _validate_identifier(self.name, context=f"RelSpec.name={self.name!r}")
        if self.direction not in _VALID_DIRECTIONS:
            raise SchemaMapError(
                f"RelSpec direction must be one of {sorted(_VALID_DIRECTIONS)}, "
                f"got {self.direction!r} for relationship {self.name!r}"
            )


def _validate_identifier(value: str, *, context: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.match(value):
        raise SchemaMapError(
            f"invalid identifier {value!r} ({context}): must match "
            f"{_IDENTIFIER_RE.pattern!r} to be safely interpolated into "
            f"Cypher/SQL"
        )
    return value


# ---------------------------------------------------------------------------
# Defaults. These follow Solution_details/07_Data_Flow_And_Databases.md
# wherever the planning docs speak, and the original Part 3 brief wherever
# the docs are silent — see INTEGRATION.md for the full list of divergences
# and what needs to be confirmed with Teammate 1.
# ---------------------------------------------------------------------------

DEFAULT_NODE_LABELS: dict[str, str] = {
    "standard": "Standard",
    "product_category": "ProductCategory",
    "certification_scheme": "CertificationScheme",
}

# Keys for cluster-membership roles match `contracts.cluster.EdgeType.value`
# exactly, so `RELATIONSHIP_TYPES[edge_type.value]` always resolves. A few
# extra keys exist for graph relationships that are not cluster-membership
# roles (supersession, overlap, category).
DEFAULT_RELATIONSHIP_TYPES: dict[str, RelSpec] = {
    # Cluster-membership roles (contracts.cluster.EdgeType) -----------------
    # Docs: (Standard)-[:NORMATIVE_REFERENCE]->(Standard) — seed references
    # the target normatively, so seed -> target is outgoing.
    "normative_reference": RelSpec("NORMATIVE_REFERENCE", "outgoing"),
    # Docs: (TestMethodStandard)-[:TEST_METHOD_FOR]->(ProductStandard) — when
    # the seed is the product standard, its test methods are reached by
    # walking the edge backwards, i.e. incoming.
    "test_method_for": RelSpec("TEST_METHOD_FOR", "incoming"),
    "terminology_for": RelSpec("TERMINOLOGY_FOR", "incoming"),
    "safety_requirement_for": RelSpec("SAFETY_REQUIREMENT_FOR", "incoming"),
    # CORRECTED against real data (integration Stage B): the demo corpus's
    # one real INSTALLATION_GUIDE_FOR edge is (ProductStandard)->(InstallationCode)
    # — IS 694:2010 -> IS 732:2019 — the opposite of the guessed direction
    # below this replaced. With the old "incoming" setting, expand() from
    # IS 694:2010 (the frontend's own worked example) returned zero allied
    # standards. Confirmed correct now via the same real pair.
    "installation_guide_for": RelSpec("INSTALLATION_GUIDE_FOR", "outgoing"),
    # Confirmed real (Stage C): IS 2062:2011 -> IS 800:2007, product ->
    # design code, same direction and role as INSTALLATION_GUIDE_FOR.
    "design_code_for": RelSpec("DESIGN_CODE_FOR", "outgoing"),
    # Docs are silent on both of these — see INTEGRATION.md.
    "related_product": RelSpec("RELATED_PRODUCT", "either"),
    "amended_by": RelSpec("AMENDED_BY", "outgoing"),
    # Three more real, domain-specific "related" variants (Stage C),
    # symmetric like RELATED_PRODUCT — real data's own direction is
    # arbitrary per pair, not semantically meaningful either way.
    "complementary_part": RelSpec("COMPLEMENTARY_PART", "either"),
    "related_ppe": RelSpec("RELATED_PPE", "either"),
    "related_piping": RelSpec("RELATED_PIPING", "either"),
    # Non-membership relationships --------------------------------------
    # Docs: (Standard)-[:SUPERSEDED_BY]->(Standard), old -> new. Outgoing
    # from an old standard reaches its successor; walking outgoing
    # repeatedly reaches the current edition.
    "superseded_by": RelSpec("SUPERSEDED_BY", "outgoing"),
    "overlaps_scope_with": RelSpec("OVERLAPS_SCOPE_WITH", "either"),
    "belongs_to": RelSpec("BELONGS_TO", "outgoing"),
}

DEFAULT_PROPERTY_NAMES: dict[str, str] = {
    # CONFIRMED against Teammate 1's real (if unpopulated) Neo4j client
    # (app/db/neo4j_client.py) during integration Stage A/B: Standard nodes
    # use `number`, not `is_number`.
    "is_number": "number",
    "title": "title",
    "scope_text": "scope_text",
    "status": "status",  # active / superseded / withdrawn
    "edition": "edition_year",
    # ProductCategory nodes are merged on `id`; `name` is the display
    # property — confirmed from neo4j_client.upsert_category.
    "category_name": "name",
    "overlap_score": "overlap_score",  # optional property on OVERLAPS_SCOPE_WITH
    # Not present in either of Teammate 1's schemas at all. Was a flat
    # config guess; superseded by real derivation logic in Phase 3's
    # freshness checker (VersionStatus.data_verified / verification_reason),
    # not a column lookup — see db/queries.py and INTEGRATION.md. Left here
    # only for the (currently unpopulated, aspirational) Neo4j path, should
    # Teammate 1 ever add it.
    "verified": "verified",
}

DEFAULT_TABLE_NAMES: dict[str, str] = {
    "standards": "standards",
    "amendments": "amendments",
    "certification_rules": "certification_rules",
    "product_categories": "product_categories",
    # Confirmed real (data/schema.sql): the graph relationship data itself
    # lives here, not in Neo4j — see PostgresGraphRepository.
    "standard_relationships": "standard_relationships",
}

# Table-scoped: column_names[table_key][logical_name] = actual_name.
#
# This replaced a flat dict during integration with Teammate 1's real
# schema (data/schema.sql). The flat version broke on the first real
# cross-table join: `standards`' own PK is `id`, but `amendments`' FK
# pointing at it is `standard_id` — two different real column names for
# the same concept, in different tables. One flat key cannot represent
# both without ambiguity ("standard_id" -> "id" would then be silently
# wrong for `amendments.standard_id`, which really is called that).
# Scoping by table removes the ambiguity structurally rather than by
# convention. See INTEGRATION.md, "table-scoped column map".
DEFAULT_COLUMN_NAMES: dict[str, dict[str, str]] = {
    "standards": {
        "id": "id",
        # CONFIRMED against data/schema.sql (Teammate 1's real, operative
        # schema — see INTEGRATION.md "which Part 1 is authoritative").
        "standard_number": "number",
        "title": "title",
        "scope_text": "scope",
        "status": "status",
        "current_version": "version",
        "last_amended": "last_amended",
        # Flat string column, populated for every real standard (confirmed
        # Stage C: 18/18). This is the real, working category source —
        # `product_category_id` below exists in their schema but is never
        # populated by their ingestion path; kept only in case that changes.
        "category": "category",
        "superseded_by_id": "superseded_by_id",
        "product_category_id": "product_category_id",
        "sector": "sector",
        # Used by the `verified` derivation (VersionStatus.data_verified /
        # verification_reason) — see db/queries.py, not a column rename.
        "source_url": "source_url",
        "source_checked_at": "source_checked_at",
    },
    "amendments": {
        "id": "amendment_id",
        "standard_id": "standard_id",  # FK into standards.id — real table is empty in practice; see AMENDED_BY-edge amendments in db/queries.py
        "amendment_number": "amendment_number",
        "date_issued": "date_issued",
        "change_summary": "change_summary",
    },
    "certification_rules": {
        # Flat TEXT match against standards.category — Teammate 1's real
        # table has no product_category_id/standard_id FK columns at all
        # (confirmed Stage A/B), so this is a WHERE equality, never a join.
        "category": "category",
        "scheme_type": "scheme_type",
        "mandatory": "mandatory",
        # None of these four exist in Teammate 1's real schema (confirmed
        # Stage A/B) — kept as the aspirational config target for if/when
        # they're added. The query that would read them defaults them to
        # None/[] in code rather than selecting nonexistent columns; see
        # db/queries.py and INTEGRATION.md, "certification traceability".
        "notification_reference": "notification_reference",
        "effective_date": "effective_date",
        "source_url": "source_url",
        "required_evidence": "required_evidence",
    },
    "product_categories": {
        "id": "category_id",
        "name": "name",
    },
    "standard_relationships": {
        "source_id": "source_id",
        "target_id": "target_id",
        "type": "type",
    },
}

# Which store is authoritative for product category, per decision: Postgres
# is the documented source of truth and Neo4j's BELONGS_TO edge is a derived
# projection of it, so "property" (Postgres) is primary by default. The
# fallback strategy is always tried if the primary returns nothing, so a
# repository implementation can still answer if only one side is populated.
CategoryStrategy = Literal["property", "edge"]
DEFAULT_CATEGORY_STRATEGY: CategoryStrategy = "property"


@dataclass(frozen=True)
class SchemaMap:
    node_labels: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_NODE_LABELS))
    relationship_types: dict[str, RelSpec] = field(
        default_factory=lambda: dict(DEFAULT_RELATIONSHIP_TYPES)
    )
    property_names: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_PROPERTY_NAMES)
    )
    table_names: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TABLE_NAMES))
    column_names: dict[str, dict[str, str]] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_COLUMN_NAMES.items()}
    )
    category_strategy: CategoryStrategy = DEFAULT_CATEGORY_STRATEGY

    def label(self, key: str) -> str:
        return self.node_labels[key]

    def rel(self, key: str) -> RelSpec:
        return self.relationship_types[key]

    def prop(self, key: str) -> str:
        return self.property_names[key]

    def table(self, key: str) -> str:
        return self.table_names[key]

    def column(self, table_key: str, logical_key: str) -> str:
        """Table-scoped column lookup — see DEFAULT_COLUMN_NAMES' docstring
        for why this isn't a flat namespace."""
        return self.column_names[table_key][logical_key]

    def validate(self) -> None:
        """Fail loudly, at load time, if anything here is unsafe to
        interpolate into Cypher/SQL, or structurally inconsistent."""
        for key, label in self.node_labels.items():
            _validate_identifier(label, context=f"node_labels[{key!r}]")
        for key, spec in self.relationship_types.items():
            # RelSpec.__post_init__ already validated name + direction; this
            # re-check guards against a YAML override constructing a RelSpec
            # via a path that skips __post_init__ (e.g. `dataclasses.replace`
            # in future code) and against `key` itself being nonsense.
            _validate_identifier(spec.name, context=f"relationship_types[{key!r}].name")
            if spec.direction not in _VALID_DIRECTIONS:
                raise SchemaMapError(
                    f"relationship_types[{key!r}] has invalid direction "
                    f"{spec.direction!r}"
                )
        for key, prop in self.property_names.items():
            _validate_identifier(prop, context=f"property_names[{key!r}]")
        for key, table in self.table_names.items():
            _validate_identifier(table, context=f"table_names[{key!r}]")
        for table_key, columns in self.column_names.items():
            if not isinstance(columns, dict):
                raise SchemaMapError(
                    f"column_names[{table_key!r}] must be a mapping of "
                    f"logical name -> actual column name, got {columns!r}"
                )
            for logical_key, col in columns.items():
                _validate_identifier(
                    col, context=f"column_names[{table_key!r}][{logical_key!r}]"
                )
        if self.category_strategy not in ("property", "edge"):
            raise SchemaMapError(
                f"category_strategy must be 'property' or 'edge', got "
                f"{self.category_strategy!r}"
            )


def _merge_dict(base: dict, override: dict | None) -> dict:
    if not override:
        return dict(base)
    merged = dict(base)
    merged.update(override)
    return merged


def _merge_nested_dict(
    base: dict[str, dict[str, str]], override: dict | None
) -> dict[str, dict[str, str]]:
    """Two-level merge for table-scoped column_names: an override for one
    table's columns only replaces the keys it specifies, same as the
    flat-dict merge does for everything else."""
    merged = {table_key: dict(cols) for table_key, cols in base.items()}
    for table_key, cols in (override or {}).items():
        if not isinstance(cols, dict):
            raise SchemaMapError(
                f"column_names[{table_key!r}] override must be a mapping, "
                f"got {cols!r}"
            )
        merged.setdefault(table_key, {})
        merged[table_key].update(cols)
    return merged


def load_schema_map(yaml_path: str | Path | None = None) -> SchemaMap:
    """Build the effective schema map: defaults, overridden by a YAML file
    when one is given (env var `KR_SCHEMA_MAP_PATH`, or an explicit path).
    Always validates before returning — a bad map never reaches a caller.
    """
    schema = SchemaMap()

    if yaml_path is not None:
        path = Path(yaml_path)
        if not path.exists():
            raise SchemaMapError(f"schema map override file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        node_labels = _merge_dict(schema.node_labels, raw.get("node_labels"))

        rel_types = dict(schema.relationship_types)
        for key, entry in (raw.get("relationship_types") or {}).items():
            if not isinstance(entry, dict) or "name" not in entry or "direction" not in entry:
                raise SchemaMapError(
                    f"relationship_types[{key!r}] override must be a mapping "
                    f"with 'name' and 'direction', got {entry!r}"
                )
            rel_types[key] = RelSpec(name=entry["name"], direction=entry["direction"])

        property_names = _merge_dict(schema.property_names, raw.get("property_names"))
        table_names = _merge_dict(schema.table_names, raw.get("table_names"))
        column_names = _merge_nested_dict(schema.column_names, raw.get("column_names"))
        category_strategy = raw.get("category_strategy", schema.category_strategy)

        schema = SchemaMap(
            node_labels=node_labels,
            relationship_types=rel_types,
            property_names=property_names,
            table_names=table_names,
            column_names=column_names,
            category_strategy=category_strategy,
        )

    schema.validate()
    return schema


__all__ = [
    "CategoryStrategy",
    "Direction",
    "RelSpec",
    "SchemaMap",
    "SchemaMapError",
    "load_schema_map",
]
