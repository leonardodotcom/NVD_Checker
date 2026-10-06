from datetime import datetime

from ..models import DateField, Vulnerability
from .base import SourceError
from .cn_common import WindowSource


class CNVDSource(WindowSource):
    """China National Vulnerability Database (cnvd.org.cn).

    Run by CNCERT/CC. Needs a human-captured login session, and the site adds a
    JavaScript anti-bot challenge, so the adapter may have to drive a headless
    browser using the saved session. Details are confirmed in Phase 0 with
    `scripts/cn_probe.py`; until then `implemented` stays False.
    """

    id = "cnvd"
    name = "CNVD (China)"
    site = "cnvd"
    description = "China National Vulnerability Database (CNCERT/CC); needs a login session"
    implemented = False

    async def fetch_entries(self, start: datetime, end: datetime, date_field: DateField) -> list[Vulnerability]:
        raise SourceError("CNVD parser not implemented yet (needs Phase 0 recordings)")
