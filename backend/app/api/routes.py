from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.models.schemas import SearchResult
from app.services.enrich import EnrichService
from app.services.openalex import OpenAlexService
from app.services.storage import StorageService
from app.services.verify_links import LinkVerifier
from app.services.web_search import WebSearchService

router = APIRouter(prefix="/api/v1")

openalex_service = OpenAlexService()
web_search_service = WebSearchService()
storage_service = StorageService()
link_verifier = LinkVerifier()
enrich_service = EnrichService()


# --- Projects ---


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


@router.post("/projects")
async def create_project(body: ProjectCreate) -> dict:
    return storage_service.create_project(body.name, body.description)


@router.get("/projects")
async def list_projects() -> list[dict]:
    return storage_service.list_projects()


@router.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict:
    return storage_service.get_project(project_id)


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str) -> dict:
    return storage_service.delete_project(project_id)


@router.get("/projects/{project_id}/stakeholders")
async def get_project_stakeholders(project_id: str) -> list[dict]:
    return storage_service.get_project_stakeholders(project_id)


@router.get("/projects/{project_id}/searches")
async def get_project_searches(project_id: str) -> list[dict]:
    return storage_service.get_search_history(project_id=project_id)


@router.delete("/projects/{project_id}/data")
async def clear_project_data(project_id: str) -> dict:
    return storage_service.clear_project(project_id)


# --- Upload (paste names) ---


class UploadBody(BaseModel):
    text: str
    context: str = ""


@router.post("/projects/{project_id}/upload")
async def upload_stakeholders(project_id: str, body: UploadBody) -> dict:
    """Parse free-form text into stakeholder names, enrich via web search, and save."""
    result = await enrich_service.enrich_from_text(body.text, context=body.context)
    result = await link_verifier.verify_search_result(result)
    stats = storage_service.save_search_result(result, project_id=project_id)
    return stats


# --- Expand (find more) ---


class ExpandBody(BaseModel):
    prompt: str = "find more stakeholders"
    max_results: int = 5


@router.post("/projects/{project_id}/expand")
async def expand_stakeholders(project_id: str, body: ExpandBody) -> dict:
    """Find new stakeholders not already in the project."""
    existing = storage_service.get_project_stakeholders(project_id)
    existing_names = [s["name"] for s in existing]

    project = storage_service.get_project(project_id)
    topic = f"{body.prompt} (project: {project['name']})"

    result = await web_search_service.search_all_sectors(
        topic, max_results_per_sector=max(1, body.max_results // 5)
    )

    # Deduplicate against existing
    new_stakeholders = [
        s
        for s in result.stakeholders
        if s.name.lower() not in {n.lower() for n in existing_names}
    ]
    result = SearchResult(
        source=result.source,
        query=result.query,
        stakeholders=new_stakeholders[: body.max_results],
        total_records_scanned=result.total_records_scanned,
    )

    result = await link_verifier.verify_search_result(result)
    stats = storage_service.save_search_result(result, project_id=project_id)
    return stats


# --- Search (existing, now project-aware) ---


@router.get("/search/openalex", response_model=SearchResult)
async def search_openalex(
    q: str = Query(description="Topic or search query"),
    max_results: int = Query(default=25, ge=1, le=200),
    project_id: str | None = Query(default=None),
) -> SearchResult:
    result = await openalex_service.search_stakeholders(q, max_results=max_results)
    if project_id:
        storage_service.save_search_result(result, project_id=project_id)
    return result


@router.get("/search/web", response_model=SearchResult)
async def search_web(
    q: str = Query(description="Topic or search query"),
    sector: str = Query(
        default="civil_society",
        description="Sector to focus on",
        enum=["research", "government", "business", "funder", "civil_society"],
    ),
    max_results: int = Query(default=10, ge=1, le=20),
    verify: bool = Query(default=True),
    project_id: str | None = Query(default=None),
) -> SearchResult:
    result = await web_search_service.search_stakeholders(
        q, sector=sector, max_results=max_results
    )
    if verify:
        result = await link_verifier.verify_search_result(result)
    if project_id:
        storage_service.save_search_result(result, project_id=project_id)
    return result


@router.get("/search/web/all", response_model=SearchResult)
async def search_web_all_sectors(
    q: str = Query(description="Topic or search query"),
    max_results_per_sector: int = Query(default=8, ge=1, le=15),
    verify: bool = Query(default=True),
    project_id: str | None = Query(default=None),
) -> SearchResult:
    result = await web_search_service.search_all_sectors(
        q, max_results_per_sector=max_results_per_sector
    )
    if verify:
        result = await link_verifier.verify_search_result(result)
    if project_id:
        storage_service.save_search_result(result, project_id=project_id)
    return result


# --- Edit/delete individual records ---


class StakeholderUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    entity_type: str | None = None
    sector: str | None = None
    geographic_scope: str | None = None
    website: str | None = None


@router.patch("/stakeholders/{stakeholder_id}")
async def update_stakeholder(stakeholder_id: str, body: StakeholderUpdate) -> dict:
    return storage_service.update_stakeholder(
        stakeholder_id, body.model_dump(exclude_none=True)
    )


@router.delete("/stakeholders/{stakeholder_id}")
async def delete_stakeholder(stakeholder_id: str) -> dict:
    return storage_service.delete_stakeholder(stakeholder_id)


@router.delete("/activities/{activity_id}")
async def delete_activity(activity_id: str) -> dict:
    return storage_service.delete_activity(activity_id)


# --- Legacy endpoints (kept for backwards compat) ---


@router.get("/status")
async def api_status():
    return {"status": "ok"}


@router.get("/searches")
async def get_search_history() -> list[dict]:
    return storage_service.get_search_history()


@router.get("/searches/{search_run_id}")
async def get_search_run_results(search_run_id: str) -> dict:
    return storage_service.get_search_run_results(search_run_id)


@router.delete("/searches/{search_run_id}")
async def delete_search_run(search_run_id: str) -> dict:
    return storage_service.delete_search_run(search_run_id)
