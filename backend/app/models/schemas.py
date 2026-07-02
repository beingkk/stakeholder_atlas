"""Core domain models for Stakeholder Atlas.

These schemas are source-agnostic: any data source (OpenAlex, 360Giving, etc.)
produces Stakeholder + Activity objects using the same shapes.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class EntityType(StrEnum):
    INDIVIDUAL = "individual"
    ORGANISATION = "organisation"
    NETWORK = "network"
    OTHER = "other"


class Sector(StrEnum):
    RESEARCH = "research"
    GOVERNMENT = "government"
    BUSINESS = "business"
    FUNDER = "funder"
    CIVIL_SOCIETY = "civil_society"
    OTHER = "other"


class GeographicScope(StrEnum):
    LOCAL = "local"
    NATIONAL = "national"
    GLOBAL = "global"


class LinkedData(BaseModel):
    """A piece of structured data attached to an activity.

    The `type` field describes what kind of data this is (e.g. "work",
    "grant", "policy_document"). The `content` dict holds source-specific
    fields — its shape depends on type.
    """

    type: str
    content: dict


class Activity(BaseModel):
    """A piece of evidence about what a stakeholder is doing.

    Each activity traces back to a source record and carries a confidence tier.
    """

    source: str
    source_record_id: str | None = None
    title: str
    summary: str | None = None
    activity_date: date | None = None
    data: LinkedData | None = None


class ExternalId(BaseModel):
    """A stable external identifier for entity resolution."""

    type: str = Field(description="e.g. 'orcid', 'ror', 'openalex'")
    value: str


class Stakeholder(BaseModel):
    """A resolved entity — person, org, network etc. — assembled from evidence."""

    name: str
    entity_type: EntityType
    sector: Sector
    geographic_scope: GeographicScope | None = None
    description: str | None = None
    website: str | None = None
    external_ids: list[ExternalId] = Field(default_factory=list)
    activities: list[Activity] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Response from a source search — a collection of stakeholders with metadata."""

    source: str
    query: str
    stakeholders: list[Stakeholder]
    total_records_scanned: int = 0
