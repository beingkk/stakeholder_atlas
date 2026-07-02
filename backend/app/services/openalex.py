"""OpenAlex search service.

Queries the OpenAlex API for works matching a topic, then extracts
researchers (authors) and institutions as Stakeholder objects with
their publications attached as Activities.

Uses the pyalex library for API communication (same as Policy Atlas).
"""

import logging
from datetime import date

from pyalex import Works, config

from app.core.config import settings
from app.models.schemas import (
    Activity,
    EntityType,
    ExternalId,
    LinkedData,
    SearchResult,
    Sector,
    Stakeholder,
)

logger = logging.getLogger(__name__)


class OpenAlexService:
    def __init__(self):
        if settings.OPENALEX_EMAIL:
            config.email = settings.OPENALEX_EMAIL

        if settings.OPENALEX_API_KEY:
            config.api_key = settings.OPENALEX_API_KEY
            logger.info("OpenAlex API key configured")
        else:
            logger.warning("OpenAlex API key not configured — using polite pool")

        config.max_retries = 3
        config.retry_backoff_factor = 0.5

    async def search_stakeholders(
        self,
        query: str,
        *,
        max_results: int = settings.DEFAULT_MAX_RESULTS,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> SearchResult:
        """Search OpenAlex works and construct stakeholders from results.

        Args:
            query: Free-text search query (topic/concept).
            max_results: Number of works to fetch.
            date_from: Only include works published on or after this date.
            date_to: Only include works published on or before this date.

        Returns:
            SearchResult containing deduplicated researchers and institutions.
        """
        works = self._fetch_works(
            query, max_results=max_results, date_from=date_from, date_to=date_to
        )

        authors: dict[str, Stakeholder] = {}
        institutions: dict[str, Stakeholder] = {}

        for work in works:
            work_activity_data = _work_to_linked_data(work)
            pub_date = _parse_date(work.get("publication_date"))
            work_title = work.get("title") or "Untitled"

            for authorship in work.get("authorships", []):
                author_info = authorship.get("author", {})
                if not author_info:
                    continue

                author_id = author_info.get("id", "")
                author_name = author_info.get("display_name", "Unknown")

                if author_id and author_id not in authors:
                    authors[author_id] = _build_author_stakeholder(author_info)

                if author_id and author_id in authors:
                    authors[author_id].activities.append(
                        Activity(
                            source="openalex",
                            source_record_id=work.get("id"),
                            title=work_title,
                            summary=_work_summary(work),
                            activity_date=pub_date,
                            data=work_activity_data,
                        )
                    )

                for inst in authorship.get("institutions", []):
                    inst_id = inst.get("id", "")
                    if not inst_id:
                        continue

                    if inst_id not in institutions:
                        institutions[inst_id] = _build_institution_stakeholder(inst)

                    institutions[inst_id].activities.append(
                        Activity(
                            source="openalex",
                            source_record_id=work.get("id"),
                            title=work_title,
                            summary=f"{author_name} published via this institution",
                            activity_date=pub_date,
                            data=work_activity_data,
                        )
                    )

        all_stakeholders = list(authors.values()) + list(institutions.values())

        return SearchResult(
            source="openalex",
            query=query,
            stakeholders=all_stakeholders,
            total_records_scanned=len(works),
        )

    def _fetch_works(
        self,
        query: str,
        *,
        max_results: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict]:
        works_query = Works().search_filter(title_and_abstract=query)

        if date_from:
            works_query = works_query.filter(
                from_publication_date=date_from.isoformat()
            )
        if date_to:
            works_query = works_query.filter(to_publication_date=date_to.isoformat())

        results = []
        for page in works_query.paginate(
            per_page=min(200, max_results), n_max=max_results
        ):
            results.extend(page)

        # pyalex reconstructs abstracts via __getitem__
        for work in results:
            work["abstract"] = work["abstract"]

        return results


# --- Helper functions ---


def _build_author_stakeholder(author: dict) -> Stakeholder:
    external_ids = [
        ExternalId(type="openalex", value=author["id"]),
    ]
    if orcid := author.get("orcid"):
        external_ids.append(ExternalId(type="orcid", value=orcid))

    return Stakeholder(
        name=author.get("display_name", "Unknown"),
        entity_type=EntityType.INDIVIDUAL,
        sector=Sector.RESEARCH,
        external_ids=external_ids,
    )


def _build_institution_stakeholder(inst: dict) -> Stakeholder:
    external_ids = [
        ExternalId(type="openalex", value=inst["id"]),
    ]
    if ror := inst.get("ror"):
        external_ids.append(ExternalId(type="ror", value=ror))

    return Stakeholder(
        name=inst.get("display_name", "Unknown institution"),
        entity_type=EntityType.ORGANISATION,
        sector=Sector.RESEARCH,
        description=inst.get("type"),
        external_ids=external_ids,
    )


def _work_to_linked_data(work: dict) -> LinkedData:
    return LinkedData(
        type="work",
        content={
            "title": work.get("title"),
            "doi": work.get("doi"),
            "publication_year": work.get("publication_year"),
            "cited_by_count": work.get("cited_by_count"),
            "type": work.get("type"),
            "abstract": work.get("abstract"),
            "open_access": work.get("open_access", {}).get("is_oa"),
        },
    )


def _work_summary(work: dict) -> str:
    parts = []
    if year := work.get("publication_year"):
        parts.append(str(year))
    if wtype := work.get("type"):
        parts.append(wtype)
    if cites := work.get("cited_by_count"):
        parts.append(f"{cites} citations")
    return " · ".join(parts) if parts else ""


def _parse_date(date_str: str | None) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except ValueError:
        return None
