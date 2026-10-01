from datetime import datetime

from ..models import DateField, SearchKeyword, Vulnerability
from .base import Source, SourceError


class CNNVDSource(Source):
    """China National Vulnerability Database of Information Security (cnnvd.org.cn).

    Placeholder: the CNNVD portal requires an authenticated session. Implement
    login + search here (credentials via env vars) and flip `enabled`.
    """

    id = "cnnvd"
    name = "CNNVD (China)"
    description = "Requires an authenticated session — coming soon"
    requires_auth = True

    @property
    def enabled(self) -> bool:
        return False

    async def search(
        self, keyword: SearchKeyword, start: datetime, end: datetime, date_field: DateField
    ) -> list[Vulnerability]:
        raise SourceError("CNNVD adapter is not implemented yet")
