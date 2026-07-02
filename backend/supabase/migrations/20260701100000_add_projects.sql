-- Add projects table and link existing tables to it

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Add project_id to search_runs (nullable for backwards compat with existing data)
ALTER TABLE search_runs ADD COLUMN project_id UUID REFERENCES projects(id) ON DELETE CASCADE;
CREATE INDEX idx_search_runs_project ON search_runs(project_id);

-- Add project_id to stakeholders
ALTER TABLE stakeholders ADD COLUMN project_id UUID REFERENCES projects(id) ON DELETE CASCADE;
CREATE INDEX idx_stakeholders_project ON stakeholders(project_id);
