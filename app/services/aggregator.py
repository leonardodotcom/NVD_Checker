import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone

from ..models import SearchKeyword, SearchRequest, SearchResponse, SourceError as SourceErrorModel, Vulnerability
from ..sources.base import Source, SourceError

WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "180d": timedelta(days=180),
    "365d": timedelta(days=365),
}
MAX_CUSTOM_RANGE = timedelta(days=3 * 365)
SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "NONE": 4, "UNKNOWN": 5}


def resolve_window(req: SearchRequest, now: datetime | None = None) -> tuple[datetime, datetime]:
    if req.window == "custom":
        if not req.start:
            raise ValueError("A custom window requires a start date")
        start = req.start if req.start.tzinfo else req.start.replace(tzinfo=timezone.utc)
        end = req.end or datetime.now(timezone.utc)
        end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        if start >= end:
            raise ValueError("Start date must be before end date")
        if end - start > MAX_CUSTOM_RANGE:
            raise ValueError("Custom range cannot exceed 3 years")
        return start, end
    # Floor to the minute so repeated searches hit the adapter cache.
    end = (now or datetime.now(timezone.utc)).replace(second=0, microsecond=0)
    return end - WINDOWS[req.window], end


def _sort_key(v: Vulnerability):
    ts = v.published.timestamp() if v.published else 0
    return (-ts, SEVERITY_RANK.get(v.severity, 9), v.id)


async def aggregate(
    sources: list[Source],
    keywords: list[SearchKeyword],
    start: datetime,
    end: datetime,
    date_field: str,
) -> SearchResponse:
    jobs = [(s, k) for s in sources for k in keywords]
    outcomes = await asyncio.gather(
        *(s.search(k, start, end, date_field) for s, k in jobs), return_exceptions=True
    )

    merged: dict[tuple[str, str], Vulnerability] = {}
    errors: list[SourceErrorModel] = []
    for (source, keyword), outcome in zip(jobs, outcomes):
        if isinstance(outcome, BaseException):
            message = str(outcome) if isinstance(outcome, SourceError) else f"{type(outcome).__name__}: {outcome}"
            errors.append(SourceErrorModel(source=source.id, keyword=keyword.term, message=message))
            continue
        for vuln in outcome:
            key = (vuln.source, vuln.id)
            if key in merged:
                existing = merged[key]
                for term in vuln.matched_keywords:
                    if term not in existing.matched_keywords:
                        existing.matched_keywords.append(term)
            else:
                merged[key] = vuln

    results = sorted(merged.values(), key=_sort_key)
    by_keyword = Counter({k.term: 0 for k in keywords})
    for v in results:
        by_keyword.update(v.matched_keywords)
    by_severity = Counter(v.severity for v in results)

    return SearchResponse(
        start=start,
        end=end,
        total=len(results),
        results=results,
        counts_by_keyword=dict(by_keyword),
        counts_by_severity={s: by_severity.get(s, 0) for s in SEVERITY_RANK},
        errors=errors,
    )
