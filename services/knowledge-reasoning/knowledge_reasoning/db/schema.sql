-- Phase-2-of-integration dev DDL, matching config/schema_map.py's
-- DEFAULT_TABLE_NAMES / DEFAULT_COLUMN_NAMES, which now mirror Teammate 1's
-- real, operative schema (data/schema.sql) rather than a guess from
-- Solution_details/07_Data_Flow_And_Databases.md. This is still NOT
-- Teammate 1's actual file — it exists so the loader and the live adapters
-- have something real to run against in dev/fixture-mode. If you override
-- table/column names via schema_map.yaml, this file needs the matching
-- override too; it isn't generated from schema_map.py.
--
-- Differences from Teammate 1's real data/schema.sql, deliberately: no
-- pgvector column (unavailable in this sandbox, and not this service's
-- concern — that's Part 2's embedding index), no `description`/`sector`
-- population (unused by any query here). `product_categories` exists for
-- structural fidelity but is intentionally never written to by this
-- service's loader either — confirmed (integration Stage A/B) that
-- Teammate 1's real ingestion doesn't populate it either; `standards.category`
-- is the real, working category source.
--
-- No `verified` column anywhere — confirmed real absence. `source_url` /
-- `source_checked_at` exist and are what `VersionStatus.data_verified` /
-- `verification_reason` are derived from (db/queries.py), not selected as
-- a plain boolean.

CREATE TABLE IF NOT EXISTS standards (
    id TEXT PRIMARY KEY,
    number TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    scope TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    version TEXT,
    last_amended TEXT,
    category TEXT,
    superseded_by_id TEXT REFERENCES standards (id),
    product_category_id TEXT,
    sector TEXT,
    source_url TEXT,
    source_checked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS product_categories (
    category_id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS amendments (
    amendment_id TEXT PRIMARY KEY,
    standard_id TEXT NOT NULL REFERENCES standards (id),
    amendment_number TEXT NOT NULL,
    date_issued DATE NOT NULL,
    change_summary TEXT,
    UNIQUE (standard_id, amendment_number)
);

CREATE TABLE IF NOT EXISTS certification_rules (
    category TEXT NOT NULL,
    scheme_type TEXT NOT NULL,
    mandatory BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (category, scheme_type)
);

-- Confirmed real (data/schema.sql): the graph relationship data itself
-- lives here. Read by PostgresGraphRepository via a recursive CTE.
CREATE TABLE IF NOT EXISTS standard_relationships (
    source_id TEXT NOT NULL REFERENCES standards (id),
    target_id TEXT NOT NULL REFERENCES standards (id),
    type TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, type)
);
