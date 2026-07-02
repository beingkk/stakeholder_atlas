"""Enrich service: web-search each stakeholder name to build full profiles.

Accepts free-form text input (any format), uses a cheap LLM call to extract
stakeholder names, then enriches each via web search.
"""

import asyncio
import logging

from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.schemas import (
    Activity,
    EntityType,
    GeographicScope,
    LinkedData,
    SearchResult,
    Sector,
    Stakeholder,
)

logger = logging.getLogger(__name__)

PARSE_SYSTEM = """\
Extract stakeholder names from the user's input. The input may be a list, \
a paragraph, a table, comma-separated, or any other format.

Return a JSON array of strings — just the names/organisations, cleaned up. \
Remove numbering, bullets, descriptions, or other annotations. \
If the input contains context clues about what these stakeholders are, \
ignore that for the list but it will be used separately as context."""

ENRICH_SYSTEM = """\
You are a research assistant. Given an organisation or person name (and optional \
context), search the web for factual information about them.

Return structured data:
- entity_type: one of "individual", "organisation", "network", "other"
- sector: one of "research", "government", "business", \
"funder", "civil_society", "other"
- geographic_scope: one of "local", "national", "global" (relative to {geography})
- description: 1-2 sentence factual description
- website: their official website URL if found
- activities: concrete evidence of what they do, with source URLs

Only return facts you can verify via web search. If you cannot find information, \
return minimal data with entity_type "other"."""

ENRICH_USER = "Find information about: {name}\nContext: {context}"

BATCH_SIZE = 5


class ActivityOut(BaseModel):
    title: str
    summary: str | None = None
    source_url: str | None = None


class EnrichOutput(BaseModel):
    entity_type: str = "other"
    sector: str = "other"
    geographic_scope: str = "national"
    description: str | None = None
    website: str | None = None
    activities: list[ActivityOut] = Field(default_factory=list)


class ParsedNames(BaseModel):
    names: list[str]


class EnrichService:
    def __init__(self):
        self._llm: ChatOpenAI | None = None
        self._openai: AsyncOpenAI | None = None
        if settings.OPENAI_API_KEY:
            self._llm = ChatOpenAI(
                model=settings.VERIFICATION_MODEL,
                api_key=settings.OPENAI_API_KEY,
                use_responses_api=True,
            )
            self._openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    def _ensure_llm(self) -> ChatOpenAI:
        if self._llm is None:
            raise RuntimeError(
                "EnrichService unavailable: OPENAI_API_KEY not configured"
            )
        return self._llm

    async def parse_input(self, raw_text: str) -> list[str]:
        """Extract stakeholder names from free-form text using a cheap LLM call.

        Args:
            raw_text: Any user input — lists, paragraphs, tables, etc.

        Returns:
            Cleaned list of stakeholder name strings.
        """
        if not self._openai:
            raise RuntimeError("OPENAI_API_KEY not configured")

        response = await self._openai.responses.parse(
            model=settings.VERIFICATION_MODEL,
            instructions=PARSE_SYSTEM,
            input=raw_text,
            text_format=ParsedNames,
        )
        return response.output_parsed.names

    async def enrich_from_text(
        self,
        raw_text: str,
        context: str = "",
    ) -> SearchResult:
        """Parse free-form text into names, then enrich each via web search.

        Args:
            raw_text: Any format user input containing stakeholder names.
            context: Optional topic/project context to guide the search.

        Returns:
            SearchResult with source="manual_upload".
        """
        names = await self.parse_input(raw_text)
        logger.info("Parsed %d stakeholder names from input", len(names))
        return await self.enrich_names(names, context=context)

    async def enrich_names(
        self,
        names: list[str],
        context: str = "",
    ) -> SearchResult:
        """Web-search each name and return enriched stakeholder profiles.

        Args:
            names: List of stakeholder names to research.
            context: Optional topic/project context to guide the search.

        Returns:
            SearchResult with source="manual_upload".
        """
        llm = self._ensure_llm()
        structured_llm = llm.bind_tools(
            [{"type": "web_search"}],
            tool_choice="required",
        ).with_structured_output(EnrichOutput)

        geography = settings.GEOGRAPHY_CONTEXT
        system = ENRICH_SYSTEM.format(geography=geography)

        async def _enrich_one(name: str) -> Stakeholder | None:
            try:
                user_msg = ENRICH_USER.format(name=name, context=context or "general")
                result = await structured_llm.ainvoke(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ]
                )
                return self._to_stakeholder(name, result)
            except Exception as e:
                logger.warning("Failed to enrich '%s': %s", name, e)
                return Stakeholder(
                    name=name,
                    entity_type=EntityType.OTHER,
                    sector=Sector.OTHER,
                )

        stakeholders: list[Stakeholder] = []
        for i in range(0, len(names), BATCH_SIZE):
            batch = names[i : i + BATCH_SIZE]
            results = await asyncio.gather(*[_enrich_one(n) for n in batch])
            stakeholders.extend([s for s in results if s])

        return SearchResult(
            source="manual_upload",
            query=f"Upload: {len(names)} names",
            stakeholders=stakeholders,
            total_records_scanned=len(names),
        )

    def _to_stakeholder(self, name: str, output: EnrichOutput) -> Stakeholder:
        entity_map = {
            "individual": EntityType.INDIVIDUAL,
            "organisation": EntityType.ORGANISATION,
            "network": EntityType.NETWORK,
        }
        sector_map = {
            "research": Sector.RESEARCH,
            "government": Sector.GOVERNMENT,
            "business": Sector.BUSINESS,
            "funder": Sector.FUNDER,
            "civil_society": Sector.CIVIL_SOCIETY,
        }
        geo_map = {
            "local": GeographicScope.LOCAL,
            "national": GeographicScope.NATIONAL,
            "global": GeographicScope.GLOBAL,
        }

        activities = [
            Activity(
                source="manual_upload",
                source_record_id=a.source_url,
                title=a.title,
                summary=a.summary,
                data=LinkedData(
                    type="web_reference",
                    content={"url": a.source_url},
                )
                if a.source_url
                else None,
            )
            for a in output.activities
        ]

        return Stakeholder(
            name=name,
            entity_type=entity_map.get(output.entity_type, EntityType.OTHER),
            sector=sector_map.get(output.sector, Sector.OTHER),
            geographic_scope=geo_map.get(
                output.geographic_scope, GeographicScope.NATIONAL
            ),
            description=output.description,
            website=output.website,
            activities=activities,
        )
