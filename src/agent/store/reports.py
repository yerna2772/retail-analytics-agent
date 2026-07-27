"""Report store: Protocol + in-memory fake for demo and tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class Report(BaseModel):
    id: str
    owner_id: str
    thread_id: str
    title: str
    body: str
    action_items: list[str]
    created_at: str
    deleted_at: str | None = None


@runtime_checkable
class ReportStore(Protocol):
    async def save(self, report: Report) -> str: ...
    async def list_reports(self, owner_id: str) -> list[Report]: ...
    async def get(self, report_id: str) -> Report | None: ...
    async def soft_delete(self, report_id: str) -> bool: ...


class FakeReportStore:
    """In-memory report store for demo and tests."""

    def __init__(self) -> None:
        self._reports: dict[str, Report] = {}

    async def save(self, report: Report) -> str:
        if not report.id:
            report = report.model_copy(update={"id": uuid.uuid4().hex[:12]})
        self._reports[report.id] = report
        return report.id

    async def list_reports(self, owner_id: str) -> list[Report]:
        return [
            r for r in self._reports.values() if r.owner_id == owner_id and r.deleted_at is None
        ]

    async def get(self, report_id: str) -> Report | None:
        r = self._reports.get(report_id)
        if r and r.deleted_at is None:
            return r
        return None

    async def soft_delete(self, report_id: str) -> bool:
        r = self._reports.get(report_id)
        if not r or r.deleted_at is not None:
            return False
        now = datetime.now(UTC).isoformat()
        self._reports[report_id] = r.model_copy(update={"deleted_at": now})
        return True
