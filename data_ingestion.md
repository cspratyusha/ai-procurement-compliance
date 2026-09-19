# Data ingestion foundation

This repository now contains a small, repeatable data foundation for the
standards recommendation pipeline described in `Solution_details`.

## Folder structure

```text
data/
  raw/
    standards.json
    relationships.json
    certification_rules.json
    README.md
  schema.sql
  derived/
    standards.db
    graph.json
    keyword-index.json
scripts/
  ingest.py
```

## Source data

`data/raw/standards.json` is the source corpus. Each record contains the
standard identifier, IS number, title, formal scope, use-case description,
category, version, amendment date, status and search keywords.

The current demo corpus contains ten catalogue-metadata records across
structural steel, pipes, electrical work and PPE. It intentionally contains
metadata and short descriptions only; it does not reproduce copyrighted
standard text.

`data/raw/relationships.json` contains the manually curated relationships used
for allied-standard expansion. `data/raw/certification_rules.json` contains
category-level BIS certification mappings.

## Ingestion flow

Run this from any working directory inside the repository:

```powershell
python scripts\ingest.py
```

The script:

1. Validates required fields, unique IDs and standard numbers.
2. Validates ISO amendment dates and allowed status values.
3. Checks that relationships point to known standards.
4. Validates certification rule shapes.
5. Rebuilds `data/derived/standards.db` from `data/schema.sql`.
6. Writes a keyword-search projection to `data/derived/keyword-index.json`.
7. Writes a graph relationship projection to `data/derived/graph.json`.

PostgreSQL is the source of truth. Start it with `docker compose up -d
postgres`, install `requirements.txt`, then run the ingestion command. The
JSON files under `data/derived` remain rebuildable projections for local graph
and keyword consumers. Neo4j, Qdrant and Redis are provisioned by Compose for
the graph, vector and background-job stages; their adapters must be populated
from PostgreSQL rather than treated as independent sources.

## Verification

The current ingestion run produces:

```text
10 standards
6 relationships
6 certification rules
```

Running the command again clears and rebuilds the derived tables, so the
operation is repeatable rather than append-only.
