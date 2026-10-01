"""NVD (NIST) CVE API 2.0 adapter.

Docs: https://nvd.nist.gov/developers/vulnerabilities
"""

import asyncio
import time
from collections import deque
from datetime import datetime, timedelta, timezone

import httpx

from ..config import get_settings
from ..models import DateField, SearchKeyword, Vulnerability
from .base import Source, SourceError

API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
MAX_RANGE = timedelta(days=120)  # NVD rejects date ranges longer than 120 days
PAGE_SIZE = 2000
RATE_WINDOW = 30.0  # seconds
RETRY_STATUSES = {403, 429, 500, 502, 503, 504}
MAX_RETRIES = 4


class RateLimiter:
    """Sliding-window limiter: at most `max_calls` per `period` seconds."""

    def __init__(self, max_calls: int, period: float):
        self.max_calls = max_calls
        self.period = period
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self.period:
                    self._calls.popleft()
                if len(self._calls) < self.max_calls:
                    self._calls.append(now)
                    return
                await asyncio.sleep(self.period - (now - self._calls[0]) + 0.05)


def split_range(start: datetime, end: datetime, max_range: timedelta = MAX_RANGE):
    """Split [start, end] into consecutive chunks no longer than `max_range`."""
    chunks = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + max_range, end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _pick_metric(metrics: dict) -> tuple[float | None, str | None, str]:
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV40", "cvssMetricV2"):
        entries = metrics.get(key) or []
        if not entries:
            continue
        entry = next((e for e in entries if e.get("type") == "Primary"), entries[0])
        data = entry.get("cvssData", {})
        severity = data.get("baseSeverity") or entry.get("baseSeverity") or "UNKNOWN"
        return data.get("baseScore"), data.get("version"), severity.upper()
    return None, None, "UNKNOWN"


def parse_cve(item: dict, term: str) -> Vulnerability:
    cve = item["cve"]
    description = next(
        (d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"), ""
    )
    score, version, severity = _pick_metric(cve.get("metrics", {}))
    cwes = sorted(
        {
            d["value"]
            for w in cve.get("weaknesses", [])
            for d in w.get("description", [])
            if d.get("value", "").startswith("CWE-")
        }
    )
    return Vulnerability(
        id=cve["id"],
        source="nvd",
        description=description,
        published=_parse_dt(cve.get("published")),
        last_modified=_parse_dt(cve.get("lastModified")),
        cvss_score=score,
        cvss_version=version,
        severity=severity,
        cwe=cwes,
        references=[r["url"] for r in cve.get("references", []) if r.get("url")],
        url=f"https://nvd.nist.gov/vuln/detail/{cve['id']}",
        matched_keywords=[term],
    )


class NVDSource(Source):
    id = "nvd"
    name = "NVD (NIST)"
    description = "U.S. National Vulnerability Database — CVE API 2.0"

    def __init__(self, api_key: str | None = None, cache_ttl: int | None = None):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.nvd_api_key
        self.cache_ttl = cache_ttl if cache_ttl is not None else settings.cache_ttl
        self.limiter = RateLimiter(50 if self.api_key else 5, RATE_WINDOW)
        self._cache: dict[tuple, tuple[float, list[Vulnerability]]] = {}

    async def search(
        self, keyword: SearchKeyword, start: datetime, end: datetime, date_field: DateField
    ) -> list[Vulnerability]:
        key = (keyword.term.lower(), keyword.exact_match, date_field, start, end)
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return [v.model_copy(deep=True) for v in cached[1]]

        prefix = "pub" if date_field == "published" else "lastMod"
        results: dict[str, Vulnerability] = {}
        headers = {"apiKey": self.api_key} if self.api_key else {}
        async with httpx.AsyncClient(timeout=60, headers=headers) as client:
            for chunk_start, chunk_end in split_range(start, end):
                params = {
                    "keywordSearch": keyword.term,
                    f"{prefix}StartDate": _fmt(chunk_start),
                    f"{prefix}EndDate": _fmt(chunk_end),
                    "resultsPerPage": PAGE_SIZE,
                }
                if keyword.exact_match:
                    params["keywordExactMatch"] = ""
                start_index = 0
                while True:
                    data = await self._get(client, {**params, "startIndex": start_index})
                    for item in data.get("vulnerabilities", []):
                        vuln = parse_cve(item, keyword.term)
                        results[vuln.id] = vuln
                    start_index += data.get("resultsPerPage", 0)
                    if not data.get("resultsPerPage") or start_index >= data.get("totalResults", 0):
                        break

        found = list(results.values())
        self._cache[key] = (time.monotonic() + self.cache_ttl, found)
        return [v.model_copy(deep=True) for v in found]

    async def _get(self, client: httpx.AsyncClient, params: dict) -> dict:
        last_error = ""
        for attempt in range(MAX_RETRIES):
            await self.limiter.acquire()
            try:
                resp = await client.get(API_URL, params=params)
            except httpx.HTTPError as exc:
                last_error = f"network error: {exc}"
            else:
                if resp.status_code == 200:
                    return resp.json()
                message = resp.headers.get("message") or resp.text[:200]
                last_error = f"HTTP {resp.status_code}: {message}"
                if resp.status_code not in RETRY_STATUSES:
                    break
            await asyncio.sleep(2**attempt)
        raise SourceError(last_error)
