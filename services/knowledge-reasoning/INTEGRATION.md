# Integration guide — Part 3 (Graph Expansion & Compliance Validation) & Part 5 (LLM Reasoning & Generation)

This is what I take to the team. It says three things: what I need from
each of you, exactly which files change when you deliver it, and where my
assumptions diverge from `Solution_details/` so you can correct me before
integration week instead of during it.

Everything below is implemented against **placeholder data** — every fixture
node, edge, amendment, and certification rule is real-shaped but invented,
and marked `verified: false` throughout (see `fixtures/README.md`). Nothing
here should be mistaken for curated BIS data.

**Update, post-integration:** you've now pushed real work and I've adapted
to it. §0 below is the running record of what actually happened —
everything else in this document is the original Phase 1 proposal, kept
for context and still mostly accurate about the contracts themselves.

## What works today (read this first)

Plan your own work against this, not against the "Contracts I'm
proposing" or "Scope" language further down — those describe the target
design, not current state.

**Working, and live-tested against real data:**
- The port/adapter/repository layer for both Parts: `GraphRepository`
  (fixture, Postgres, Neo4j) and `StandardsRepository` (fixture, Postgres).
  Postgres is the default backend and reads real data correctly —
  supersession, category, amendments, certification rules, graph
  expansion with a fallback bucket for unmapped relationship types.
- `config/schema_map.py` — absorbed the real naming and direction drift
  found during integration with zero code changes elsewhere.
- The idempotent loader, the schema-contract test (Tier A + Tier B), and
  a one-command curated-relationships importer.

**Working, real, but standalone — not wired into anything downstream,
because nothing downstream exists yet:**
- The orphan-query gate (`validation/orphan_gate.py`).
- The untraceable-certification guard (`generation/certification_guard.py`,
  `certification_notes.py`) — narrow, scoped to one hallucination surface.

**Not built — the entire business-logic layer of both Parts:** cluster
assembly, cluster ranking, scope-overlap detection (the computed half and
the union/assembly), multi-hop supersession resolution, the certification
mapper, trust score; and all of Part 5's generation layer — explanation
generator, version-diff summariser, impact estimator, clause generator,
the general hallucination guard, multilingual rendering. Full list with
evidence for each: "What's not built yet" under §0 below.

## 0. Integration status (adapting to what you actually built)

Full findings from inspecting and measuring your real pushed work are in
the Stage A–D report I gave the team separately (directory inventory,
real schema, real data measurements, and a three-part divergence list).
This section tracks what changed on my side as a result, in the order it
happened.

**Which schema is authoritative:** `data/schema.sql` + `data/raw/*.json` +
`scripts/ingest.py` — the only Part 1 pipeline that's demonstrably been
run (its derived FAISS/BM25 artifacts exist; `app/`'s SQLAlchemy+Neo4j
pipeline shows no evidence of ever executing — its default seed file
doesn't exist anywhere in the repo). I did not touch either implementation;
this is a decision for the team, not something I resolved unilaterally.

**There is no real Neo4j data anywhere**, and no evidence anything has
ever written to it. `Neo4jGraphRepository` stays exactly as built and
selectable via `KR_GRAPH_BACKEND=neo4j` for whenever that changes — but the
default `GraphRepository` is now `PostgresGraphRepository`, reading the
real relationship data from `standard_relationships` via a recursive CTE.
**This is the clearest evidence yet that the ports design was worth
building**: swapping the graph backend from an assumption (Neo4j) to
reality (Postgres) was a new adapter class plus one default-value change
in `settings.py` — nothing in `contracts/`, nothing in any future Phase
2/3 business logic (none of which exists yet) had to change, or will have
to change again if Neo4j gets populated for real later. That was the
entire point of `GraphRepository` being a `Protocol` instead of a concrete
class from day one.

Confirmed against real data, not just re-read schema:

- `installation_guide_for`'s direction was inverted from what Phase 1
  guessed — fixed, and confirmed against `IS 694:2010`, the exact standard
  your own frontend mock picked as its worked example. It now correctly
  finds `IS 732:2019`.
- `SUPERSEDED_BY` and `NORMATIVE_REFERENCE` directions were already
  correct.
- `standards.category` (flat string, 18/18 populated) is the real,
  working category source — `product_category_id` exists in your schema
  but is never populated; I kept it as a secondary/aspirational path only.
- `certification_rules` has no FK columns at all (`category`, `scheme_type`,
  `mandatory` only) — my query is now a flat equality match, no join.
- Real amendments are separate `Standard` rows linked by `AMENDED_BY`, not
  `amendments` table rows (that table exists but nothing writes to it) —
  `get_version_status` now reads both and unions them, so a populated
  `amendments` table would be picked up automatically with no code change.
- `standards.id` (PK) and `amendments.standard_id` (FK) are genuinely
  different real column names for the same concept — `SchemaMap.column_names`
  is now table-scoped (`column(table, logical_name)`) instead of a flat
  namespace, which is what actually exposed and fixed this.

Two smaller things this surfaced, fixed as found:

- The `certification_rules.scheme_type` values are free text ("BIS Product
  Certification"), not the closed ISI/CRS/HALLMARKING vocabulary I'd
  assumed — `CertificationRuleRow.scheme` is now `str`, and narrowing it
  into the closed set is explicitly the not-yet-built Phase 3 mapper's job,
  not something to pretend is already true at the repository layer.
- Postgres enforces real FK constraints on `standard_relationships`, unlike
  Neo4j's `MERGE` (which just matches nothing for a missing endpoint) — a
  dangling-reference fixture edge that loaded fine into Neo4j raised a
  `ForeignKeyViolation` here. The loader now checks both endpoints exist
  before writing an edge and records a drop, same policy as the Neo4j path,
  just enforced differently because the two databases are differently
  strict.

### Unmapped relationship types: never dropped, never crash the loader

The corpus will always contain relationship-type strings I haven't
anticipated — Stage C's real-data measurement already found the graph is
sparse and that most relationship types are thin. Decision 3 was: an
unmapped type is a fallback (`EdgeType.RELATED_UNCLASSIFIED`), never
silently dropped and never something that blocks a response.

- `GraphRepository.expand()` (all three backends) now returns
  `ExpansionResult { paths, unmapped_edge_types: dict[str, int] }` instead
  of a bare list. Any relationship-type string with no `schema_map` entry
  is still traversed, surfaces with `role = RELATED_UNCLASSIFIED`, and is
  counted in `unmapped_edge_types` — visible in `ValidatedCluster.graph_stats`,
  not silently absorbed.
- New explicit mappings for the four real types I hadn't accounted for:
  `DESIGN_CODE_FOR` (sibling of `INSTALLATION_GUIDE_FOR`), `COMPLEMENTARY_PART`,
  `RELATED_PPE`, `RELATED_PIPING`.
- `python -m knowledge_reasoning.loader.report_relationship_types
  [--backend postgres]` prints every distinct relationship type currently in
  the data (fixture or live) and whether it's mapped — run it any time new
  data lands, before an unmapped type shows up as a surprise in a response.
- **A real bug this surfaced, found and fixed:** the loader itself
  (`load_into_postgres`) originally still hard-failed on an unmapped type —
  it called `schema.rel(edge.type).name` unconditionally, which raises
  `KeyError` for anything not in `schema_map`. Decision 3 only reached the
  *read* side (`expand()`) at first; I hadn't updated the *write* side to
  match. Since the crash happened mid-transaction, before the loader's
  `conn.commit()` and before the owning test fixture's `yield`, the
  Postgres connection was orphaned holding an uncommitted lock — which then
  hung every subsequent test module's own connection indefinitely the
  moment it touched an overlapping row. Fixed: the loader now writes an
  unmapped type through as-is (with a loud `logger.warning`), matching what
  `expand()` already expects to read back. `load_into_neo4j` gets the
  analogous treatment, but skips-and-logs instead of writing through,
  because `graph/queries.py`'s whole invariant is "only validated schema
  names get interpolated into Cypher, never raw data" — writing an
  unvalidated type name into a Neo4j relationship type would be the same
  class of risk that invariant exists to prevent. (Not currently exercised
  by real data either way — see "no real Neo4j data anywhere" above.)

### The orphan gate: margin-based, not an absolute score cutoff

First real piece of Phase 3 business logic
(`knowledge_reasoning/validation/orphan_gate.py`). The original Phase 1
plan assumed `RetrievalCandidate.score` was a calibrated, cross-query
comparable confidence and would have used a fixed floor. Stage C found
real evidence against that: Teammate 2's own code documents `final_score`
as "a relative ranking signal... not comparable across separate /retrieve
calls" (it's rescaled per-response), their own logged interactions show a
*correct* top-1 match scoring as low as 0.4693, and a nonsense query
("quantum flux capacitor mounting bracket for interdimensional
teleportation") scored in the same range as legitimate low-rank candidates
for real queries. An absolute cutoff on a score with those properties
isn't a safety net.

What the gate does instead, in priority order: (1) primary — the margin
between the top two candidates' scores, which stays meaningful *within
one response* even though the absolute numbers don't compare *across*
responses; (2) secondary — flags a flat/low-variance score distribution
even when the margin alone would pass; (3) tertiary — a single candidate
with no independent graph corroboration (no other retrieved candidate
reachable from it) is treated as orphan regardless of its score, since one
number with nothing else backing it is exactly the failure mode above; (4)
an absolute floor exists as a config knob (`absolute_floor`) but is
**disabled by default** — it's there for if/when real score calibration
data exists, not turned on against evidence that says it would be
meaningless today.

**Calibration honesty, stated in the code and repeated here:** these
thresholds (`min_margin=0.10`, `min_score_stdev=0.05`,
`require_graph_corroboration_below_margin=0.20`) come from the only real
numbers available at integration time — two logged interactions, a
four-query BM25 smoke test, an 18-standard corpus. That's evidence, not a
guess, but it's thin. Don't read `min_margin=0.10` as a validated figure;
revisit once real usage data exists. **I did not invent a hub-node
penalty, an overlap-detection cutoff, or a result-count cap to
"recalibrate" — say this plainly: those are not tuning gaps, they are
missing features.** There is no cluster-ranking code to apply a hub
penalty to, no overlap-scoring code for a cutoff to filter, and no
cluster-assembly code to cap a result count from. None of the three
exists as code, in any form, tuned or not. See "What's not built yet"
below for the full list.

### Certification traceability and the untraceable-certification guard

This is, in my judgement, **the highest-risk hallucination surface in the
whole system**: an LLM asked about "ISI certification for structural
steel" will happily produce specific-sounding evidence requirements
(licence numbers, test report formats) from training data, because that
text reads as competent domain knowledge, not as a hallucination — and it
can go straight into a tender's evaluation criteria. Unlike a fabricated
IS number, a plausible-but-fabricated evidence requirement isn't
mechanically checkable against grounding context.

- `CertificationRequirement.traceable: bool` (new) is derived, not
  settable — `True` only when `notification_reference` is populated, i.e.
  only when `required_evidence`/`effective_date`/`source_url` trace back to
  a specific, citable BIS notification.
- `knowledge_reasoning/generation/certification_guard.py` is a real,
  regex-based guard: `assert_no_fabricated_evidence(text, requirement)`
  raises if evidence-specific language ("required evidence", "must
  submit", licence-number phrasing, etc.) appears in generated text for an
  untraceable requirement. When untraceable, the (deterministic,
  template-based) generator may still state the scheme and whether it's
  mandatory — both are taken as given from the `CertificationRequirement`
  passed in, not invented by the generator itself. (No caller populates
  that field from real category data yet — the certification mapper that
  would is the not-built item above; today only tests construct one
  directly.) The generator must say evidence isn't recorded and needs
  verification, nothing more specific.
  A test (`test_generator_never_emits_evidence_language_when_untraceable`)
  asserts the generator's own output never trips its own guard.
- **Scope note:** this is *not* the full Phase 4 LLM generator from the
  original brief (prompt templates, the general grounding/hallucination
  guard over cited IS numbers, multilingual rendering) — none of that was
  built in this engagement. This is specifically the guard decision 6
  asked for, built narrow and real so whatever the eventual generator
  becomes can call it without a redesign.
- **`verified`/`VersionStatus.verification_reason` — derived, with a real
  caveat for you, not a decorative one.** Neither of your schemas has an
  actual `verified` column, but `data/schema.sql`'s `source_url` /
  `source_checked_at` are the closest real signal. Rule: checked and
  recent (`_RECENT_CHECK_WINDOW_DAYS`) -> verified; checked but stale ->
  not verified, `"stale_check"`; `source_url` present with no check
  timestamp -> not verified, `"unchecked_source"`; neither -> not
  verified, `"no_provenance"`. **The catch:** your real
  `source_checked_at` column is `NOT NULL DEFAULT NOW()` and your
  ingestion never writes `source_url` at all — so today this column means
  "when this row was last written to the database", not "when someone
  last confirmed the standard is still current against BIS". Every real
  row currently derives as `verified=True` right after any ingestion run,
  regardless of whether anyone re-checked anything. I'm deriving this
  correctly from the best signal that exists; the signal itself doesn't
  yet mean what the derivation needs it to mean. If provenance tracking
  matters for the final product (and I think it should, given §11 of the
  original brief), this needs an actual "last verified against source"
  write in your ingestion path, distinct from "last written to the row".

### Realistic fixture data, and a curation importer for the corpus gap

Stage C measured the real corpus as sparse (most standards have zero
outgoing structural edges, several small disconnected components, one
fully isolated node) and containing relationship types beyond the
documented vocabulary. The original two fixture domains
(`street_lighting/`, `reinforcement_steel/`) were deliberately *dense*,
built to exercise a hub node and a cycle as edge cases — useful, but not
representative of what business logic will actually see against real
data. Added `fixtures/sparse_real_topology/`: 14 nodes, ~0.57 edges/node,
a fully isolated node, one deliberately unmapped relationship type
(`material_grade_variant`), mirroring the real corpus's shape rather than
its content (placeholder `IS 5xxx` numbers, never real standards). The
original two domains stay exactly as they were — the hub/cycle edge cases
remain load-bearing tests, this is additive, not a replacement.

Fixing the corpus's sparseness for real — getting more actual
cross-references curated — is a data problem, not a code problem, and
outside this engagement's scope; that's being handled with the team
directly. What *is* in scope: `python -m
knowledge_reasoning.loader.import_curated_relationships
path/to/relationships.json` — a one-command importer for a hand-curated
addendum file in the **exact shape of your real `data/raw/relationships.json`**
(`[{"source_id": ..., "target_id": ..., "type": ...}, ...]`, ids being your
real `standards.id` values, type already the upper-case Cypher/SQL name).
It validates the file shape, skips (and reports, doesn't crash on) any row
whose endpoint isn't an existing `standards.id`, writes an unmapped type
through rather than dropping it (same fallback-bucket policy as
everywhere else), and is idempotent (`ON CONFLICT DO NOTHING`) so
re-running against a growing file is always safe. It does not generate or
validate the cross-references themselves — only loads rows a human already
believes are correct.

### What's not built yet, stated plainly rather than papered over

This is the complete list — not an illustrative sample. If something
isn't named here or in "What works today" at the top, assume it doesn't
exist. For each item: not built means no module implements it, and I
checked by grep, not by memory — nothing outside its own class
definition ever constructs the contract type named.

**Part 3:**
- **Cluster assembly.** No code builds a `ValidatedCluster`. Zero call
  sites outside `contracts/cluster.py` itself.
- **Cluster ranking (centrality + edge weighting).** No ranking module,
  no centrality computation anywhere. `ClusterMember.relevance` is a bare
  field nothing populates.
- **Scope-overlap detection.** The curated-edge *read* exists and is
  tested (`get_curated_overlaps`); the computed-from-scope-text half and
  the union/assembly into `OverlapWarning` do not exist. See §3 item 3.
- **Freshness/supersession resolution.** The one-hop *read* exists and is
  tested (`get_version_status`, `get_supersession`); the multi-hop
  chain-walk to the ultimate current edition — the actual "resolution" —
  does not exist. See §3 item 5.
- **Certification mapper.** No code maps a real free-text scheme string
  into the closed `ISI/CRS/HALLMARKING/NONE/UNKNOWN` vocabulary.
- **Trust score.** `ClusterMember.trust_score` is `None` and nothing
  outside its own field default ever sets it.

**Part 5** (all of Phase 4 from the original brief — none of it built):
- **Explanation generator.** `StandardExplanation` never constructed
  outside `contracts/generation.py`.
- **Version-diff summariser.** `VersionNote` never constructed outside
  the contract file; no diff logic anywhere.
- **Impact estimator.** `risk_if_omitted` is a bare field, never
  populated.
- **Clause generator.** `GeneratedResponse.clause_text` never set
  anywhere.
- **General hallucination guard.** The narrow certification-evidence
  guard below is real; the general guard (checking
  `cited_is_numbers ⊆ context_is_numbers`, triggering regeneration) is
  not built. `GeneratedResponse`/`GroundingReport` are never constructed
  outside `contracts/generation.py` and its own unit test.
- **Multilingual rendering.** `GeneratedResponse.language` is an unused
  field; no rendering or translation code exists.

**What does exist beyond the repository/adapter layer:** the orphan gate
(`validation/orphan_gate.py`) and the certification guard/notes pair
(`generation/certification_guard.py`, `certification_notes.py`) — both
real, tested, standalone. Neither is called by anything else in this
codebase, because nothing that would call them (cluster assembly, a
generation pipeline) exists yet. There's no evidence yet (real usage
data, a real UI consuming `ValidatedCluster`) to calibrate hub-penalty/
overlap-cutoff/result-cap *against* even if the features existed — but
the primary point stands on its own regardless of evidence: the features
themselves are not there.

## 1. What I need from each of you

### From Teammate 1 (corpus, Postgres, Neo4j — Stages 1–2)

1. **Real data**, in the shape documented in `fixtures/README.md` — a
   `nodes.yaml` / `edges.yaml` per domain is the easiest handoff, since my
   loader (`loader/fixture_loader.py`) already reads exactly that shape and
   writes it idempotently into both stores. If your export format differs,
   tell me and I adapt `fixture_data.py`'s parser — one file, not the
   loader or the repositories.
2. Confirmation of your actual Neo4j relationship-type **names and
   directions** — or just push real data and I run
   `tests/test_schema_contract.py` Tier B against it, which tells me
   exactly what doesn't match in seconds.
3. **Updated, post-integration:** I no longer need a `verified` column
   added — I derive it from `standards.source_url`/`source_checked_at`,
   which already exist. What I do need: `source_checked_at` currently
   means "row last written" (`NOT NULL DEFAULT NOW()`), not "last
   confirmed against BIS", and `source_url` is never written at all — so
   the derivation is correct but the underlying signal isn't meaningful
   yet. See "Certification traceability..." in §0 for the full caveat. If
   provenance matters for the final product, this needs a real "last
   verified" write in your ingestion path, separate from "last written".
4. `required_evidence`, `notification_reference`, `effective_date`,
   `source_url` columns on `certification_rules` — also not in the
   documented schema, needed for `CertificationRequirement` to be
   traceable rather than just a scheme name.
5. Answers to the six open questions in §3.

### From Teammate 2 (retrieval — Stage 3)

1. Either adopt `contracts/retrieval.py`'s `RetrievalResult`/
   `RetrievalCandidate` as-is, or tell me what you'd rather send — it's a
   proposal (§4 below), not a demand.
2. A real `POST {base_url}/retrieve` endpoint matching that shape. Until
   then I run against `fixtures/mock_queries.yaml`'s canned results.
   Whichever shape you land on, only `adapters/live/http_retrieval_port.py`
   needs to change on my side.

### From Teammate 4 (orchestrator/API — Stage 7)

1. Confirmation that `contracts/cluster.py`'s `ValidatedCluster` and
   `contracts/generation.py`'s `GeneratedResponse` are what you'd want to
   receive from Part 3 and Part 5 respectively — **as designed, not as
   built.** Nothing in this codebase constructs either type today (see
   "What works today" at the top and §0's "not built yet" list); this is
   asking you to react to the proposed shape before logic gets written
   against it, not confirming a working handoff.
2. Whether you want to call Part 3/5 in-process (import the package
   directly) or over HTTP once they exist. `fastapi` is a listed
   dependency in `pyproject.toml` but there is no app, route, or harness
   built yet — `knowledge_reasoning/app/` is an empty placeholder package.
   Tell me which you'd want and I'll build accordingly, but there's
   nothing to "add a route to" today.

## 2. Which files change when a delivery arrives

| Delivery | Files that change |
|---|---|
| Teammate 1: real data, same YAML shape | `fixtures/*/*.yaml` only — loader, repositories, contracts untouched |
| Teammate 1: real data, different export shape | `knowledge_reasoning/adapters/fixture/fixture_data.py` (the parser) |
| Teammate 1: different label/relationship/property/table/column names | `knowledge_reasoning/config/schema_map.yaml` (no code change) |
| Teammate 1: structurally different schema (missing `verified` column, etc.) | `knowledge_reasoning/db/schema.sql` (Phase 1 dev DDL only — your real migration is your own) |
| Teammate 2: real retrieval endpoint, matching contract | `.env` — set `KR_RETRIEVAL_BACKEND=live`, `KR_RETRIEVAL_BASE_URL` |
| Teammate 2: different response shape | `knowledge_reasoning/adapters/live/http_retrieval_port.py` only |
| Teammate 4: contract feedback | `contracts/*.py` (shared, versioned — flag changes to me directly, these are the seams everyone depends on) |

The `tests/test_schema_contract.py` Tier B suite is the fastest way to find
out which of the above you actually need: point `KR_NEO4J_URI`/
`KR_POSTGRES_DSN` at your database and run it.

## 3. Where I diverge from `Solution_details/` — please confirm or correct

1. **Relationship-type vocabulary.** I adopted your Neo4j names exactly
   (`SAFETY_REQUIREMENT_FOR`, `INSTALLATION_GUIDE_FOR`, `SUPERSEDED_BY`,
   ...) from `07_Data_Flow_And_Databases.md` rather than my own earlier
   draft. `RELATED_PRODUCT` and `AMENDED_BY` are **not** in your documented
   model — I kept them from my original brief because Part 3's contract
   needs *some* way to represent "these two standards address the same
   product family" and "this standard has an amendment," but I don't know
   if you intend to model either as a graph relationship. If amendments
   only ever live in your `amendments` Postgres table (which is what I've
   assumed and built against), `AMENDED_BY` may be dead weight in the
   `EdgeType` enum — tell me and I'll drop it rather than leave an unused
   role sitting in the contract.
2. **Relationship direction.** Your docs give one Cypher pattern per
   relationship type but don't say in prose which side is the "seed" in a
   typical expansion. I inferred direction from your own comments (e.g.
   `TEST_METHOD_FOR`: test-method standard -> product standard, so
   expanding *from* a product standard reads that edge backwards). My
   guesses are in `knowledge_reasoning/config/schema_map.py`'s
   `DEFAULT_RELATIONSHIP_TYPES`, each with the reasoning in a comment.
   Wrong guesses here don't silently corrupt anything — `RelSpec` makes
   direction explicit and `tests/test_schema_contract.py` will catch a
   mismatch the moment it runs against your real graph — but I'd rather
   you sanity-check them now than find out during integration.
3. **Scope overlap — status correction, this was overstated before.** Your
   model has `OVERLAPS_SCOPE_WITH` as a graph edge, which I'm reading as
   *curated by you*. My brief's Part 3 spec also asks for *computed*
   overlap detection from scope text. What actually exists today:
   `GraphRepository.get_curated_overlaps` — a real, tested read of your
   curated edges (verified against the 2 real `OVERLAPS_SCOPE_WITH` edges
   in the corpus). What does **not** exist: the computed-from-scope-text
   detection itself, and the logic that would union curated + computed
   results into `OverlapWarning` objects tagged
   `source: "curated" | "computed"` — that union/assembly is designed into
   the contract (`contracts/cluster.py`) but nothing builds one; grep
   confirms `OverlapWarning(...)` is never constructed outside its own
   class definition and one contract unit test. If you're not planning to
   curate `OVERLAPS_SCOPE_WITH` beyond those 2 edges, the computed half is
   what carries this feature — worth knowing now, before assuming either
   half is done.
4. **Product category.** Your docs model category as *both* a Postgres FK
   (`standards.product_category_id`) *and* a Neo4j `BELONGS_TO` edge. I
   treat the Postgres property as primary (matching your "Postgres is
   source of truth, Neo4j is derived" rule) with the graph edge as
   fallback, configurable via `schema_map.category_strategy`. Confirm this
   matches how your fan-out-from-Postgres ingestion actually keeps the two
   in sync — if the edge is sometimes populated without the FK (or vice
   versa) in practice, I want to know which case is real.
5. **Supersession is one-hop only, so far.** `superseded_by_id` in your
   schema is a single FK. My Phase 1 primitives
   (`StandardsRepository.get_version_status`, `GraphRepository.get_supersession`)
   read exactly that one hop — they do not walk A -> B -> C to find the
   *ultimate* current edition; that chain-walk is Phase 3. Does your
   ingestion ever leave multi-hop supersession chains for me to walk, or
   do you normalise `superseded_by_id` to always point at the current
   edition directly? Changes how much logic Phase 3 actually needs.
6. **Dangling references.** My fixture deliberately includes a reference
   to a standard not in the corpus (see `fixtures/README.md`). My loader's
   current behaviour: the referencing node still loads, the edge to the
   missing target is silently dropped (Neo4j `MATCH` on a target that
   doesn't exist just matches nothing), and it's reported in the loader's
   `LoadReport.edges_dropped_dangling` rather than raised as an error.
   Open question for you: should a standard referenced-but-not-yet-in-the-
   corpus get a placeholder/stub node (visibly "known to exist, not yet
   catalogued") instead of silently vanishing from the graph? I lean
   toward yes, for the same "make gaps visible" reason as `verified:
   false`, but haven't built it since it's your ingestion pipeline that
   would need to decide when a placeholder gets reconciled.

## 4. Contracts I'm proposing (paste-ready summary)

Full definitions live in `contracts/` (a standalone top-level package —
see its docstring for why, if we later want a shared `packages/contracts/`).
Every IS number crossing any of these is canonicalised via
`contracts.is_number.parse_is_number` before validation — send me any
format ("IS 10322-5-3", "IS 10322 Part 5 Section 3", "IS:10322(Pt5/Sec3)")
and it normalises the same way.

**Part 2 -> Part 3** (`contracts/retrieval.py`):
`RetrievalResult { query_id, normalised_query, original_query,
original_language, product_category?, candidates: RetrievalCandidate[] }`,
each candidate `{ is_number, title, score ∈ [0,1], match_reason: "dense" |
"sparse" | "hybrid" | "reranked", snippet? }`.

**Part 3 output** (`contracts/cluster.py`):
`ValidatedCluster { query_id, primary: ClusterMember[], allied:
ClusterMember[], overlaps: OverlapWarning[], orphan, orphan_reason?,
confidence, graph_stats }`. Every `ClusterMember` carries `role`
(`EdgeType`), `path` (seed -> ... -> member), `hop_distance`, `version`
(`VersionStatus`), and `certification` (`CertificationRequirement`,
**intended** — see caveat below — to never be silently `NONE` when
unmapped, always `UNKNOWN` instead). Part 3 emits structure only, never
prose. **Status:** this is the target shape, not a working handoff —
nothing in this codebase constructs a `ValidatedCluster` today (see "What
works today"); the `_unknown_is_never_silently_none` validator on
`CertificationRequirement.scheme` currently documents that invariant for
the not-yet-built mapper but doesn't enforce anything itself (it's a
no-op today — nothing sets `scheme` outside tests, so there's nothing yet
to enforce it against).

**Part 3/5 -> Part 4** (`contracts/generation.py`):
`GeneratedResponse { query_id, summary, explanations:
StandardExplanation[], version_notes, overlap_notes,
certification_notes, clause_text?, language, grounding_report }`. Once the
hallucination guard (Phase 4, not built) exists, every IS number in
`grounding_report.cited_is_numbers` is meant to be a subset of
`grounding_report.context_is_numbers`, with `grounding_report.passed =
false` meaning the output was suppressed rather than returned ungrounded.
**Status:** design intent only — nothing constructs a `GeneratedResponse`
today; see "What works today" and the certification guard's narrower,
already-real scope below.

## 5. What's already true, so you know where to point things

- **Updated, post-integration:** `KR_GRAPH_BACKEND` and
  `KR_STANDARDS_BACKEND` now default to `postgres`, not `fixture` — your
  real data is the default the moment `KR_POSTGRES_DSN` is set, no
  `.env` flag needed. `fixture` stays fully supported and test-covered
  (pass `KR_GRAPH_BACKEND=fixture`/`KR_STANDARDS_BACKEND=fixture`
  explicitly) — both modes are kept green through every change from here
  on, not just at delivery time. `KR_GRAPH_BACKEND=neo4j` stays selectable
  too, for whenever real Neo4j data exists. `KR_RETRIEVAL_BACKEND` still
  defaults to `fixture` — no live retrieval endpoint exists yet (§1).
- The loader (`python -m knowledge_reasoning.loader.run`) is idempotent —
  safe to re-run against changing data — and refuses to write
  `verified: false` records into `KR_ENV=production` without an explicit
  override flag.
