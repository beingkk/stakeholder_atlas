"""Storage service for persisting stakeholder data to Supabase."""

import logging

from app.core.config import settings
from app.models.schemas import SearchResult, Stakeholder
from supabase import Client, create_client

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self):
        self._client: Client | None = None
        if settings.SUPABASE_URL and settings.SUPABASE_KEY:
            self._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        else:
            logger.warning("Supabase not configured — storage disabled")

    def _ensure_client(self) -> Client:
        if self._client is None:
            raise RuntimeError(
                "Storage unavailable: SUPABASE_URL/SUPABASE_KEY not configured"
            )
        return self._client

    # --- Projects ---

    def create_project(self, name: str, description: str | None = None) -> dict:
        client = self._ensure_client()
        row = (
            client.table("projects")
            .insert(
                {
                    "name": name,
                    "description": description,
                }
            )
            .execute()
        )
        return row.data[0]

    def list_projects(self) -> list[dict]:
        client = self._ensure_client()
        result = (
            client.table("projects")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return result.data

    def get_project(self, project_id: str) -> dict:
        client = self._ensure_client()
        project = (
            client.table("projects").select("*").eq("id", project_id).single().execute()
        )
        stakeholder_count = (
            client.table("stakeholders")
            .select("id", count="exact")
            .eq("project_id", project_id)
            .execute()
        )
        search_count = (
            client.table("search_runs")
            .select("id", count="exact")
            .eq("project_id", project_id)
            .execute()
        )
        return {
            **project.data,
            "stakeholder_count": stakeholder_count.count or 0,
            "search_count": search_count.count or 0,
        }

    def delete_project(self, project_id: str) -> dict:
        client = self._ensure_client()
        client.table("projects").delete().eq("id", project_id).execute()
        return {"status": "deleted", "id": project_id}

    # --- Search runs (project-scoped) ---

    def save_search_result(
        self, result: SearchResult, project_id: str | None = None
    ) -> dict:
        """Persist a SearchResult: creates a search_run and upserts stakeholders."""
        client = self._ensure_client()

        sector = None
        if result.stakeholders:
            sector = result.stakeholders[0].sector.value

        run_data = {
            "source": result.source,
            "query": result.query,
            "sector": sector,
            "total_records_scanned": result.total_records_scanned,
        }
        if project_id:
            run_data["project_id"] = project_id

        search_run = client.table("search_runs").insert(run_data).execute()
        search_run_id = search_run.data[0]["id"]
        stats = {"search_run_id": search_run_id, "stakeholders_saved": 0}

        for stakeholder in result.stakeholders:
            stakeholder_id = self._upsert_stakeholder(
                client, stakeholder, project_id=project_id
            )
            if stakeholder_id:
                client.table("search_run_stakeholders").insert(
                    {
                        "search_run_id": search_run_id,
                        "stakeholder_id": stakeholder_id,
                    }
                ).execute()
                stats["stakeholders_saved"] += 1

        return stats

    def get_search_history(self, project_id: str | None = None) -> list[dict]:
        client = self._ensure_client()
        query = (
            client.table("search_runs")
            .select("*")
            .order("created_at", desc=True)
            .limit(50)
        )
        if project_id:
            query = query.eq("project_id", project_id)
        return query.execute().data

    def get_search_run_results(self, search_run_id: str) -> dict:
        client = self._ensure_client()

        run = (
            client.table("search_runs")
            .select("*")
            .eq("id", search_run_id)
            .single()
            .execute()
        )
        run_data = run.data

        links = (
            client.table("search_run_stakeholders")
            .select("stakeholder_id")
            .eq("search_run_id", search_run_id)
            .execute()
        )
        stakeholder_ids = [r["stakeholder_id"] for r in links.data]
        stakeholders = [self._load_stakeholder(client, sid) for sid in stakeholder_ids]

        return {
            "source": run_data["source"],
            "query": run_data["query"],
            "stakeholders": [s for s in stakeholders if s],
            "total_records_scanned": run_data["total_records_scanned"],
        }

    def delete_search_run(self, search_run_id: str) -> dict:
        client = self._ensure_client()

        linked = (
            client.table("search_run_stakeholders")
            .select("stakeholder_id")
            .eq("search_run_id", search_run_id)
            .execute()
        )
        stakeholder_ids = [r["stakeholder_id"] for r in linked.data]

        client.table("search_run_stakeholders").delete().eq(
            "search_run_id", search_run_id
        ).execute()
        client.table("search_runs").delete().eq("id", search_run_id).execute()

        for sid in stakeholder_ids:
            remaining = (
                client.table("search_run_stakeholders")
                .select("search_run_id")
                .eq("stakeholder_id", sid)
                .limit(1)
                .execute()
            )
            if not remaining.data:
                client.table("activities").delete().eq("stakeholder_id", sid).execute()
                client.table("external_ids").delete().eq(
                    "stakeholder_id", sid
                ).execute()
                client.table("stakeholders").delete().eq("id", sid).execute()

        return {"status": "deleted", "id": search_run_id}

    def clear_project(self, project_id: str) -> dict:
        """Delete all stakeholders and searches in a project."""
        client = self._ensure_client()
        run_ids = [
            r["id"]
            for r in client.table("search_runs")
            .select("id")
            .eq("project_id", project_id)
            .execute()
            .data
        ]
        if run_ids:
            client.table("search_run_stakeholders").delete().in_(
                "search_run_id", run_ids
            ).execute()
        client.table("search_runs").delete().eq("project_id", project_id).execute()
        client.table("stakeholders").delete().eq("project_id", project_id).execute()
        return {"status": "cleared"}

    # --- Project stakeholders (pooled view) ---

    def get_project_stakeholders(self, project_id: str) -> list[dict]:
        """Get all stakeholders in a project with their activities and IDs."""
        client = self._ensure_client()
        rows = (
            client.table("stakeholders")
            .select("*")
            .eq("project_id", project_id)
            .order("created_at", desc=True)
            .execute()
        )
        results = [self._load_stakeholder(client, r["id"]) for r in rows.data]
        return [s for s in results if s]

    # --- Edit/delete individual records ---

    def update_stakeholder(self, stakeholder_id: str, updates: dict) -> dict:
        """Update fields on a stakeholder."""
        client = self._ensure_client()
        allowed = {
            "name",
            "description",
            "entity_type",
            "sector",
            "geographic_scope",
            "website",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not filtered:
            return {"status": "no_changes"}
        client.table("stakeholders").update(filtered).eq("id", stakeholder_id).execute()
        return {"status": "updated", "id": stakeholder_id}

    def delete_stakeholder(self, stakeholder_id: str) -> dict:
        client = self._ensure_client()
        client.table("search_run_stakeholders").delete().eq(
            "stakeholder_id", stakeholder_id
        ).execute()
        client.table("activities").delete().eq(
            "stakeholder_id", stakeholder_id
        ).execute()
        client.table("external_ids").delete().eq(
            "stakeholder_id", stakeholder_id
        ).execute()
        client.table("stakeholders").delete().eq("id", stakeholder_id).execute()
        return {"status": "deleted", "id": stakeholder_id}

    def delete_activity(self, activity_id: str) -> dict:
        client = self._ensure_client()
        client.table("activities").delete().eq("id", activity_id).execute()
        return {"status": "deleted", "id": activity_id}

    # --- Helpers ---

    def _load_stakeholder(self, client: Client, stakeholder_id: str) -> dict | None:
        try:
            row = (
                client.table("stakeholders")
                .select("*")
                .eq("id", stakeholder_id)
                .single()
                .execute()
            )
        except Exception:
            return None
        s = row.data

        ext_ids = (
            client.table("external_ids")
            .select("type, value")
            .eq("stakeholder_id", stakeholder_id)
            .execute()
        )
        activities = (
            client.table("activities")
            .select("id, source, source_record_id, title, summary, activity_date, data")
            .eq("stakeholder_id", stakeholder_id)
            .execute()
        )

        return {
            "id": s["id"],
            "name": s["name"],
            "entity_type": s["entity_type"],
            "sector": s["sector"],
            "geographic_scope": s["geographic_scope"],
            "description": s["description"],
            "website": s["website"],
            "external_ids": ext_ids.data,
            "activities": activities.data,
        }

    def _upsert_stakeholder(
        self, client: Client, stakeholder: Stakeholder, project_id: str | None = None
    ) -> str | None:
        existing_id = self._find_by_external_id(client, stakeholder)
        if existing_id:
            self._add_new_activities(client, existing_id, stakeholder)
            return existing_id

        row_data = {
            "name": stakeholder.name,
            "entity_type": stakeholder.entity_type.value,
            "sector": stakeholder.sector.value,
            "geographic_scope": (
                stakeholder.geographic_scope.value
                if stakeholder.geographic_scope
                else None
            ),
            "description": stakeholder.description,
            "website": stakeholder.website,
        }
        if project_id:
            row_data["project_id"] = project_id

        row = client.table("stakeholders").insert(row_data).execute()
        stakeholder_id = row.data[0]["id"]

        for eid in stakeholder.external_ids:
            client.table("external_ids").upsert(
                {
                    "stakeholder_id": stakeholder_id,
                    "type": eid.type,
                    "value": eid.value,
                },
                on_conflict="type,value",
            ).execute()

        for activity in stakeholder.activities:
            client.table("activities").insert(
                {
                    "stakeholder_id": stakeholder_id,
                    "source": activity.source,
                    "source_record_id": activity.source_record_id,
                    "title": activity.title,
                    "summary": activity.summary,
                    "activity_date": (
                        activity.activity_date.isoformat()
                        if activity.activity_date
                        else None
                    ),
                    "data": activity.data.model_dump() if activity.data else None,
                }
            ).execute()

        return stakeholder_id

    def _find_by_external_id(
        self, client: Client, stakeholder: Stakeholder
    ) -> str | None:
        for eid in stakeholder.external_ids:
            result = (
                client.table("external_ids")
                .select("stakeholder_id")
                .eq("type", eid.type)
                .eq("value", eid.value)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]["stakeholder_id"]
        return None

    def _add_new_activities(
        self, client: Client, stakeholder_id: str, stakeholder: Stakeholder
    ) -> None:
        for activity in stakeholder.activities:
            if activity.source_record_id:
                existing = (
                    client.table("activities")
                    .select("id")
                    .eq("stakeholder_id", stakeholder_id)
                    .eq("source_record_id", activity.source_record_id)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue

            client.table("activities").insert(
                {
                    "stakeholder_id": stakeholder_id,
                    "source": activity.source,
                    "source_record_id": activity.source_record_id,
                    "title": activity.title,
                    "summary": activity.summary,
                    "activity_date": (
                        activity.activity_date.isoformat()
                        if activity.activity_date
                        else None
                    ),
                    "data": activity.data.model_dump() if activity.data else None,
                }
            ).execute()
