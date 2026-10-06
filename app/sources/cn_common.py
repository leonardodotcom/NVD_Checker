"""Shared machinery for the Chinese databases (CNNVD, CNVD).

Both sites are human-oriented web UIs behind a login, so instead of one request
per trigger word we fetch *every* entry in the date window once, cache it, and
match all keywords locally. Adapters only implement `fetch_entries`.
"""

import asyncio
import random
import re
import time
from abc import abstractmethod
from datetime import datetime, timedelta, timezone

from ..config import get_settings
from ..models import DateField, SearchKeyword, Severity, Vulnerability
from . import cn_session
from .base import SessionExpired, Source, SourceError

BEIJING = timezone(timedelta(hours=8))
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
_CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")

# Chinese severity wording -> our scale. Confirm against real data in Phase 0.
_SEVERITY_WORDS = (
    ("超危", "CRITICAL"),
    ("严重", "CRITICAL"),
    ("高危", "HIGH"),
    ("中危", "MEDIUM"),
    ("低危", "LOW"),
    ("高", "HIGH"),
    ("中", "MEDIUM"),
    ("低", "LOW"),
)


def map_severity(text: str | None) -> Severity:
    """Map '超危/高危/中危/低危' (or '高/中/低') to CRITICAL/HIGH/MEDIUM/LOW."""
    if not text:
        return "UNKNOWN"
    t = text.strip()
    upper = t.upper()
    for word in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        if word in upper:
            return word  # type: ignore[return-value]
    for needle, level in _SEVERITY_WORDS:
        if needle in t:
            return level  # type: ignore[return-value]
    return "UNKNOWN"


def parse_cn_datetime(value: str | None) -> datetime | None:
    """Parse a date shown on a Chinese site (Beijing time unless it carries an offset) into UTC."""
    if not value:
        return None
    v = value.strip().replace("/", "-").replace("年", "-").replace("月", "-").replace("日", "")
    v = v.replace("Z", "+00:00")
    for candidate in (v, v.replace(" ", "T")):
        try:
            dt = datetime.fromisoformat(candidate.rstrip("-"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=BEIJING)
        return dt.astimezone(timezone.utc)
    return None


def extract_cves(*texts: str | None) -> list[str]:
    found: list[str] = []
    for text in texts:
        for m in CVE_RE.findall(text or ""):
            cve = m.upper()
            if cve not in found:
                found.append(cve)
    return found


def term_matches(entry: Vulnerability, keyword: SearchKeyword) -> bool:
    """Case-insensitive match over id, text and aliases.

    Chinese needs no tokenising, so CJK terms are a plain substring match. An
    "exact" Latin term must not sit inside a longer word (so 'ssl' won't match 'openssl').
    """
    term = keyword.term.strip().casefold()
    if not term:
        return False
    haystack = " ".join([entry.id, entry.description, *entry.aliases]).casefold()
    if keyword.exact_match and not _CJK_RE.search(term):
        return re.search(rf"(?<![0-9a-z]){re.escape(term)}(?![0-9a-z])", haystack) is not None
    return term in haystack


def _floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _in_window(entry: Vulnerability, start: datetime, end: datetime, date_field: DateField) -> bool:
    ts = entry.published if date_field == "published" else (entry.last_modified or entry.published)
    return ts is None or start <= ts <= end


class WindowSource(Source):
    """A login-gated source that lists everything in a date window.

    Subclasses set `id`, `name`, `site` (a key of cn_session.SITES), `implemented`,
    and implement `fetch_entries`.
    """

    requires_auth = True
    site: str
    implemented: bool = False

    def __init__(self, ttl: int | None = None, delay: float | None = None):
        settings = get_settings()
        self.ttl = ttl if ttl is not None else settings.cn_cache_ttl
        self.delay = delay if delay is not None else settings.cn_request_delay
        self._cache: dict[tuple, tuple[float, list[Vulnerability]]] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}

    # ----- status -----
    def status(self) -> tuple[str, str]:
        if not self.implemented:
            return "not_implemented", "Adapter not finished yet (waiting for site recordings)"
        return cn_session.describe(self.site)

    @property
    def enabled(self) -> bool:
        return self.status()[0] == "ready"

    # ----- fetching -----
    @abstractmethod
    async def fetch_entries(self, start: datetime, end: datetime, date_field: DateField) -> list[Vulnerability]:
        """Return every entry in [start, end] using the saved session.

        Must raise SessionExpired if the site shows a login page / captcha / 401 / 403,
        and should call `await self.pause()` between page requests.
        """

    async def pause(self) -> None:
        await asyncio.sleep(self.delay * random.uniform(0.7, 1.3))

    async def _window(self, start: datetime, end: datetime, date_field: DateField) -> list[Vulnerability]:
        # Quantise to whole hours so searches a few minutes apart share one fetch.
        qstart = _floor_hour(start)
        qend = _floor_hour(end) + timedelta(hours=1)
        key = (date_field, qstart, qend)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:  # single-flight: concurrent keyword searches share one fetch
            cached = self._cache.get(key)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            try:
                entries = await self.fetch_entries(qstart, qend, date_field)
            except SessionExpired:
                cn_session.mark_expired(self.site)
                raise
            self._cache[key] = (time.monotonic() + self.ttl, entries)
            return entries

    async def search(
        self, keyword: SearchKeyword, start: datetime, end: datetime, date_field: DateField
    ) -> list[Vulnerability]:
        if not self.implemented:
            raise SourceError(f"{self.name} adapter is not implemented yet")
        state = cn_session.load_state(self.site)
        if state is None:
            raise SessionExpired(f"No {self.name} login session. Run: python -m app.manage cn-login {self.site}")
        entries = await self._window(start, end, date_field)
        hits = []
        for entry in entries:
            if _in_window(entry, start, end, date_field) and term_matches(entry, keyword):
                copy = entry.model_copy(deep=True)
                copy.matched_keywords = [keyword.term]
                hits.append(copy)
        return hits
