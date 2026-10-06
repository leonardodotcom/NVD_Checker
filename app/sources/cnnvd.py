from datetime import datetime

from ..models import DateField, Vulnerability
from .base import SourceError
from .cn_common import WindowSource


class CNNVDSource(WindowSource):
    """China National Vulnerability Database of Information Security (cnnvd.org.cn).

    Run by CNITSEC. Needs a human-captured login session (see cn_session.py).
    The page/endpoint details are confirmed in Phase 0 with `scripts/cn_probe.py`;
    until the recordings exist `implemented` stays False and the source is shown
    as unavailable.
    """

    id = "cnnvd"
    name = "CNNVD (China)"
    site = "cnnvd"
    description = "China National Vulnerability Database of Information Security (CNITSEC); needs a login session"
    implemented = False

    async def fetch_entries(self, start: datetime, end: datetime, date_field: DateField) -> list[Vulnerability]:
        raise SourceError("CNNVD parser not implemented yet (needs Phase 0 recordings)")
