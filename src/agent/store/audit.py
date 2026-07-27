"""Append-only audit log for destructive operations."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel


class AuditEntry(BaseModel):
    actor: str
    action: str
    target_ids: list[str]
    filter_text: str
    risk_tier: str
    trace_id: str
    timestamp: str


class FakeAuditStore:
    """In-memory audit log for demo and tests."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    async def append(self, entry: AuditEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)


def create_audit_entry(
    *,
    actor: str,
    action: str,
    target_ids: list[str],
    filter_text: str,
    risk_tier: str,
    trace_id: str,
) -> AuditEntry:
    return AuditEntry(
        actor=actor,
        action=action,
        target_ids=target_ids,
        filter_text=filter_text,
        risk_tier=risk_tier,
        trace_id=trace_id,
        timestamp=datetime.now(UTC).isoformat(),
    )
