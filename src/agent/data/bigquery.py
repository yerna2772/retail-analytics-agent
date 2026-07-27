from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures"


@runtime_checkable
class BigQueryClient(Protocol):
    async def dry_run(self, sql: str) -> dict[str, Any]: ...
    async def execute(self, sql: str) -> dict[str, Any]: ...
    async def get_table_schema(self, table: str) -> dict[str, str]: ...


class FakeBigQuery:
    """CSV-backed BigQuery stub. No network, no credentials."""

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = fixtures_dir or FIXTURES_DIR
        self._tables: dict[str, list[dict[str, str]]] = {}
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        if not self._fixtures_dir.exists():
            logger.warning("Fixtures directory not found: %s", self._fixtures_dir)
            return
        for csv_file in sorted(self._fixtures_dir.glob("*.csv")):
            table_name = csv_file.stem
            with open(csv_file, newline="") as f:
                self._tables[table_name] = list(csv.DictReader(f))
            logger.debug("Loaded fixture %s (%d rows)", table_name, len(self._tables[table_name]))

    async def dry_run(self, sql: str) -> dict[str, Any]:
        return {"estimated_bytes": 1024, "ok": True}

    async def execute(self, sql: str) -> dict[str, Any]:
        return {"columns": [], "rows": [], "row_count": 0, "bytes_scanned": 1024}

    async def get_table_schema(self, table: str) -> dict[str, str]:
        from agent.safety.ast_rules import TABLE_SCHEMA

        return TABLE_SCHEMA.get(table, {})
