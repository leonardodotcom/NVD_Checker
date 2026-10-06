from abc import ABC, abstractmethod
from datetime import datetime

from ..models import DateField, SearchKeyword, SourceInfo, Vulnerability


class SourceError(Exception):
    """Raised by an adapter when a query cannot be completed."""


class SessionExpired(SourceError):
    """The saved login session was rejected (login page, captcha, 401/403).

    A human has to log in again (`python -m app.manage cn-login <site>`).
    """


class Source(ABC):
    """A vulnerability database the aggregator can query.

    To add a new database, subclass this, implement `search`, and register an
    instance in `registry.py`. Sources that need a login (e.g. CNNVD/CNVD) should
    read their credentials from environment variables and set `enabled` only
    when those are present.
    """

    id: str
    name: str
    description: str = ""
    requires_auth: bool = False

    @property
    def enabled(self) -> bool:
        return True

    def status(self) -> tuple[str, str]:
        """(status, human-readable detail) shown next to the source in the UI."""
        return ("ready", "") if self.enabled else ("not_implemented", "Not available")

    def info(self) -> SourceInfo:
        status, detail = self.status()
        return SourceInfo(
            id=self.id,
            name=self.name,
            enabled=self.enabled,
            requires_auth=self.requires_auth,
            description=self.description,
            status=status,
            status_detail=detail,
        )

    @abstractmethod
    async def search(
        self, keyword: SearchKeyword, start: datetime, end: datetime, date_field: DateField
    ) -> list[Vulnerability]:
        """Return every vulnerability matching `keyword` within [start, end]."""
