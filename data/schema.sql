CREATE TABLE IF NOT EXISTS standards (
    id TEXT PRIMARY KEY,
    number TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    scope TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    version TEXT NOT NULL,
    last_amended TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
    keywords_json TEXT NOT NULL
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
    mandatory INTEGER NOT NULL CHECK (mandatory IN (0, 1)),
    PRIMARY KEY (category, scheme_type)
);

CREATE INDEX IF NOT EXISTS idx_standards_category ON standards(category);
CREATE INDEX IF NOT EXISTS idx_standards_status ON standards(status);
