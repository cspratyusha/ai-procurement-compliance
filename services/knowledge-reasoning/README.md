# Knowledge Reasoning — Part 3 & Part 5

Graph expansion + compliance validation (Part 3), and LLM reasoning +
generation (Part 5), for the AI recommendation engine that helps Indian
procurement officials identify the full cluster of Indian Standards (IS)
applicable to a product — not just the one standard they thought to search
for.

Full system context: `../../Solution_details/`. This service's own
proposal to the team, including every place it diverges from those
planning docs: `INTEGRATION.md`.

## Why this exists before the rest of the pipeline does

Three teammates own the pieces this service sits between (retrieval,
Postgres/Neo4j corpus, the orchestrator/API) and none of them exist yet.
Every design decision here is judged against one question: when the real
thing arrives, is swapping it in a configuration change, or a rewrite?
Four mechanisms make that true — see each module's own docstring for the
reasoning, not repeated here:

- **`graph/queries.py`** is the only file with Cypher; **`db/queries.py`**
  the only one with SQL. Both build every query from `config/schema_map.py`.
- **`config/schema_map.py`** — no node label, relationship type, table, or
  column name is ever a hardcoded string anywhere else. Relationship
  entries carry an explicit `direction`, not just a name (a swapped name
  with the same direction assumption silently inverts traversal — see the
  module docstring). Overridable via `config/schema_map.yaml` without
  touching code. Every identifier is validated at load time.
- **`ports/`** — `GraphRepository`, `StandardsRepository`, `RetrievalPort`
  are `Protocol`s. Business logic depends only on these. Two
  implementations of each exist today: `adapters/fixture/` (in-memory,
  backed by `fixtures/*.yaml`, no database required — what tests run
  against) and `adapters/live/` (real Neo4j/Postgres/HTTP). Selected by
  environment variable in `factory.py`.
- **`tests/test_schema_contract.py`** — the single most valuable file
  here. Tier A asserts business-logic correctness against the fixture
  (always runs). Tier B connects to whatever `KR_NEO4J_URI`/
  `KR_POSTGRES_DSN` point at and asserts the configured labels,
  relationship types, tables, and columns literally exist there — repoint
  it at Teammate 1's real database and run it to find every mismatch in
  seconds, instead of during integration week.

## Scope

This lists intended responsibility, not build status — for what's
actually working today versus not yet built, see `INTEGRATION.md`'s
"What works today" section at the top; don't infer either from this list.

**Mine:** graph traversal and cluster assembly, scope-overlap detection,
freshness/supersession, the certification mapper, the orphan gate, the
trust-score interface, LLM-grounded explanation/diff/impact/clause
generation, the hallucination guard, multilingual rendering.

**Not mine — do not extend this service to cover it:** corpus scraping,
embeddings/BM25/cross-encoder/LTR retrieval, the production HTTP API/auth/
RBAC/orchestrator, any frontend/extension/voice interface, scheduled jobs.
`fastapi` is a listed dependency for a planned thin local test harness to
exercise this service's own logic in isolation — it does not exist yet
(no app, no route); `knowledge_reasoning/app/` is an empty placeholder.
When built, it will be a test rig, not the product API.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # runs fully against fixtures, no database needed
```

To also exercise the live-backend tests and Tier B of the schema contract
test:

```bash
cp .env.example .env        # adjust if needed
docker compose -f docker-compose.dev.yml up -d
python -m knowledge_reasoning.loader.run
KR_TEST_NEO4J_URI=bolt://localhost:7688 \
KR_TEST_NEO4J_PASSWORD=devpassword \
KR_TEST_POSTGRES_DSN=postgresql://postgres:devpassword@localhost:5433/kr_dev \
pytest -m "live_neo4j or live_postgres"
```

`docker-compose.dev.yml` runs Neo4j and Postgres on non-default ports
(7688/7475, 5433) specifically so it can never collide with whatever
Teammate 1 eventually stands up as the team's shared infrastructure — see
"Integrating real data" below, this needs reconciling once that exists.

**A note on how this was built:** the environment used to write this had
no Docker daemon and no route to download a Neo4j distribution (network
policy). Everything Neo4j-related — `graph/queries.py`'s generated Cypher,
`Neo4jGraphRepository`, the loader's Neo4j path — is validated by
string-shape unit tests and by the fixture-backed adapter passing the
identical test suite Neo4j would run against, but was never executed
against a real Neo4j server. Postgres *was* verified end-to-end against a
real local instance, including a real idempotency bug the first version of
the certification-rules upsert had (missing `ON CONFLICT` target — fixed,
see `db/schema.sql`'s functional unique index). Run
`docker compose -f docker-compose.dev.yml up` and the Tier B Neo4j tests
before trusting that path in anger.

## Layout

```
contracts/            shared pydantic contracts (standalone package, see its docstring)
knowledge_reasoning/
  config/              schema_map (labels/rel-types/properties/tables/columns + direction),
                       settings (env-driven backend selection)
  ports/               Protocol interfaces + internal DTOs
  graph/queries.py     the only Cypher in this codebase
  db/queries.py        the only SQL in this codebase
  db/schema.sql        Phase 1 dev DDL (not Teammate 1's real migration)
  adapters/fixture/    in-memory port implementations, backed by fixtures/*.yaml
  adapters/live/       Neo4j / Postgres / HTTP port implementations
  loader/              idempotent fixture -> Neo4j+Postgres loader, with a
                       production/unverified-data guard
  factory.py           env-driven wiring: which port implementation backs what
fixtures/              placeholder domain data — see fixtures/README.md FIRST
tests/
  test_schema_contract.py   the contract test — see above
docker-compose.dev.yml My own dev stack, not the team's shared infra (see below)
INTEGRATION.md          what I need from each teammate, and where I diverge
                        from Solution_details/
```

## Integrating real data

See `INTEGRATION.md` for the full breakdown (what's needed from each
teammate, exactly which files change per delivery, and every place my
assumptions diverge from the planning docs). Short version: real corpus
data replaces `fixtures/*.yaml` in place, a differently-shaped Neo4j/
Postgres schema is a `config/schema_map.yaml` edit, and a real retrieval
endpoint is one adapter file
(`knowledge_reasoning/adapters/live/http_retrieval_port.py`) plus two
environment variables. None of it should ever require touching the graph
expansion, validation, or generation logic itself — if it does, that's a
sign the port abstraction leaked and worth fixing rather than working
around.

`docker-compose.dev.yml` is mine alone, for local development before
Teammate 1's shared Neo4j/Postgres infrastructure exists. It needs
reconciling (probably: deleting, in favour of pointing `KR_NEO4J_URI`/
`KR_POSTGRES_DSN` at the shared stack) once that infrastructure is real.
