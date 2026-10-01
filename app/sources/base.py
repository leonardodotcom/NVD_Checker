from abc import ABC, abstractmethod
from datetime import datetime

from ..models import DateField, SearchKeyword, SourceInfo, Vulnerability


class SourceError(Exception):
    """Raised by an adapter when a query cannot be completed."""


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

    def info(self) -> SourceInfo:
        return SourceInfo(
            id=self.id,
            name=self.name,
            enabled=self.enabled,
            requires_auth=self.requires_auth,
            description=self.description,
        )

    @abstractmethod
    async def search(
        self, keyword: SearchKeyword, start: datetime, end: datetime, date_field: DateField
    ) -> list[Vulnerability]:
        """Return every vulnerability matching `keyword` within [start, end]."""
