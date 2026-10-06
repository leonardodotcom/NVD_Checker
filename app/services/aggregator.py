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


def _absorb(base: Vulnerability, other: Vulnerability) -> None:
    """Fold `other` (same flaw reported by another source) into `base`."""
    for source in other.sources or [other.source]:
        if source not in base.sources:
            base.sources.append(source)
    for term in other.matched_keywords:
        if term not in base.matched_keywords:
            base.matched_keywords.append(term)
    for alias in [other.id, *other.aliases]:
        if alias.upper() != base.id.upper() and alias not in base.aliases:
            base.aliases.append(alias)
    for ref in other.references:
        if ref not in base.references:
            base.references.append(ref)
    for cwe in other.cwe:
        if cwe not in base.cwe:
            base.cwe.append(cwe)
    if not base.description:
        base.description = other.description
    if base.cvss_score is None and other.cvss_score is not None:
        base.cvss_score, base.cvss_version = other.cvss_score, other.cvss_version
    if base.severity == "UNKNOWN" and other.severity != "UNKNOWN":
        base.severity = other.severity
    if base.published is None:
        base.published = other.published


def merge_by_alias(entries: list[Vulnerability]) -> list[Vulnerability]:
    """Merge entries that share an identifier (e.g. NVD CVE-2026-1 + CNNVD entry citing CVE-2026-1).

    NVD entries go first so they stay the primary row (they carry CVSS and English text);
    the other sources are recorded in `sources` and their ids in `aliases`.
    """
    groups: list[Vulnerability] = []
    index: dict[str, int] = {}
    for entry in sorted(entries, key=lambda e: e.source != "nvd"):
        entry.sources = [entry.source]
        ids = {entry.id.upper(), *(a.upper() for a in entry.aliases)}
        hit = next((index[i] for i in ids if i in index), None)
        if hit is None:
            groups.append(entry)
            hit = len(groups) - 1
        else:
            _absorb(groups[hit], entry)
        for i in ids | {a.upper() for a in groups[hit].aliases}:
            index.setdefault(i, hit)
    return groups


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

    results = sorted(merge_by_alias(list(merged.values())), key=_sort_key)
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
