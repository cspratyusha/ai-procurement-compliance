"""The only module in this codebase permitted to contain SQL.

Same rule as `graph/queries.py`: table and column names are interpolated
from `config.schema_map` (validated identifiers only, table-scoped — see
that module's `DEFAULT_COLUMN_NAMES` docstring); every value is bound as a
`%(name)s` parameter, never string-formatted into the query.

Shape confirmed against Teammate 1's real, operative schema
(`data/schema.sql`, integration Stage A/B — see INTEGRATION.md "which
Part 1 is authoritative"), not the originally-guessed
`07_Data_Flow_And_Databases.md` shape:

- `standards.category` is a flat string, populated for every real row
  (Stage C: 18/18). `product_category_id` exists but is never populated —
  kept as a secondary/aspirational path, never the primary read.
- `certification_rules` has no FK columns at all — `(category, scheme_type,
  mandatory)` only, matched by plain string equality, never a join.
- Real amendments are modelled as separate `Standard` rows linked by an
  `AMENDED_BY` relationship, not rows in `amendments` (which exists but is
  never populated by the real ingestion path). `get_version_status`
  (in the repository adapter, not here) unions both sources.
- There is no `verified` column anywhere. `VersionStatus.data_verified` /
  `verification_reason` are derived from `source_url`/`source_checked_at`
  in the repository adapter, not selected as a plain column.

These reads are literal, one-hop reads of what's stored, not chain-walking
business logic. Composing them into the external contracts (`VersionStatus`,
`CertificationRequirement`) happens in the repository adapter, not here.
"""

from __future__ import annotations

from knowledge_reasoning.config.schema_map import SchemaMap


def build_get_standard_query(schema: SchemaMap) -> str:
    """One standard's core metadata, including its flat category and the
    raw provenance columns the `verified` derivation reads. Bound
    parameter: `%(is_number)s`."""
    standards = schema.table("standards")
    return f"""
SELECT
    s.{schema.column('standards', 'standard_number')} AS is_number,
    s.{schema.column('standards', 'title')} AS title,
    s.{schema.column('standards', 'scope_text')} AS scope_text,
    s.{schema.column('standards', 'status')} AS status,
    s.{schema.column('standards', 'current_version')} AS edition,
    s.{schema.column('standards', 'last_amended')} AS last_amended,
    s.{schema.column('standards', 'category')} AS category,
    s.{schema.column('standards', 'source_url')} AS source_url,
    s.{schema.column('standards', 'source_checked_at')} AS source_checked_at
FROM {standards} s
WHERE s.{schema.column('standards', 'standard_number')} = %(is_number)s
""".strip()


def build_get_version_row_query(schema: SchemaMap) -> str:
    """One standard's version/supersession/provenance facts (self-joined to
    resolve the superseded-by standard's own number). Bound parameter:
    `%(is_number)s`."""
    standards = schema.table("standards")
    return f"""
SELECT
    s.{schema.column('standards', 'standard_number')} AS is_number,
    s.{schema.column('standards', 'status')} AS status,
    s.{schema.column('standards', 'current_version')} AS current_edition,
    s.{schema.column('standards', 'source_url')} AS source_url,
    s.{schema.column('standards', 'source_checked_at')} AS source_checked_at,
    succ.{schema.column('standards', 'standard_number')} AS superseded_by
FROM {standards} s
LEFT JOIN {standards} succ
    ON s.{schema.column('standards', 'superseded_by_id')} = succ.{schema.column('standards', 'id')}
WHERE s.{schema.column('standards', 'standard_number')} = %(is_number)s
""".strip()


def build_get_amendments_query(schema: SchemaMap) -> str:
    """A standard's amendments from the `amendments` table, oldest first —
    a secondary source, since real amendments are (also, or instead)
    modelled as AMENDED_BY-linked Standard rows; the repository adapter
    unions both. Bound parameter: `%(is_number)s`."""
    standards = schema.table("standards")
    amendments = schema.table("amendments")
    return f"""
SELECT
    a.{schema.column('amendments', 'amendment_number')} AS amendment_number,
    a.{schema.column('amendments', 'date_issued')} AS date_issued,
    a.{schema.column('amendments', 'change_summary')} AS change_summary
FROM {amendments} a
JOIN {standards} s
    ON a.{schema.column('amendments', 'standard_id')} = s.{schema.column('standards', 'id')}
WHERE s.{schema.column('standards', 'standard_number')} = %(is_number)s
ORDER BY a.{schema.column('amendments', 'date_issued')} ASC
""".strip()


def build_get_product_category_query(schema: SchemaMap) -> str:
    """A standard's category — the flat `standards.category` column
    (property strategy's real, working source). Bound parameter:
    `%(is_number)s`."""
    standards = schema.table("standards")
    return f"""
SELECT s.{schema.column('standards', 'category')} AS category
FROM {standards} s
WHERE s.{schema.column('standards', 'standard_number')} = %(is_number)s
""".strip()


def build_get_certification_rules_query(schema: SchemaMap) -> str:
    """Certification rules for a product category — flat equality match,
    no join (Teammate 1's real table has no FK columns at all). Bound
    parameter: `%(category)s`.

    Only `category`, `scheme_type`, `mandatory` are selected. The
    traceability fields (`required_evidence`, `notification_reference`,
    `effective_date`, `source_url`) and `standard_is_number` scoping don't
    exist in Teammate 1's real schema — the repository adapter defaults
    them (None/[] /None) in code rather than this query pretending they
    can be selected. See INTEGRATION.md, "certification traceability".
    """
    rules = schema.table("certification_rules")
    return f"""
SELECT
    cr.{schema.column('certification_rules', 'category')} AS category,
    cr.{schema.column('certification_rules', 'scheme_type')} AS scheme,
    cr.{schema.column('certification_rules', 'mandatory')} AS mandatory
FROM {rules} cr
WHERE cr.{schema.column('certification_rules', 'category')} = %(category)s
""".strip()


def build_expand_query(schema: SchemaMap) -> str:
    """Recursive-CTE graph expansion over `standard_relationships`, the
    Postgres-backed alternative to Neo4j traversal (integration Stage A/B:
    there is no real Neo4j data; this table is where the real relationship
    data actually lives).

    Bound parameters: `seeds` (text[]), `max_hops` (int),
    `outgoing_types`/`incoming_types`/`either_types` (text[] — cluster-
    membership relationship-type names split by `RelSpec.direction`, same
    as every other backend), `all_known_types` (text[] — every name in
    `SchemaMap.relationship_types`, membership or not, e.g. also
    SUPERSEDED_BY/OVERLAPS_SCOPE_WITH/BELONGS_TO).

    A hop is only followed if its type+direction matches a configured
    membership role (the three `*_types` lists), OR the type isn't in
    `all_known_types` at all — the fallback bucket (decision 3): an edge
    with no configured mapping is still traversed and returned (as
    `role=NULL`, which the caller maps to `EdgeType.RELATED_UNCLASSIFIED`
    and counts), rather than silently invisible the way it was before this
    existed. A *recognised but non-membership* type (in `all_known_types`
    but not in any `*_types` list — supersession, overlap, category) is
    excluded from both traversal and result, exactly as before: those are
    read via their own dedicated accessors, never via expand().

    Semantics matched to `Neo4jGraphRepository`/`FixtureGraphRepository`:
    a node is excluded once it's an original seed or already appears in its
    own path (cycle safety), and each reachable node is returned exactly
    once, at its shortest hop distance (`DISTINCT ON`), same as the
    BFS-with-global-visited-set the other two backends do.
    """
    relationships = schema.table("standard_relationships")
    source_col = schema.column("standard_relationships", "source_id")
    target_col = schema.column("standard_relationships", "target_id")
    type_col = schema.column("standard_relationships", "type")
    return f"""
WITH RECURSIVE traversal AS (
    SELECT
        seed_value AS node_id,
        seed_value AS seed,
        ARRAY[seed_value]::text[] AS path,
        0 AS hop,
        NULL::text AS role
    FROM unnest(%(seeds)s::text[]) AS seed_value

    UNION ALL

    SELECT
        next_hop.node_id,
        t.seed,
        t.path || next_hop.node_id,
        t.hop + 1,
        next_hop.rel_type
    FROM traversal t
    CROSS JOIN LATERAL (
        SELECT sr.{target_col} AS node_id, sr.{type_col} AS rel_type, 'outgoing' AS actual_dir
        FROM {relationships} sr
        WHERE sr.{source_col} = t.node_id
        UNION ALL
        SELECT sr.{source_col} AS node_id, sr.{type_col} AS rel_type, 'incoming' AS actual_dir
        FROM {relationships} sr
        WHERE sr.{target_col} = t.node_id
    ) next_hop
    WHERE t.hop < %(max_hops)s
      AND NOT (next_hop.node_id = ANY(t.path))
      AND NOT (next_hop.node_id = ANY(%(seeds)s::text[]))
      AND (
            (next_hop.rel_type = ANY(%(outgoing_types)s::text[]) AND next_hop.actual_dir = 'outgoing')
         OR (next_hop.rel_type = ANY(%(incoming_types)s::text[]) AND next_hop.actual_dir = 'incoming')
         OR (next_hop.rel_type = ANY(%(either_types)s::text[]))
         OR NOT (next_hop.rel_type = ANY(%(all_known_types)s::text[]))
      )
)
SELECT DISTINCT ON (node_id) node_id AS target, seed, path, hop, role
FROM traversal
WHERE hop > 0
ORDER BY node_id, hop ASC
""".strip()


def build_get_relationship_query(schema: SchemaMap) -> str:
    """Direct (one-hop) neighbours of a single standard via a single named
    relationship type, both directions — used for `get_supersession`
    (direction-aware) and `get_curated_overlaps`. Bound parameters:
    `is_number`, `type_name`.

    Returns rows of (direction, neighbour) where direction is
    'source' (is_number was the source) or 'target' (is_number was the
    target) — the caller applies `RelSpec.direction` to interpret which
    one means what, exactly as `graph/queries.py`'s Cypher builders do.
    """
    relationships = schema.table("standard_relationships")
    standards = schema.table("standards")
    source_col = schema.column("standard_relationships", "source_id")
    target_col = schema.column("standard_relationships", "target_id")
    type_col = schema.column("standard_relationships", "type")
    return f"""
SELECT 'source' AS direction, tgt.{schema.column('standards', 'standard_number')} AS neighbour
FROM {relationships} sr
JOIN {standards} s ON sr.{source_col} = s.{schema.column('standards', 'id')}
JOIN {standards} tgt ON sr.{target_col} = tgt.{schema.column('standards', 'id')}
WHERE s.{schema.column('standards', 'standard_number')} = %(is_number)s AND sr.{type_col} = %(type_name)s
UNION ALL
SELECT 'target' AS direction, src.{schema.column('standards', 'standard_number')} AS neighbour
FROM {relationships} sr
JOIN {standards} s ON sr.{target_col} = s.{schema.column('standards', 'id')}
JOIN {standards} src ON sr.{source_col} = src.{schema.column('standards', 'id')}
WHERE s.{schema.column('standards', 'standard_number')} = %(is_number)s AND sr.{type_col} = %(type_name)s
""".strip()


def build_get_curated_overlaps_query(schema: SchemaMap) -> str:
    """Curated overlap edges among a given set of standards. Bound
    parameters: `is_numbers` (text[]), `type_name`. No `overlap_score`
    column exists in Teammate 1's real schema — the caller defaults it,
    same as the Neo4j path does for an absent property."""
    relationships = schema.table("standard_relationships")
    standards = schema.table("standards")
    return f"""
SELECT
    a.{schema.column('standards', 'standard_number')} AS is_a,
    b.{schema.column('standards', 'standard_number')} AS is_b
FROM {relationships} sr
JOIN {standards} a ON sr.{schema.column('standard_relationships', 'source_id')} = a.{schema.column('standards', 'id')}
JOIN {standards} b ON sr.{schema.column('standard_relationships', 'target_id')} = b.{schema.column('standards', 'id')}
WHERE sr.{schema.column('standard_relationships', 'type')} = %(type_name)s
  AND a.{schema.column('standards', 'standard_number')} = ANY(%(is_numbers)s::text[])
  AND b.{schema.column('standards', 'standard_number')} = ANY(%(is_numbers)s::text[])
""".strip()


# ---------------------------------------------------------------------------
# Writes (loader) — mirror the real shape above, for fixture-mode Postgres
# testing (db/schema.sql). No product_categories writes: that table exists
# in the real schema but is never populated by the real ingestion path
# either (category is flat on `standards`), so there is nothing faithful
# to mirror by writing to it.
# ---------------------------------------------------------------------------


def build_upsert_standard_query(schema: SchemaMap) -> str:
    """Bound parameters: id, is_number, title, scope_text, status, edition,
    last_amended, category. `id` is caller-supplied (Teammate 1's real PK
    has no default/serial — the loader uses the canonical IS number as a
    stable, idempotent id for fixture rows)."""
    standards = schema.table("standards")
    return f"""
INSERT INTO {standards} (
    {schema.column('standards', 'id')}, {schema.column('standards', 'standard_number')},
    {schema.column('standards', 'title')}, {schema.column('standards', 'scope_text')},
    {schema.column('standards', 'status')}, {schema.column('standards', 'current_version')},
    {schema.column('standards', 'last_amended')}, {schema.column('standards', 'category')}
)
VALUES (
    %(id)s, %(is_number)s, %(title)s, %(scope_text)s, %(status)s, %(edition)s,
    %(last_amended)s, %(category)s
)
ON CONFLICT ({schema.column('standards', 'standard_number')}) DO UPDATE SET
    {schema.column('standards', 'title')} = EXCLUDED.{schema.column('standards', 'title')},
    {schema.column('standards', 'scope_text')} = EXCLUDED.{schema.column('standards', 'scope_text')},
    {schema.column('standards', 'status')} = EXCLUDED.{schema.column('standards', 'status')},
    {schema.column('standards', 'current_version')} = EXCLUDED.{schema.column('standards', 'current_version')},
    {schema.column('standards', 'last_amended')} = EXCLUDED.{schema.column('standards', 'last_amended')},
    {schema.column('standards', 'category')} = EXCLUDED.{schema.column('standards', 'category')}
""".strip()


def build_set_superseded_by_query(schema: SchemaMap) -> str:
    """Set the superseded_by FK after both rows exist (avoids ordering
    issues during load). Bound parameters: is_number, superseded_by_number."""
    standards = schema.table("standards")
    return f"""
UPDATE {standards} SET {schema.column('standards', 'superseded_by_id')} = (
    SELECT {schema.column('standards', 'id')} FROM {standards}
    WHERE {schema.column('standards', 'standard_number')} = %(superseded_by_number)s
)
WHERE {schema.column('standards', 'standard_number')} = %(is_number)s
""".strip()


def build_upsert_amendment_query(schema: SchemaMap) -> str:
    """Bound parameters: id, is_number, amendment_number, date_issued,
    change_summary. `id` is caller-supplied for the same reason as
    `build_upsert_standard_query`; idempotency comes from the (standard_id,
    amendment_number) unique constraint in db/schema.sql."""
    standards = schema.table("standards")
    amendments = schema.table("amendments")
    return f"""
INSERT INTO {amendments} (
    {schema.column('amendments', 'id')}, {schema.column('amendments', 'standard_id')}, {schema.column('amendments', 'amendment_number')},
    {schema.column('amendments', 'date_issued')}, {schema.column('amendments', 'change_summary')}
)
SELECT %(id)s, s.{schema.column('standards', 'id')}, %(amendment_number)s, %(date_issued)s, %(change_summary)s
FROM {standards} s WHERE s.{schema.column('standards', 'standard_number')} = %(is_number)s
ON CONFLICT (standard_id, amendment_number) DO NOTHING
""".strip()


def build_upsert_standard_relationship_query(schema: SchemaMap) -> str:
    """Bound parameters: source_id, target_id, type. `source_id`/`target_id`
    are canonical IS numbers, reused as the `standards.id` (see
    `build_upsert_standard_query`). No `overlap_score` column exists in
    Teammate 1's real schema — `PostgresGraphRepository.get_curated_overlaps`
    defaults it to 1.0, same as the Neo4j path defaults an absent property."""
    relationships = schema.table("standard_relationships")
    source_col = schema.column("standard_relationships", "source_id")
    target_col = schema.column("standard_relationships", "target_id")
    type_col = schema.column("standard_relationships", "type")
    return f"""
INSERT INTO {relationships} ({source_col}, {target_col}, {type_col})
VALUES (%(source_id)s, %(target_id)s, %(type)s)
ON CONFLICT ({source_col}, {target_col}, {type_col}) DO NOTHING
""".strip()


def build_upsert_certification_rule_query(schema: SchemaMap) -> str:
    """Idempotent on (category, scheme_type) — Teammate 1's real primary
    key. Bound parameters: category, scheme, mandatory."""
    rules = schema.table("certification_rules")
    category_col = schema.column("certification_rules", "category")
    scheme_col = schema.column("certification_rules", "scheme_type")
    mandatory_col = schema.column("certification_rules", "mandatory")
    return f"""
INSERT INTO {rules} ({category_col}, {scheme_col}, {mandatory_col})
VALUES (%(category)s, %(scheme)s, %(mandatory)s)
ON CONFLICT ({category_col}, {scheme_col}) DO UPDATE SET
    {mandatory_col} = EXCLUDED.{mandatory_col}
""".strip()
