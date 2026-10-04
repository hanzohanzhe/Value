PRAGMA foreign_keys = ON;

CREATE TABLE datasets (
    dataset_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    version TEXT NOT NULL,
    kind TEXT NOT NULL,
    model_status TEXT NOT NULL,
    frozen_on TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE sources (
    source_id TEXT PRIMARY KEY,
    organisation TEXT NOT NULL,
    title TEXT NOT NULL,
    publication_year INTEGER NOT NULL,
    source_type TEXT NOT NULL,
    url TEXT NOT NULL,
    doi TEXT,
    accessed_on TEXT NOT NULL,
    locator TEXT NOT NULL,
    authority_class TEXT NOT NULL,
    notes TEXT NOT NULL
);

CREATE TABLE factors (
    record_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    technology TEXT NOT NULL,
    variant TEXT NOT NULL,
    component TEXT NOT NULL,
    factor_kind TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    basis TEXT NOT NULL,
    lifecycle_scope TEXT NOT NULL,
    geography TEXT NOT NULL,
    scenario TEXT NOT NULL,
    commissioning_year INTEGER,
    load_factor REAL,
    lifetime_years REAL,
    duration_hours REAL,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    source_locator TEXT NOT NULL,
    status TEXT NOT NULL,
    used_by_snapshot INTEGER NOT NULL CHECK (used_by_snapshot IN (0, 1)),
    derivation TEXT,
    quality_note TEXT NOT NULL,
    CHECK (load_factor IS NULL OR (load_factor >= 0 AND load_factor <= 1)),
    CHECK (lifetime_years IS NULL OR lifetime_years > 0),
    CHECK (duration_hours IS NULL OR duration_hours > 0)
);

CREATE TABLE methodology_rules (
    rule_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    formula_or_rule TEXT NOT NULL,
    applies_to TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    status TEXT NOT NULL,
    notes TEXT NOT NULL
);

CREATE TABLE snapshot_artifacts (
    artifact_id TEXT PRIMARY KEY,
    portable_name TEXT NOT NULL,
    sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
    size_bytes INTEGER NOT NULL,
    modified_at TEXT NOT NULL,
    copied_into_repository INTEGER NOT NULL CHECK (copied_into_repository IN (0, 1)),
    repository_copy TEXT,
    note TEXT NOT NULL
);

CREATE INDEX idx_factors_lookup
ON factors(dataset_id, technology, factor_kind, scenario);

CREATE INDEX idx_factors_component
ON factors(component, technology);

CREATE VIEW factor_records AS
SELECT
    f.*,
    d.title AS dataset_title,
    d.kind AS dataset_kind,
    d.model_status,
    s.organisation AS source_organisation,
    s.title AS source_title,
    s.url AS source_url,
    s.authority_class
FROM factors AS f
JOIN datasets AS d USING (dataset_id)
JOIN sources AS s USING (source_id);
