-- Enable pgvector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Core tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS product_categories (
    category_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_category_id TEXT REFERENCES product_categories(category_id)
);

CREATE TABLE IF NOT EXISTS standards (
    id TEXT PRIMARY KEY,
    number TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    scope TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    version TEXT NOT NULL,
    last_amended TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'superseded', 'withdrawn')),
    keywords_json JSONB NOT NULL,
    superseded_by_id TEXT REFERENCES standards(id),
    product_category_id TEXT REFERENCES product_categories(category_id),
    sector TEXT,
    source_url TEXT,
    source_checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- pgvector embedding column (384-dim for all-MiniLM-L6-v2)
    embedding vector(384)
);

CREATE TABLE IF NOT EXISTS amendments (
    amendment_id TEXT PRIMARY KEY,
    standard_id TEXT NOT NULL REFERENCES standards(id),
    amendment_number INTEGER NOT NULL,
    date_issued TEXT,
    change_summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS standard_relationships (
    source_id TEXT NOT NULL REFERENCES standards(id),
    target_id TEXT NOT NULL REFERENCES standards(id),
    type TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, type)
);

CREATE TABLE IF NOT EXISTS certification_rules (
    category TEXT NOT NULL,
    scheme_type TEXT NOT NULL,
    mandatory BOOLEAN NOT NULL,
    PRIMARY KEY (category, scheme_type)
);

-- ---------------------------------------------------------------------------
-- Analytics / logging tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS interaction_logs (
    interaction_id BIGSERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,
    input_mode TEXT NOT NULL DEFAULT 'text',
    candidates JSONB NOT NULL DEFAULT '[]'::jsonb,
    dense_scores JSONB DEFAULT '[]'::jsonb,
    bm25_scores JSONB DEFAULT '[]'::jsonb,
    cross_encoder_scores JSONB DEFAULT '[]'::jsonb,
    user_action TEXT,
    corrected_to_standard_id TEXT REFERENCES standards(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_findings (
    finding_id BIGSERIAL PRIMARY KEY,
    cited_number TEXT NOT NULL,
    matched_standard_id TEXT REFERENCES standards(id),
    severity TEXT NOT NULL,
    finding TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_standards_category ON standards(category);
CREATE INDEX IF NOT EXISTS idx_standards_status ON standards(status);

-- Full-text search GIN index
CREATE INDEX IF NOT EXISTS idx_standards_search ON standards
    USING GIN (to_tsvector('simple', number || ' ' || title || ' ' || scope || ' ' || description));

-- Vector similarity HNSW index (cosine distance)
CREATE INDEX IF NOT EXISTS idx_standards_embedding ON standards
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_amendments_standard ON amendments(standard_id);
