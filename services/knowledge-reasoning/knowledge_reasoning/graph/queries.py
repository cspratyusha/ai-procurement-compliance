"""The only module in this codebase permitted to contain Cypher.

Every string built here interpolates *schema* names (labels, relationship
types, property names) — never user data, and never a raw query fragment
passed in from elsewhere. Values are always bound as `$parameters`, never
string-formatted into the query. Schema names are safe to interpolate only
because `config.schema_map` validates every one of them against a strict
identifier pattern at load time (`SchemaMap.validate()`), before any of
these functions ever run.

Read vs. write direction
-------------------------
`RelSpec.direction` describes, for a given relationship type, which side of
the (fixed, absolute) edge a typical *expansion seed* sits on — it exists to
build correct one-hop traversal patterns in `build_expand_one_hop_query`.
Writing edges (the loader) never consults it: fixture/ingested edge records
carry their own explicit `from`/`to`, matching the relationship's documented
absolute arrow direction (e.g. NORMATIVE_REFERENCE: referencer -> referenced;
TEST_METHOD_FOR: test-method-standard -> product-standard; SUPERSEDED_BY:
old -> new), and `build_merge_relationship_query` writes exactly that arrow.
See `fixtures/README.md` for the from/to convention per relationship type.
"""

from __future__ import annotations

from knowledge_reasoning.config.schema_map import Direction, RelSpec, SchemaMap


def _pattern(direction: Direction, rel_name: str, left: str, right: str) -> str:
    if direction == "outgoing":
        return f"({left})-[:{rel_name}]->({right})"
    if direction == "incoming":
        return f"({left})<-[:{rel_name}]-({right})"
    return f"({left})-[:{rel_name}]-({right})"


def _reverse(direction: Direction) -> Direction:
    if direction == "outgoing":
        return "incoming"
    if direction == "incoming":
        return "outgoing"
    return "either"


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def build_expand_one_hop_query(schema: SchemaMap, rel_keys: list[str]) -> str:
    """One hop of traversal from a set of seed standards, across every
    relationship role in `rel_keys`, each respecting its own configured
    direction. Bound parameter: `$seeds` (list of canonical is_numbers).

    Returns rows of (seed, target, rel_key, title, scope_text, status,
    verified) — one row per (seed, edge) pair found.
    """
    standard_label = schema.label("standard")
    is_number_prop = schema.prop("is_number")
    title_prop = schema.prop("title")
    scope_prop = schema.prop("scope_text")
    status_prop = schema.prop("status")
    verified_prop = schema.prop("verified")

    branches = []
    for rel_key in rel_keys:
        spec = schema.rel(rel_key)
        pattern = _pattern(spec.direction, spec.name, "s", "t")
        branches.append(
            f"""WITH s
    MATCH {pattern}
    RETURN t, '{rel_key}' AS rel_key"""
        )
    union_body = "\n    UNION\n    ".join(branches)

    return f"""
UNWIND $seeds AS seed_is_number
MATCH (s:{standard_label} {{{is_number_prop}: seed_is_number}})
CALL {{
    {union_body}
}}
RETURN s.{is_number_prop} AS seed,
       t.{is_number_prop} AS target,
       rel_key,
       t.{title_prop} AS title,
       t.{scope_prop} AS scope_text,
       t.{status_prop} AS status,
       t.{verified_prop} AS verified
""".strip()


def build_supersession_query(schema: SchemaMap) -> str:
    """Direct (one-hop) supersession neighbours of a single standard.
    Bound parameter: `$is_number`.

    Returns one row: (is_number, superseded_by, supersedes) where
    `supersedes` is a list (possibly empty) of direct predecessors.
    """
    standard_label = schema.label("standard")
    is_number_prop = schema.prop("is_number")
    spec = schema.rel("superseded_by")

    successor_pattern = _pattern(spec.direction, spec.name, "s", "succ")
    predecessor_pattern = _pattern(_reverse(spec.direction), spec.name, "s", "pred")

    return f"""
MATCH (s:{standard_label} {{{is_number_prop}: $is_number}})
OPTIONAL MATCH {successor_pattern}
RETURN s.{is_number_prop} AS is_number,
       succ.{is_number_prop} AS superseded_by,
       [{predecessor_pattern} | pred.{is_number_prop}] AS supersedes
""".strip()


def build_curated_overlaps_query(schema: SchemaMap) -> str:
    """Curated OVERLAPS_SCOPE_WITH edges among a given set of standards.
    Bound parameter: `$is_numbers` (list of canonical is_numbers).

    Returns rows of (is_a, is_b, overlap_score), each unordered pair once.
    """
    standard_label = schema.label("standard")
    is_number_prop = schema.prop("is_number")
    overlap_score_prop = schema.prop("overlap_score")
    spec = schema.rel("overlaps_scope_with")
    pattern = _pattern(spec.direction, spec.name, "a", "b")

    return f"""
UNWIND $is_numbers AS a_number
MATCH (a:{standard_label} {{{is_number_prop}: a_number}})
MATCH {pattern}
WHERE b.{is_number_prop} IN $is_numbers AND a.{is_number_prop} < b.{is_number_prop}
RETURN a.{is_number_prop} AS is_a,
       b.{is_number_prop} AS is_b,
       coalesce(r.{overlap_score_prop}, 1.0) AS overlap_score
""".strip()


def build_category_via_edge_query(schema: SchemaMap) -> str:
    """The ProductCategory a standard BELONGS_TO. Bound parameter: `$is_number`."""
    standard_label = schema.label("standard")
    category_label = schema.label("product_category")
    is_number_prop = schema.prop("is_number")
    category_name_prop = schema.prop("category_name")
    spec = schema.rel("belongs_to")
    pattern = _pattern(spec.direction, spec.name, "s", f"c:{category_label}")

    return f"""
MATCH (s:{standard_label} {{{is_number_prop}: $is_number}})
OPTIONAL MATCH {pattern}
RETURN c.{category_name_prop} AS category
""".strip()


def build_sample_node_properties_query(schema: SchemaMap) -> str:
    """One sample Standard node's property keys — used by the schema
    contract test to check expected properties actually exist."""
    standard_label = schema.label("standard")
    return f"MATCH (n:{standard_label}) WITH n LIMIT 1 RETURN keys(n) AS property_keys"


# ---------------------------------------------------------------------------
# Writes (loader)
# ---------------------------------------------------------------------------


def build_merge_standard_query(schema: SchemaMap) -> str:
    """Idempotent upsert of one Standard node. Bound parameters: is_number,
    title, scope_text, status, edition, verified."""
    standard_label = schema.label("standard")
    is_number_prop = schema.prop("is_number")
    return f"""
MERGE (s:{standard_label} {{{is_number_prop}: $is_number}})
SET s.{schema.prop('title')} = $title,
    s.{schema.prop('scope_text')} = $scope_text,
    s.{schema.prop('status')} = $status,
    s.{schema.prop('edition')} = $edition,
    s.{schema.prop('verified')} = $verified
""".strip()


def build_merge_category_query(schema: SchemaMap) -> str:
    """Idempotent upsert of one ProductCategory node. Bound parameter: category_name."""
    category_label = schema.label("product_category")
    category_name_prop = schema.prop("category_name")
    return f"MERGE (c:{category_label} {{{category_name_prop}: $category_name}})"


def build_merge_belongs_to_query(schema: SchemaMap) -> str:
    """Idempotent upsert of one Standard-[:BELONGS_TO]->ProductCategory edge.
    Bound parameters: is_number, category_name. Like
    `build_merge_relationship_query`, this always writes the canonical
    absolute arrow (standard -> category) and does not consult
    `RelSpec.direction`, which is a read-side traversal concept only.
    """
    standard_label = schema.label("standard")
    category_label = schema.label("product_category")
    is_number_prop = schema.prop("is_number")
    category_name_prop = schema.prop("category_name")
    rel_name = schema.rel("belongs_to").name
    return f"""
MATCH (s:{standard_label} {{{is_number_prop}: $is_number}})
MATCH (c:{category_label} {{{category_name_prop}: $category_name}})
MERGE (s)-[:{rel_name}]->(c)
""".strip()


def build_merge_relationship_query(schema: SchemaMap, rel_key: str) -> str:
    """Idempotent upsert of one Standard-[:REL]->Standard edge, written
    exactly as `from`/`to` specify (see module docstring — the loader's
    from/to already match this relationship's absolute documented arrow).
    Bound parameters: from_is_number, to_is_number, verified, and
    overlap_score (only meaningful for overlaps_scope_with; ignored by the
    query otherwise since Cypher SET simply writes whatever is bound).
    """
    standard_label = schema.label("standard")
    is_number_prop = schema.prop("is_number")
    verified_prop = schema.prop("verified")
    spec = schema.rel(rel_key)

    extra_set = ""
    if rel_key == "overlaps_scope_with":
        extra_set = f", r.{schema.prop('overlap_score')} = $overlap_score"

    return f"""
MATCH (a:{standard_label} {{{is_number_prop}: $from_is_number}})
MATCH (b:{standard_label} {{{is_number_prop}: $to_is_number}})
MERGE (a)-[r:{spec.name}]->(b)
SET r.{verified_prop} = $verified{extra_set}
""".strip()
