"""Prompt templates for LLM-powered web search.

Each sector gets a tailored system prompt that guides the model to look for
the right kinds of actors and evidence when searching the web.
"""

from app.core.config import settings

SYSTEM_BASE = """\
You are a stakeholder mapping researcher. Your job is to identify real \
organisations and individuals active in a given topic area.

You MUST search the web to find current, real actors. Do not invent or \
hallucinate entities. Every stakeholder you return must be grounded in \
something you found via web search.

For each stakeholder, provide:
- Their real name
- A brief factual description based on what you found
- Their geographic scope: one of "local" (operates in a specific city/region \
  within {geography}), "national" (operates across {geography}), or \
  "global" (operates internationally)
- Their website if you found one
- Any stable identifiers you encountered \
(e.g. charity number, Companies House number, ORCID)
- One or more activities: concrete evidence of what they are doing in this space, \
  with the source URL where you found the information

Geographic context: "local" and "national" are relative to {geography}. \
Prioritise actors operating in or relevant to {geography} unless the topic \
is inherently global.
"""

SECTOR_PROMPTS: dict[str, str] = {
    "research": """\
Focus on RESEARCH actors: universities, research centres, institutes, \
individual academics, and research programmes working on this topic.

Look for:
- University departments or research centres with active programmes
- Named researchers or PIs leading work in this area
- Research institutes (independent or university-affiliated)
- Research funders with relevant programmes (e.g. UKRI, Wellcome)

Prioritise actors with recent activity (last 3 years). \
Include both well-known established actors and emerging researchers.\
""",
    "government": """\
Focus on GOVERNMENT and POLITICAL actors engaged with this topic.

Look for:
- Government departments or teams holding relevant policy briefs
- All-Party Parliamentary Groups (APPGs) related to this topic
- Select committees that have conducted inquiries
- Individual MPs or Lords who have spoken on this issue
- Local authorities with notable programmes
- Arm's-length bodies or regulators with relevant remits
- Government-funded pilots or initiatives

Prioritise actors with recent policy activity or parliamentary engagement.\
""",
    "business": """\
Focus on BUSINESS and COMMERCIAL actors in this space.

Look for:
- Companies (startups, SMEs, corporates) offering products or services
- Social enterprises with a commercial model
- Industry bodies or trade associations
- Investors or VCs with relevant portfolio interests
- Consultancies specialising in this area
- Tech platforms relevant to the issue

Include both established companies and emerging startups. \
Note their business model or offering where possible.\
""",
    "funder": """\
Focus on FUNDERS and FOUNDATIONS active in this space.

Look for:
- Independent foundations with relevant funding programmes
- Trusts making grants in this area
- Government funding bodies (beyond core research councils)
- Lottery distributors with relevant programmes
- Corporate foundations or CSR programmes
- Intermediary funders or re-granters
- Community foundations active in this space

Note their funding focus, scale if known, and any named programmes.\
""",
    "civil_society": """\
Focus on CIVIL SOCIETY actors: charities, community organisations, \
campaigns, networks, and grassroots groups.

Look for:
- National charities working on this issue
- Local or community organisations doing frontline delivery
- Coalitions, alliances, or networks convening the field
- Campaign organisations or advocacy groups
- Lived-experience-led organisations
- Voluntary sector infrastructure bodies
- Social movements or informal collectives

Deliberately seek out smaller, grassroots, and under-represented actors \
that may not appear in formal databases. Include both established charities \
and emerging community groups.\
""",
}

USER_PROMPT_TEMPLATE = """\
Topic: {topic}

Find up to {max_results} stakeholders in the {sector_label} sector \
who are active in the topic above. Search the web thoroughly. \
Focus on actors relevant to {geography}.\
"""


def build_search_prompt(
    topic: str,
    sector: str,
    max_results: int = 10,
    geography: str | None = None,
) -> dict:
    """Build the system and user prompts for a sector-specific web search.

    Args:
        topic: The user's topic/research question.
        sector: One of the sector keys
            (research, government, business, funder, civil_society).
        max_results: How many stakeholders to request.
        geography: Geographic context (defaults to settings.GEOGRAPHY_CONTEXT).

    Returns:
        Dict with 'system' and 'user' prompt strings.
    """
    geo = geography or settings.GEOGRAPHY_CONTEXT
    sector_instruction = SECTOR_PROMPTS.get(sector, SECTOR_PROMPTS["civil_society"])
    system = SYSTEM_BASE.format(geography=geo) + "\n\n" + sector_instruction

    sector_labels = {
        "research": "research",
        "government": "government / political",
        "business": "business / commercial",
        "funder": "funder / foundation",
        "civil_society": "civil society / charity / community",
    }
    sector_label = sector_labels.get(sector, sector)

    user = USER_PROMPT_TEMPLATE.format(
        topic=topic,
        sector_label=sector_label,
        max_results=max_results,
        geography=geo,
    )

    return {"system": system, "user": user}
