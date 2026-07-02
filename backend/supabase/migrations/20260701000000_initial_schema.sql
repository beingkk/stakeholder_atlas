-- Stakeholder Atlas: initial schema
-- Maps to the Pydantic models in app/models/schemas.py

-- Enum types
CREATE TYPE entity_type AS ENUM ('individual', 'organisation', 'network', 'other');
CREATE TYPE sector AS ENUM ('research', 'government', 'business', 'funder', 'civil_society', 'other');
CREATE TYPE geographic_scope AS ENUM ('local', 'national', 'global');

-- Stakeholders: the core resolved entities
CREATE TABLE stakeholders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    entity_type entity_type NOT NULL,
    sector sector NOT NULL,
    geographic_scope geographic_scope,
    description TEXT,
    website TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- External IDs: stable identifiers for entity resolution
CREATE TABLE external_ids (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stakeholder_id UUID NOT NULL REFERENCES stakeholders(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    value TEXT NOT NULL,
    UNIQUE (type, value)
);

CREATE INDEX idx_external_ids_stakeholder ON external_ids(stakeholder_id);
CREATE INDEX idx_external_ids_type_value ON external_ids(type, value);

-- Activities: evidence of what a stakeholder is doing
CREATE TABLE activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stakeholder_id UUID NOT NULL REFERENCES stakeholders(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    source_record_id TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    activity_date DATE,
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_activities_stakeholder ON activities(stakeholder_id);
CREATE INDEX idx_activities_source ON activities(source);

-- Search runs: track what searches produced which stakeholders
CREATE TABLE search_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    query TEXT NOT NULL,
    sector sector,
    total_records_scanned INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Junction: which stakeholders came from which search run
CREATE TABLE search_run_stakeholders (
    search_run_id UUID NOT NULL REFERENCES search_runs(id) ON DELETE CASCADE,
    stakeholder_id UUID NOT NULL REFERENCES stakeholders(id) ON DELETE CASCADE,
    PRIMARY KEY (search_run_id, stakeholder_id)
);

-- Auto-update updated_at on stakeholders
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER stakeholders_updated_at
    BEFORE UPDATE ON stakeholders
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
