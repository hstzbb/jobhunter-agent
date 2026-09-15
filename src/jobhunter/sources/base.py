"""Job-source adapters.

A source knows how to turn a search query into a list of Jobs. The
project ships a `DummySource` that emits fake jobs so the whole pipeline
is runnable offline. Real sources (LinkedIn, Boss, Lagou, company ATS,
Greenhouse, Lever, ...) implement the same interface.

Keep each adapter small: scraping, parsing, pagination. All scoring,
fact-checking and submitting live in the pipeline -- adapters never
decide what to apply to.
"""
from __future__ import annotations

import uuid
from typing import Iterable, Protocol

from ..store import models as m


class Source(Protocol):
    name: str

    def search(self, query: str, *, limit: int = 50) -> list[m.Job]:
        ...


def make_id(source: str, raw_id: str) -> str:
    return f"{source}:{raw_id}" if raw_id else f"{source}:{uuid.uuid4().hex[:10]}"
