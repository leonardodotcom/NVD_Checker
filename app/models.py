from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE", "UNKNOWN"]
Window = Literal["24h", "7d", "30d", "90d", "180d", "365d", "custom"]
DateField = Literal["published", "modified"]


class Keyword(BaseModel):
    id: int
    term: str
    exact_match: bool = False


class KeywordIn(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    exact_match: bool = False


class Project(BaseModel):
    id: int
    name: str
    created_at: str
    keywords: list[Keyword] = []


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SearchKeyword(BaseModel):
    term: str
    exact_match: bool = False


class Vulnerability(BaseModel):
    id: str
    source: str
    description: str = ""
    published: datetime | None = None
    last_modified: datetime | None = None
    cvss_score: float | None = None
    cvss_version: str | None = None
    severity: Severity = "UNKNOWN"
    cwe: list[str] = []
    references: list[str] = []
    url: str | None = None
    matched_keywords: list[str] = []
    # Other identifiers for the same flaw (e.g. the CVE id cited by a CNNVD/CNVD entry)
    aliases: list[str] = []
    # Every database that reported this flaw (filled in by the aggregator when entries merge)
    sources: list[str] = []


class SearchRequest(BaseModel):
    project_id: int | None = None
    keywords: list[SearchKeyword] = []
    sources: list[str] = ["nvd"]
    window: Window = "7d"
    start: datetime | None = None
    end: datetime | None = None
    date_field: DateField = "published"


class SourceError(BaseModel):
    source: str
    keyword: str | None = None
    message: str


class SearchResponse(BaseModel):
    start: datetime
    end: datetime
    total: int
    results: list[Vulnerability]
    counts_by_keyword: dict[str, int]
    counts_by_severity: dict[str, int]
    errors: list[SourceError]


class SourceInfo(BaseModel):
    id: str
    name: str
    enabled: bool
    requires_auth: bool
    description: str = ""
    # "ready" | "login_required" | "session_expired" | "not_implemented"
    status: str = "ready"
    status_detail: str = ""
