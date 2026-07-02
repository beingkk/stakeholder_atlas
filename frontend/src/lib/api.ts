const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export interface ExternalId {
  type: string;
  value: string;
}

export interface Activity {
  id?: string;
  source: string;
  source_record_id: string | null;
  title: string;
  summary: string | null;
  activity_date: string | null;
  data: { type: string; content: Record<string, unknown> } | null;
}

export interface Stakeholder {
  id?: string;
  name: string;
  entity_type: string;
  sector: string;
  geographic_scope: string | null;
  description: string | null;
  website: string | null;
  external_ids: ExternalId[];
  activities: Activity[];
}

export interface SearchResult {
  source: string;
  query: string;
  stakeholders: Stakeholder[];
  total_records_scanned: number;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  stakeholder_count?: number;
  search_count?: number;
}

export interface SearchRun {
  id: string;
  source: string;
  query: string;
  sector: string | null;
  total_records_scanned: number;
  created_at: string;
}

// --- Projects ---

export async function createProject(name: string, description?: string): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/v1/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
  if (!res.ok) throw new Error(`Create project failed: ${res.status}`);
  return res.json();
}

export async function listProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/api/v1/projects`);
  if (!res.ok) throw new Error(`List projects failed: ${res.status}`);
  return res.json();
}

export async function getProject(id: string): Promise<Project> {
  const res = await fetch(`${API_BASE}/api/v1/projects/${id}`);
  if (!res.ok) throw new Error(`Get project failed: ${res.status}`);
  return res.json();
}

export async function deleteProject(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/projects/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete project failed: ${res.status}`);
}

export async function getProjectStakeholders(projectId: string): Promise<Stakeholder[]> {
  const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/stakeholders`);
  if (!res.ok) throw new Error(`Get stakeholders failed: ${res.status}`);
  return res.json();
}

export async function getProjectSearches(projectId: string): Promise<SearchRun[]> {
  const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/searches`);
  if (!res.ok) throw new Error(`Get searches failed: ${res.status}`);
  return res.json();
}

// --- Search (project-aware) ---

export async function searchWeb(
  query: string,
  sector: string,
  maxResults = 10,
  projectId?: string,
): Promise<SearchResult> {
  const params = new URLSearchParams({ q: query, sector, max_results: String(maxResults) });
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/v1/search/web?${params}`);
  if (!res.ok) throw new Error(`Web search failed: ${res.status}`);
  return res.json();
}

export async function searchWebAll(
  query: string,
  maxResultsPerSector = 5,
  projectId?: string,
): Promise<SearchResult> {
  const params = new URLSearchParams({ q: query, max_results_per_sector: String(maxResultsPerSector) });
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/v1/search/web/all?${params}`);
  if (!res.ok) throw new Error(`Web search (all) failed: ${res.status}`);
  return res.json();
}

export async function searchOpenAlex(
  query: string,
  maxResults = 25,
  projectId?: string,
): Promise<SearchResult> {
  const params = new URLSearchParams({ q: query, max_results: String(maxResults) });
  if (projectId) params.set("project_id", projectId);
  const res = await fetch(`${API_BASE}/api/v1/search/openalex?${params}`);
  if (!res.ok) throw new Error(`OpenAlex search failed: ${res.status}`);
  return res.json();
}

// --- Upload & Expand ---

export async function uploadStakeholders(
  projectId: string,
  text: string,
  context = "",
): Promise<{ search_run_id: string; stakeholders_saved: number }> {
  const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/upload`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, context }),
  });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function expandStakeholders(
  projectId: string,
  prompt: string,
  maxResults = 5,
): Promise<{ search_run_id: string; stakeholders_saved: number }> {
  const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/expand`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, max_results: maxResults }),
  });
  if (!res.ok) throw new Error(`Expand failed: ${res.status}`);
  return res.json();
}

// --- Edit/Delete ---

export async function updateStakeholder(
  id: string,
  updates: Partial<Pick<Stakeholder, "name" | "description" | "entity_type" | "sector" | "geographic_scope" | "website">>,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/stakeholders/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Update failed: ${res.status}`);
}

export async function deleteStakeholder(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/stakeholders/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete stakeholder failed: ${res.status}`);
}

export async function deleteActivity(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/v1/activities/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete activity failed: ${res.status}`);
}
