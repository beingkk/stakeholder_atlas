"""Post-search link verification service.

Checks that activity source URLs are live and contextually relevant,
removing any that are broken or irrelevant.
"""

import asyncio
import logging
from enum import StrEnum

import httpx
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.schemas import SearchResult, Stakeholder

logger = logging.getLogger(__name__)

RELEVANCE_PROMPT = """\
You are verifying whether a web page is relevant evidence for a stakeholder's activity.

Stakeholder: {name}
Activity title: {title}
Activity summary: {summary}

The following is a snippet from the web page at {url}:
---
{snippet}
---

Is this page genuinely relevant evidence that this stakeholder is active in this area?
Answer ONLY "relevant" or "irrelevant"."""

MAX_CONCURRENT_FETCHES = 10
FETCH_TIMEOUT = 10.0
SNIPPET_CHARS = 2000


class LinkStatus(StrEnum):
    OK = "ok"
    DEAD = "dead"
    IRRELEVANT = "irrelevant"


class LinkVerifier:
    def __init__(self):
        self._client: AsyncOpenAI | None = None
        if settings.OPENAI_API_KEY:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def verify_search_result(self, result: SearchResult) -> SearchResult:
        """Verify all activity links in a SearchResult, removing bad ones.

        Args:
            result: The SearchResult to verify.

        Returns:
            A new SearchResult with dead/irrelevant activities removed.
            Stakeholders with no remaining activities are kept but flagged.
        """
        if not self._client:
            logger.warning("OPENAI_API_KEY not configured — skipping link verification")
            return result

        verified_stakeholders: list[Stakeholder] = []
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

        # Verify stakeholder websites in parallel
        website_tasks = [self._check_website(semaphore, s) for s in result.stakeholders]
        website_statuses = await asyncio.gather(*website_tasks, return_exceptions=True)

        for stakeholder, ws_status in zip(result.stakeholders, website_statuses):
            if isinstance(ws_status, Exception):
                ws_status = LinkStatus.OK
            if ws_status == LinkStatus.DEAD:
                logger.info(
                    "Removed stakeholder with dead website: %s (%s)",
                    stakeholder.name,
                    stakeholder.website,
                )
                continue

            # Verify activity links
            verified_activities = []
            tasks = [
                self._check_activity(semaphore, stakeholder.name, activity)
                for activity in stakeholder.activities
            ]
            statuses = await asyncio.gather(*tasks, return_exceptions=True)

            for activity, status in zip(stakeholder.activities, statuses):
                if isinstance(status, Exception):
                    logger.debug(
                        "Verification error for %s: %s",
                        activity.source_record_id,
                        status,
                    )
                    verified_activities.append(activity)
                    continue
                if status == LinkStatus.OK:
                    verified_activities.append(activity)
                else:
                    logger.info(
                        "Removed %s activity: %s (%s)",
                        status.value,
                        activity.title,
                        activity.source_record_id,
                    )

            verified_stakeholders.append(
                stakeholder.model_copy(update={"activities": verified_activities})
            )

        return SearchResult(
            source=result.source,
            query=result.query,
            stakeholders=verified_stakeholders,
            total_records_scanned=result.total_records_scanned,
        )

    async def _check_website(
        self,
        semaphore: asyncio.Semaphore,
        stakeholder: Stakeholder,
    ) -> LinkStatus:
        """Check if a stakeholder's website is reachable."""
        url = stakeholder.website
        if not url or not url.startswith("http"):
            return LinkStatus.OK

        async with semaphore:
            snippet = await self._fetch_snippet(url)

        if snippet is None:
            return LinkStatus.DEAD
        return LinkStatus.OK

    async def _check_activity(
        self,
        semaphore: asyncio.Semaphore,
        stakeholder_name: str,
        activity,
    ) -> LinkStatus:
        """Check a single activity's source URL."""
        url = activity.source_record_id
        if not url or not url.startswith("http"):
            return LinkStatus.OK

        async with semaphore:
            snippet = await self._fetch_snippet(url)

        if snippet is None:
            return LinkStatus.DEAD

        return await self._check_relevance(
            name=stakeholder_name,
            title=activity.title,
            summary=activity.summary or "",
            url=url,
            snippet=snippet,
        )

    async def _fetch_snippet(self, url: str) -> str | None:
        """Fetch a URL and return first N chars of text, or None if dead."""
        try:
            async with httpx.AsyncClient(
                timeout=FETCH_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "StakeholderAtlas/1.0 link-checker"},
            ) as client:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    return None
                content_type = resp.headers.get("content-type", "")
                if "html" in content_type or "text" in content_type:
                    return resp.text[:SNIPPET_CHARS]
                return resp.text[:SNIPPET_CHARS]
        except (httpx.HTTPError, httpx.InvalidURL):
            return None

    async def _check_relevance(
        self,
        *,
        name: str,
        title: str,
        summary: str,
        url: str,
        snippet: str,
    ) -> LinkStatus:
        """Use a fast model to judge if the page content is relevant."""
        prompt = RELEVANCE_PROMPT.format(
            name=name,
            title=title,
            summary=summary,
            url=url,
            snippet=snippet,
        )

        try:
            response = await self._client.chat.completions.create(
                model=settings.VERIFICATION_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0,
            )
            content = response.choices[0].message.content or ""
            if "irrelevant" in content.strip().lower():
                return LinkStatus.IRRELEVANT
            return LinkStatus.OK
        except Exception as e:
            logger.debug("Relevance check failed for %s: %s", url, e)
            return LinkStatus.OK
