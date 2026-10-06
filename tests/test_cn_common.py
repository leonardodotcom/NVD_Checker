import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.models import SearchKeyword, Vulnerability
from app.sources import cn_session
from app.sources.base import SessionExpired
from app.sources.cn_common import (
    WindowSource, extract_cves, map_severity, parse_cn_datetime, term_matches,
)

UTC = timezone.utc
NOW = datetime(2026, 10, 3, 12, 30, tzinfo=UTC)
STATE = {"cookies": [{"name": "sid", "value": "x", "domain": "d", "path": "/", "expires": -1}]}


@pytest.fixture(autouse=True)
def session_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CN_SESSION_DIR", str(tmp_path / "sessions"))


def entry(id_, desc, published=NOW - timedelta(days=1), aliases=()):
    return Vulnerability(id=id_, source="fake", description=desc, published=published, aliases=list(aliases))


class FakeCN(WindowSource):
    id = "fakecn"
    name = "Fake CN"
    site = "cnvd"
    implemented = True

    def __init__(self, entries=None, error=None, **kw):
        super().__init__(ttl=60, delay=0, **kw)
        self.entries, self.error, self.calls = entries or [], error, 0

    async def fetch_entries(self, start, end, date_field):
        self.calls += 1
        await asyncio.sleep(0.01)
        if self.error:
            raise self.error
        return self.entries


def test_severity_words():
    assert [map_severity(x) for x in ("超危", "高危", "中危", "低危", "高", "中", "低", "High", None, "未知")] == [
        "CRITICAL", "HIGH", "MEDIUM", "LOW", "HIGH", "MEDIUM", "LOW", "HIGH", "UNKNOWN", "UNKNOWN"]


def test_dates_are_beijing_time_converted_to_utc():
    assert parse_cn_datetime("2026-10-01 08:30:00") == datetime(2026, 10, 1, 0, 30, tzinfo=UTC)
    assert parse_cn_datetime("2026-10-01") == datetime(2026, 9, 30, 16, 0, tzinfo=UTC)
    assert parse_cn_datetime("2026年10月01日") == datetime(2026, 9, 30, 16, 0, tzinfo=UTC)
    assert parse_cn_datetime("2026-10-01T08:30:00Z") == datetime(2026, 10, 1, 8, 30, tzinfo=UTC)
    assert parse_cn_datetime("") is None and parse_cn_datetime("garbage") is None


def test_extract_cves_dedupes_and_uppercases():
    assert extract_cves("see cve-2026-1234 and CVE-2026-1234", "CVE-2025-99999") == ["CVE-2026-1234", "CVE-2025-99999"]


def test_term_matching_chinese_latin_and_exact():
    e = entry("CNVD-2026-1", "Apache Tomcat 存在远程代码执行漏洞", aliases=["CVE-2026-5"])
    assert term_matches(e, SearchKeyword(term="远程代码执行"))
    assert term_matches(e, SearchKeyword(term="tomcat"))
    assert term_matches(e, SearchKeyword(term="cve-2026-5"))
    assert not term_matches(e, SearchKeyword(term="nginx"))
    ssl = entry("CNVD-2026-2", "OpenSSL heap overflow")
    assert term_matches(ssl, SearchKeyword(term="ssl"))
    assert not term_matches(ssl, SearchKeyword(term="ssl", exact_match=True))
    assert term_matches(ssl, SearchKeyword(term="openssl", exact_match=True))


def test_search_filters_locally_and_one_fetch_is_shared():
    cn_session.save_state("cnvd", STATE)
    src = FakeCN([entry("CNVD-1", "Apache 漏洞"), entry("CNVD-2", "Nginx 漏洞"),
                  entry("CNVD-3", "Apache 旧漏洞", published=NOW - timedelta(days=40))])
    start, end = NOW - timedelta(days=7), NOW

    async def run():
        return await asyncio.gather(*(src.search(SearchKeyword(term=t), start, end, "published")
                                       for t in ("apache", "nginx", "漏洞")))

    apache, nginx, vuln = asyncio.run(run())
    assert [v.id for v in apache] == ["CNVD-1"] and apache[0].matched_keywords == ["apache"]
    assert [v.id for v in nginx] == ["CNVD-2"]
    assert sorted(v.id for v in vuln) == ["CNVD-1", "CNVD-2"]  # CNVD-3 is outside the window
    assert src.calls == 1  # three keywords, one site fetch
    asyncio.run(src.search(SearchKeyword(term="apache"), start + timedelta(minutes=3), end, "published"))
    assert src.calls == 1  # served from cache


def test_missing_session_raises_session_expired():
    src = FakeCN([entry("CNVD-1", "x")])
    with pytest.raises(SessionExpired):
        asyncio.run(src.search(SearchKeyword(term="x"), NOW - timedelta(days=1), NOW, "published"))
    assert src.calls == 0


def test_site_rejection_marks_session_expired():
    cn_session.save_state("cnvd", STATE)
    src = FakeCN(error=SessionExpired("login page"))
    with pytest.raises(SessionExpired):
        asyncio.run(src.search(SearchKeyword(term="x"), NOW - timedelta(days=1), NOW, "published"))
    assert cn_session.describe("cnvd")[0] == "session_expired"
    assert src.enabled is False


def test_unfinished_adapters_stay_disabled():
    from app.sources.cnnvd import CNNVDSource
    from app.sources.cnvd import CNVDSource

    cn_session.save_state("cnvd", STATE)
    assert CNVDSource().status()[0] == "not_implemented" and not CNVDSource().enabled
    assert CNNVDSource().info().status == "not_implemented"
