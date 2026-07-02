"""LLM-powered web search service for stakeholder discovery.

Uses LangChain's ChatOpenAI with the Responses API web_search tool
to find stakeholders across different sectors, returning structured
output via Pydantic models.
"""

import asyncio
import logging
import warnings

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.schemas import (
    Activity,
    EntityType,
    ExternalId,
    GeographicScope,
    LinkedData,
    SearchResult,
    Sector,
    Stakeholder,
)
from app.services.prompts import build_search_prompt

warnings.filterwarnings(
    "ignore",
    message="Pydantic serializer warnings",
    category=UserWarning,
    module="pydantic",
)

logger = logging.getLogger(__name__)


# --- Pydantic models for structured LLM output ---


class ActivityOutput(BaseModel):
    title: str = Field(description="Short title of the activity or evidence")
    summary: str | None = Field(
        default=None, description="Brief description of what was found"
    )
    source_url: str | None = Field(
        default=None, description="URL where this information was found"
    )
    date_info: str | None = Field(
        default=None, description="Date or date range of the activity"
    )


class ExternalIdOutput(BaseModel):
    type: str = Field(description="Identifier type, e.g. charity_number, orcid, ror")
    value: str = Field(description="The identifier value")


class StakeholderOutput(BaseModel):
    name: str = Field(description="Full name of the stakeholder")
    entity_type: str = Field(
        description="One of: individual, organisation, network, other"
    )
    geographic_scope: str = Field(description="One of: local, national, global")
    description: str = Field(
        description="Brief factual description based on web evidence"
    )
    website: str | None = Field(default=None, description="Website URL if found")
    external_ids: list[ExternalIdOutput] = Field(
        default_factory=list,
        description="Stable identifiers found (charity number, Companies House, etc.)",
    )
    activities: list[ActivityOutput] = Field(
        default_factory=list,
        description="Evidence of what they are doing in this space",
    )


class StakeholderSearchOutput(BaseModel):
    """Structured output from web search for stakeholders."""

    stakeholders: list[StakeholderOutput] = Field(
        description="List of stakeholders found via web search"
    )


# --- Service ---


class WebSearchService:
    def __init__(self):
        self._llm: ChatOpenAI | None = None
        if settings.OPENAI_API_KEY:
            self._llm = ChatOpenAI(
                model=settings.WEB_SEARCH_MODEL,
                api_key=settings.OPENAI_API_KEY,
                use_responses_api=True,
            )
        else:
            logger.warning("OPENAI_API_KEY not configured — web search disabled")

    def _ensure_llm(self) -> ChatOpenAI:
        if self._llm is None:
            raise RuntimeError(
                "Web search service unavailable: OPENAI_API_KEY not configured"
            )
        return self._llm

    async def search_stakeholders(
        self,
        topic: str,
        *,
        sector: str = "civil_society",
        max_results: int = 10,
    ) -> SearchResult:
        """Search the web for stakeholders in a given sector.

        Args:
            topic: The topic or research question to search for.
            sector: Which sector to focus on (research, government,
                    business, funder, civil_society).
            max_results: How many stakeholders to request from the model.

        Returns:
            SearchResult with stakeholders assembled from web evidence.
        """
        llm = self._ensure_llm()
        prompts = build_search_prompt(topic, sector, max_results=max_results)

        structured_llm = llm.bind_tools(
            [{"type": "web_search"}],
            tool_choice="required",
        ).with_structured_output(StakeholderSearchOutput)

        result = await structured_llm.ainvoke(
            [
                {"role": "system", "content": prompts["system"]},
                {"role": "user", "content": prompts["user"]},
            ]
        )

        return self._to_search_result(result, topic=topic, sector=sector)

    async def search_all_sectors(
        self,
        topic: str,
        *,
        max_results_per_sector: int = 8,
    ) -> SearchResult:
        """Run web search across all sectors and combine results.

        Args:
            topic: The topic or research question.
            max_results_per_sector: How many stakeholders per sector.

        Returns:
            Combined SearchResult from all sector searches.
        """
        sectors = ["research", "government", "business", "funder", "civil_society"]
        tasks = [
            self.search_stakeholders(
                topic, sector=s, max_results=max_results_per_sector
            )
            for s in sectors
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_stakeholders: list[Stakeholder] = []
        total_scanned = 0

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Web search for sector %s failed: %s", sectors[i], result)
                continue
            all_stakeholders.extend(result.stakeholders)
            total_scanned += result.total_records_scanned

        return SearchResult(
            source="web_search",
            query=topic,
            stakeholders=all_stakeholders,
            total_records_scanned=total_scanned,
        )

    def _to_search_result(
        self,
        output: StakeholderSearchOutput,
        *,
        topic: str,
        sector: str,
    ) -> SearchResult:
        """Convert LLM structured output into our domain models."""
        sector_enum = _map_sector(sector)
        stakeholders: list[Stakeholder] = []

        for raw in output.stakeholders:
            activities = [
                Activity(
                    source="web_search",
                    source_record_id=act.source_url,
                    title=act.title,
                    summary=act.summary,
                    data=LinkedData(
                        type="web_reference",
                        content={
                            "url": act.source_url,
                            "date_info": act.date_info,
                        },
                    ),
                )
                for act in raw.activities
            ]

            external_ids = [
                ExternalId(type=eid.type, value=eid.value) for eid in raw.external_ids
            ]

            stakeholder = Stakeholder(
                name=raw.name,
                entity_type=_map_entity_type(raw.entity_type),
                sector=sector_enum,
                geographic_scope=_map_geographic_scope(raw.geographic_scope),
                description=raw.description,
                website=raw.website,
                external_ids=external_ids,
                activities=activities,
            )
            stakeholders.append(stakeholder)

        return SearchResult(
            source="web_search",
            query=topic,
            stakeholders=stakeholders,
            total_records_scanned=len(stakeholders),
        )


def _map_sector(sector: str) -> Sector:
    mapping = {
        "research": Sector.RESEARCH,
        "government": Sector.GOVERNMENT,
        "business": Sector.BUSINESS,
        "funder": Sector.FUNDER,
        "civil_society": Sector.CIVIL_SOCIETY,
    }
    return mapping.get(sector, Sector.OTHER)


def _map_entity_type(raw: str) -> EntityType:
    mapping = {
        "individual": EntityType.INDIVIDUAL,
        "organisation": EntityType.ORGANISATION,
        "network": EntityType.NETWORK,
        "other": EntityType.OTHER,
    }
    return mapping.get(raw, EntityType.OTHER)


def _map_geographic_scope(raw: str) -> GeographicScope:
    mapping = {
        "local": GeographicScope.LOCAL,
        "national": GeographicScope.NATIONAL,
        "global": GeographicScope.GLOBAL,
    }
    return mapping.get(raw, GeographicScope.NATIONAL)
