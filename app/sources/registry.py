from functools import lru_cache

from ..models import SourceInfo
from .base import Source
from .cnnvd import CNNVDSource
from .cnvd import CNVDSource
from .nvd import NVDSource


@lru_cache
def get_sources() -> dict[str, Source]:
    sources: list[Source] = [NVDSource(), CNNVDSource(), CNVDSource()]
    return {s.id: s for s in sources}


def list_sources() -> list[SourceInfo]:
    return [s.info() for s in get_sources().values()]
