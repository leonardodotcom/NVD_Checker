import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.models import SearchKeyword, SearchRequest, Vulnerability
from app.services.aggregator import aggregate, resolve_window
from app.sources.base import Source, SourceError

UTC = timezone.utc


class FakeSource(Source):
    id = "fake"
    name = "Fake"

    def __init__(self, data):
        self.data = data

    async def search(self, keyword, start, end, date_field):
        result = self.data[keyword.term]
        if isinstance(result, Exception):
            raise result
        return [Vulnerability(**v, source="fake", matched_keywords=[keyword.term]) for v in result]


def ts(day):
    return datetime(2026, 9, day, tzinfo=UTC)


def test_aggregate_dedupes_merges_sorts_and_reports_errors():
    src = FakeSource({
        "openssl": [{"id": "CVE-1", "published": ts(1), "severity": "LOW"},
                    {"id": "CVE-2", "published": ts(5), "severity": "HIGH"}],
        "rce": [{"id": "CVE-2", "published": ts(5), "severity": "HIGH"},
                {"id": "CVE-3", "published": ts(5), "severity": "CRITICAL"}],
        "broken": SourceError("HTTP 503: down"),
    })
    kws = [SearchKeyword(term=t) for t in ("openssl", "rce", "broken")]
    resp = asyncio.run(aggregate([src], kws, ts(1), ts(10), "published"))

    assert [v.id for v in resp.results] == ["CVE-3", "CVE-2", "CVE-1"]
    assert resp.results[1].matched_keywords == ["openssl", "rce"]
    assert resp.counts_by_keyword == {"openssl": 2, "rce": 2, "broken": 0}
    assert resp.counts_by_severity["CRITICAL"] == 1 and resp.counts_by_severity["HIGH"] == 1
    assert resp.total == 3
    assert len(resp.errors) == 1 and resp.errors[0].keyword == "broken"


def test_resolve_window_presets_and_custom():
    now = datetime(2026, 10, 1, 12, 30, 45, tzinfo=UTC)
    start, end = resolve_window(SearchRequest(window="30d"), now)
    assert end == now.replace(second=0) and end - start == timedelta(days=30)

    req = SearchRequest(window="custom", start=datetime(2026, 1, 1), end=datetime(2026, 2, 1))
    start, end = resolve_window(req)
    assert start.tzinfo is not None and (end - start).days == 31

    with pytest.raises(ValueError):
        resolve_window(SearchRequest(window="custom"))
    with pytest.raises(ValueError):
        resolve_window(SearchRequest(window="custom", start=ts(5), end=ts(1)))
