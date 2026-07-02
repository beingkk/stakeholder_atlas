import { useEffect, useMemo, useState } from "react";
import {
  listProjects,
  createProject,
  deleteProject,
  getProjectStakeholders,
  getProjectSearches,
  searchWeb,
  searchWebAll,
  searchOpenAlex,
  uploadStakeholders,
  updateStakeholder,
  deleteStakeholder,
  deleteActivity,
  type Project,
  type Stakeholder,
  type SearchRun,
} from "./lib/api";

const SECTORS = [
  { key: "all", label: "All sectors" },
  { key: "research", label: "Research" },
  { key: "government", label: "Government" },
  { key: "business", label: "Business" },
  { key: "funder", label: "Funders" },
  { key: "civil_society", label: "Civil society" },
] as const;

type Source = "openalex" | "web";

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [newProjectName, setNewProjectName] = useState("");

  useEffect(() => {
    listProjects().then(setProjects).catch(() => {});
  }, []);

  if (!activeProject) {
    return (
      <>
        <nav className="nav">
          <div className="nav__brand">Stakeholder <b>Atlas</b></div>
        </nav>
        <div className="container">
          <h2 style={{ color: "var(--navy)", marginBottom: 16 }}>Projects</h2>
          <div className="project-list">
            {projects.map((p) => (
              <div key={p.id} className="project-card" onClick={() => setActiveProject(p)}>
                <div className="project-card__name">{p.name}</div>
                {p.description && <div className="project-card__desc">{p.description}</div>}
                <div className="project-card__meta">
                  {new Date(p.created_at).toLocaleDateString()}
                </div>
                <button
                  className="history__delete"
                  title="Delete project"
                  onClick={async (e) => {
                    e.stopPropagation();
                    if (!confirm(`Delete project "${p.name}" and all its data?`)) return;
                    await deleteProject(p.id);
                    setProjects((ps) => ps.filter((x) => x.id !== p.id));
                  }}
                >×</button>
              </div>
            ))}
          </div>
          <form
            className="search-form"
            style={{ marginTop: 20 }}
            onSubmit={async (e) => {
              e.preventDefault();
              if (!newProjectName.trim()) return;
              const p = await createProject(newProjectName.trim());
              setProjects((ps) => [p, ...ps]);
              setNewProjectName("");
              setActiveProject(p);
            }}
          >
            <input
              className="search-input"
              placeholder="New project name..."
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
            />
            <button className="btn" type="submit" disabled={!newProjectName.trim()}>
              Create
            </button>
          </form>
        </div>
      </>
    );
  }

  return (
    <>
      <nav className="nav">
        <div className="nav__brand">Stakeholder <b>Atlas</b></div>
        <button className="nav__back" onClick={() => setActiveProject(null)}>
          &lt; Projects
        </button>
      </nav>
      <div className="container">
        <h2 style={{ color: "var(--navy)", marginBottom: 4 }}>{activeProject.name}</h2>
        {activeProject.description && (
          <p style={{ color: "var(--grey)", fontSize: 13, marginBottom: 16 }}>{activeProject.description}</p>
        )}
        <ProjectView project={activeProject} />
      </div>
    </>
  );
}

function ProjectView({ project }: { project: Project }) {
  const [stakeholders, setStakeholders] = useState<Stakeholder[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Search state
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<Source>("web");
  const [sector, setSector] = useState("all");
  const [maxResults, setMaxResults] = useState(5);
  const [optionsOpen, setOptionsOpen] = useState(false);

  // Upload state
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadText, setUploadText] = useState("");

  // Search history
  const [searches, setSearches] = useState<SearchRun[]>([]);


  // Filters
  const [filterSector, setFilterSector] = useState("all");
  const [filterGeo, setFilterGeo] = useState("all");
  const [filterType, setFilterType] = useState("all");

  useEffect(() => {
    loadStakeholders();
    loadSearches();
  }, [project.id]);

  const loadStakeholders = async () => {
    try {
      const data = await getProjectStakeholders(project.id);
      setStakeholders(data);
    } catch { /* empty */ }
  };

  const loadSearches = async () => {
    try {
      const data = await getProjectSearches(project.id);
      setSearches(data);
    } catch { /* empty */ }
  };

  const filtered = useMemo(() => {
    return stakeholders.filter((s) => {
      if (filterSector !== "all" && s.sector !== filterSector) return false;
      if (filterGeo !== "all" && s.geographic_scope !== filterGeo) return false;
      if (filterType !== "all" && s.entity_type !== filterType) return false;
      return true;
    });
  }, [stakeholders, filterSector, filterGeo, filterType]);

  const filterOptions = useMemo(() => {
    const sectors = [...new Set(stakeholders.map((s) => s.sector))];
    const geos = [...new Set(stakeholders.map((s) => s.geographic_scope).filter(Boolean))];
    const types = [...new Set(stakeholders.map((s) => s.entity_type))];
    return { sectors, geos, types };
  }, [stakeholders]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      if (source === "openalex") {
        await searchOpenAlex(query, maxResults * 3, project.id);
      } else if (sector === "all") {
        await searchWebAll(query, maxResults, project.id);
      } else {
        await searchWeb(query, sector, maxResults, project.id);
      }
      await loadStakeholders();
      await loadSearches();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await uploadStakeholders(project.id, uploadText, project.name);
      await loadStakeholders();
      await loadSearches();
      setUploadText("");
      setUploadOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };


  const handleDeleteStakeholder = async (id: string) => {
    if (!confirm("Remove this stakeholder?")) return;
    try {
      await deleteStakeholder(id);
      setStakeholders((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleDeleteActivity = async (stakeholderId: string, activityId: string) => {
    try {
      await deleteActivity(activityId);
      setStakeholders((prev) =>
        prev.map((s) =>
          s.id === stakeholderId
            ? { ...s, activities: s.activities.filter((a) => a.id !== activityId) }
            : s
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleUpdateStakeholder = async (id: string, updates: Record<string, string>) => {
    try {
      await updateStakeholder(id, updates);
      setStakeholders((prev) =>
        prev.map((s) => (s.id === id ? { ...s, ...updates } : s))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  };

  return (
    <>
      {/* Search */}
      <form className="search-form" onSubmit={handleSearch}>
        <input
          className="search-input"
          type="text"
          placeholder="Search for stakeholders by topic..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn" type="submit" disabled={loading || !query.trim()}>
          {loading ? "Working…" : "Search"}
        </button>
      </form>

      <button className="options-toggle" onClick={() => setOptionsOpen(!optionsOpen)} type="button">
        <span className={`options-toggle__arrow ${optionsOpen ? "options-toggle__arrow--open" : ""}`}>›</span>
        Search options
      </button>

      {optionsOpen && (
        <div className="search-options">
          <div className="search-options__row">
            <span className="search-options__label">Source:</span>
            <div className="chips">
              <span className={`chip ${source === "openalex" ? "chip--on" : ""}`} onClick={() => setSource("openalex")}>OpenAlex</span>
              <span className={`chip ${source === "web" ? "chip--on" : ""}`} onClick={() => setSource("web")}>Web search</span>
            </div>
          </div>
          {source === "web" && (
            <div className="search-options__row">
              <span className="search-options__label">Sector:</span>
              <div className="chips">
                {SECTORS.map((s) => (
                  <span key={s.key} className={`chip ${sector === s.key ? "chip--on" : ""}`} onClick={() => setSector(s.key)}>{s.label}</span>
                ))}
              </div>
            </div>
          )}
          <div className="search-options__row">
            <span className="search-options__label">Results:</span>
            <input className="search-options__number" type="number" min={1} max={20} value={maxResults} onChange={(e) => { const v = parseInt(e.target.value, 10); if (Number.isFinite(v)) setMaxResults(Math.max(1, Math.min(20, v))); }} />
            <span className="search-options__hint">per sector</span>
          </div>
        </div>
      )}

      <div className="section-divider" />

      {/* Add from list */}
      <div className="search-form">
        <button className="btn" type="button" onClick={() => setUploadOpen(!uploadOpen)}>
          + Add from list
        </button>
      </div>

      {uploadOpen && (
        <form className="panel" onSubmit={handleUpload}>
          <textarea
            className="panel__textarea"
            placeholder="Paste stakeholders in any format — names, lists, paragraphs, tables..."
            value={uploadText}
            onChange={(e) => setUploadText(e.target.value)}
            rows={5}
          />
          <button className="btn" type="submit" disabled={loading || !uploadText.trim()} style={{ marginTop: 10 }}>
            {loading ? "Enriching…" : "Upload & enrich"}
          </button>
        </form>
      )}


      {error && <p style={{ color: "var(--orange)" }}>{error}</p>}
      {loading && <div className="loading">Working…</div>}

      {/* Stats + filters */}
      {stakeholders.length > 0 && (
        <>
          <div className="stats">
            <span><span className="stats__count">{stakeholders.length}</span> stakeholders</span>
          </div>

          {(filterOptions.sectors.length > 1 || filterOptions.geos.length > 1 || filterOptions.types.length > 1) && (
            <div className="result-filters">
              {filterOptions.sectors.length > 1 && (
                <select value={filterSector} onChange={(e) => setFilterSector(e.target.value)}>
                  <option value="all">ALL SECTORS</option>
                  {filterOptions.sectors.map((s) => <option key={s} value={s}>{s.replace(/_/g, " ").toUpperCase()}</option>)}
                </select>
              )}
              {filterOptions.geos.length > 1 && (
                <select value={filterGeo} onChange={(e) => setFilterGeo(e.target.value)}>
                  <option value="all">ALL GEOGRAPHIES</option>
                  {filterOptions.geos.map((g) => <option key={g} value={g!}>{g!.replace(/_/g, " ").toUpperCase()}</option>)}
                </select>
              )}
              {filterOptions.types.length > 1 && (
                <select value={filterType} onChange={(e) => setFilterType(e.target.value)}>
                  <option value="all">ALL TYPES</option>
                  {filterOptions.types.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ").toUpperCase()}</option>)}
                </select>
              )}
              <span className="result-filters__count">Showing {filtered.length} of {stakeholders.length}</span>
            </div>
          )}

          {filtered.map((s) => (
            <StakeholderCard
              key={s.id || s.name}
              stakeholder={s}
              expanded={expandedId === s.id}
              onToggle={() => setExpandedId(expandedId === s.id ? null : (s.id || null))}
              onDelete={() => s.id && handleDeleteStakeholder(s.id)}
              onDeleteActivity={(actId) => s.id && handleDeleteActivity(s.id, actId)}
              onUpdate={(updates) => s.id && handleUpdateStakeholder(s.id, updates)}
            />
          ))}
        </>
      )}

      {/* Search history */}
      {searches.length > 0 && (
        <div className="history">
          <div className="history__head">
            <span className="history__title">Searches in this project</span>
          </div>
          {searches.map((run) => (
            <div key={run.id} className="history__item" style={{ cursor: "default" }}>
              <span className="history__query">{run.query}</span>
              <span className="chip chip--source">{run.source}</span>
              {run.sector && <span className="chip">{run.sector.replace(/_/g, " ")}</span>}
              <span className="history__meta">
                {new Date(run.created_at).toLocaleDateString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function StakeholderCard({
  stakeholder: s,
  expanded,
  onToggle,
  onDelete,
  onDeleteActivity,
  onUpdate,
}: {
  stakeholder: Stakeholder;
  expanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onDeleteActivity: (activityId: string) => void;
  onUpdate: (updates: Record<string, string>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [desc, setDesc] = useState(s.description || "");

  const startEditing = () => { setDesc(s.description || ""); setEditing(true); };

  return (
    <div
      className={`card ${expanded ? "card--open" : ""}`}
      onClick={!expanded ? onToggle : undefined}
      style={{ cursor: expanded ? "default" : "pointer" }}
    >
      <div className="card__head">
        <span className="card__name">{s.name}</span>
        <div className="card__tags">
          {s.sector && <span className="card__tag">{s.sector.replace(/_/g, " ").toUpperCase()}</span>}
          {s.geographic_scope && <span className="card__tag">{s.geographic_scope.replace(/_/g, " ").toUpperCase()}</span>}
          <span className="card__tag">{s.entity_type.replace(/_/g, " ").toUpperCase()}</span>
        </div>
      </div>

      {!editing && s.description && <div className="card__desc">{s.description}</div>}

      {editing && (
        <div className="card__edit" onClick={(e) => e.stopPropagation()}>
          <textarea
            className="panel__textarea"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            rows={2}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
            <button className="btn" onClick={() => { onUpdate({ description: desc }); setEditing(false); }}>Save</button>
            <button className="btn--sec" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      )}

      {s.website && (
        <div className="card__meta">
          <a className="card__link" href={s.website} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
            {(() => { try { return new URL(s.website).hostname; } catch { return s.website; } })()}
            <svg className="card__ext-icon" viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M4.5 1.5H2a.5.5 0 0 0-.5.5v8a.5.5 0 0 0 .5.5h8a.5.5 0 0 0 .5-.5V7.5M7 1.5h3.5V5M6 6.5l4.5-4.5" />
            </svg>
          </a>
        </div>
      )}

      {expanded && (
        <div className="activities">
          <div className="activities__head">
            <span className="activities__title">Activities ({s.activities.length})</span>
            <div style={{ display: "flex", gap: 4 }}>
              <button className="activities__collapse" onClick={() => editing ? setEditing(false) : startEditing()} title="Edit">
                <svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M8.5 1.5l2 2-6 6H2.5v-2l6-6z" />
                </svg>
              </button>
              <button className="activities__collapse" style={{ color: "var(--red)" }} onClick={(e) => { e.stopPropagation(); onDelete(); }} title="Remove stakeholder">
                <svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M2 3h8M4.5 3V2h3v1M3 3v7.5h6V3M5 5.5v3M7 5.5v3" />
                </svg>
              </button>
              <button className="activities__collapse" onClick={onToggle} title="Collapse">
                <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M2.5 7.5 6 4l3.5 3.5" />
                </svg>
              </button>
            </div>
          </div>
          {s.activities.map((a) => (
            <div key={a.id || a.title} className="activity">
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <div className="activity__title" style={{ flex: 1 }}>{a.title}</div>
                {a.id && (
                  <button
                    className="history__delete"
                    title="Remove activity"
                    onClick={(e) => { e.stopPropagation(); onDeleteActivity(a.id!); }}
                    style={{ flexShrink: 0 }}
                  >×</button>
                )}
              </div>
              {a.summary && <div className="activity__summary">{a.summary}</div>}
              {a.source_record_id && (
                a.source_record_id.startsWith("http") ? (
                  <a className="activity__source" href={a.source_record_id} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                    {a.source_record_id}
                  </a>
                ) : (
                  <span className="activity__source">{a.source_record_id}</span>
                )
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
