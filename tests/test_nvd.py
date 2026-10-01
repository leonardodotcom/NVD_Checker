import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import respx

from app.models import SearchKeyword
from app.sources.nvd import API_URL, NVDSource, parse_cve, split_range

from .fixtures import cve, page

UTC = timezone.utc


def test_split_range_respects_120_day_limit():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=365)
    chunks = split_range(start, end)
    assert len(chunks) == 4
    assert chunks[0][0] == start and chunks[-1][1] == end
    assert all(b - a <= timedelta(days=120) for a, b in chunks)
    assert all(chunks[i][1] == chunks[i + 1][0] for i in range(len(chunks) - 1))


def test_split_range_short_window_is_single_chunk():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    assert split_range(start, start + timedelta(days=7)) == [(start, start + timedelta(days=7))]


def test_parse_cve_picks_primary_metric_english_and_cwe():
    v = parse_cve(cve("CVE-2026-0001", desc="Heap overflow"), "openssl")
    assert v.id == "CVE-2026-0001"
    assert v.description == "Heap overflow"
    assert v.cvss_score == 9.8 and v.severity == "CRITICAL" and v.cvss_version == "3.1"
    assert v.cwe == ["CWE-79"]
    assert v.published == datetime(2026, 9, 28, 10, tzinfo=UTC)
    assert v.matched_keywords == ["openssl"]
    assert v.url.endswith("CVE-2026-0001")


def test_parse_cve_falls_back_to_v2_and_unknown():
    item = cve("CVE-1")
    item["cve"]["metrics"] = {"cvssMetricV2": [{"type": "Primary", "baseSeverity": "HIGH", "cvssData": {"baseScore": 7.5, "version": "2.0"}}]}
    v = parse_cve(item, "x")
    assert (v.cvss_score, v.severity, v.cvss_version) == (7.5, "HIGH", "2.0")
    item["cve"]["metrics"] = {}
    assert parse_cve(item, "x").severity == "UNKNOWN"


@respx.mock
def test_search_pages_and_chunks_and_caches():
    calls = []

    def handler(request):
        params = dict(request.url.params)
        calls.append(params)
        idx = int(params["startIndex"])
        if params["pubStartDate"].startswith("2025-01-01"):
            items = [cve("CVE-A")] if idx == 0 else [cve("CVE-B")]
            return httpx.Response(200, json=page(items, idx, total=2, per_page=1))
        return httpx.Response(200, json=page([cve("CVE-A"), cve("CVE-C")]))

    respx.get(API_URL).mock(side_effect=handler)
    src = NVDSource(api_key="k", cache_ttl=60)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=150)
    kw = SearchKeyword(term="openssl", exact_match=True)

    found = asyncio.run(src.search(kw, start, end, "published"))
    assert sorted(v.id for v in found) == ["CVE-A", "CVE-B", "CVE-C"]
    assert len(calls) == 3  # two pages in chunk 1, one page in chunk 2
    assert calls[0]["keywordSearch"] == "openssl" and "keywordExactMatch" in calls[0]
    assert calls[0]["pubStartDate"] == "2025-01-01T00:00:00.000Z"

    asyncio.run(src.search(kw, start, end, "published"))
    assert len(calls) == 3  # served from cache


@respx.mock
def test_search_uses_last_modified_params():
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=page([])))
    src = NVDSource(api_key="", cache_ttl=0)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    asyncio.run(src.search(SearchKeyword(term="x"), start, start + timedelta(days=1), "modified"))
    params = route.calls[0].request.url.params
    assert "lastModStartDate" in params and "pubStartDate" not in params
    assert "keywordExactMatch" not in params
