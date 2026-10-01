from datetime import datetime

from ..models import DateField, SearchKeyword, Vulnerability
from .base import Source, SourceError


class CNVDSource(Source):
    """China National Vulnerability Database (cnvd.org.cn).

    Placeholder: CNVD requires an authenticated session. Implement login +
    search here (credentials via env vars) and flip `enabled`.
    """

    id = "cnvd"
    name = "CNVD (China)"
    description = "Requires an authenticated session — coming soon"
    requires_auth = True

    @property
    def enabled(self) -> bool:
        return False

    async def search(
        self, keyword: SearchKeyword, start: datetime, end: datetime, date_field: DateField
    ) -> list[Vulnerability]:
        raise SourceError("CNVD adapter is not implemented yet")
