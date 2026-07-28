from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from google.cloud import bigquery as bq_sdk

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parents[3] / "fixtures"


@runtime_checkable
class BigQueryClient(Protocol):
    async def dry_run(self, sql: str) -> dict[str, Any]: ...
    async def execute(self, sql: str) -> dict[str, Any]: ...
    async def get_table_schema(self, table: str) -> dict[str, str]: ...


class RealBigQuery:
    """Thin async wrapper over the google-cloud-bigquery SDK."""

    def __init__(self, project: str) -> None:
        self._client = bq_sdk.Client(project=project)

    async def dry_run(self, sql: str) -> dict[str, Any]:
        job_config = bq_sdk.QueryJobConfig(dry_run=True, use_query_cache=False)
        try:
            job = self._client.query(sql, job_config=job_config)
            return {
                "ok": True,
                "estimated_bytes": job.total_bytes_processed or 0,
                "error": None,
            }
        except Exception as exc:
            raw = str(exc)
            first_line = raw.split("\n")[0]
            if "https://" in first_line:
                idx = first_line.find(": ", first_line.find("https://") + 10)
                msg = first_line[idx + 2 :] if idx >= 0 else first_line
            elif ": " in first_line:
                msg = first_line.split(": ", 1)[-1]
            else:
                msg = first_line
            return {
                "ok": False,
                "estimated_bytes": 0,
                "error": msg.strip(),
            }

    async def execute(self, sql: str) -> dict[str, Any]:
        job = self._client.query(sql)
        result = job.result()
        columns = [field.name for field in result.schema]
        rows = [dict(row.items()) for row in result]
        return {
            "columns": columns,
            "rows": rows,
            "row_count": result.total_rows or len(rows),
            "bytes_scanned": job.total_bytes_processed or 0,
        }

    async def get_table_schema(self, table: str) -> dict[str, str]:
        from agent.safety.ast_rules import TABLE_SCHEMA

        return TABLE_SCHEMA.get(table, {})


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
        sql_lower = sql.lower()

        if "avg" in sql_lower and "spend" in sql_lower:
            return self._avg_spend_by_state(sql_lower)
        if "category" in sql_lower and "state" in sql_lower:
            return self._category_by_state(sql_lower)
        if "date_trunc" in sql_lower and "revenue" in sql_lower:
            return self._revenue_by_month(sql_lower)
        if "user_id" in sql_lower and "total_spend" in sql_lower:
            return self._top_customers()
        if "category" in sql_lower and "revenue" in sql_lower:
            return self._revenue_by_category()
        if "status" in sql_lower and "count" in sql_lower:
            return self._order_status_counts()

        return self._generic_count()

    def _avg_spend_by_state(self, sql_lower: str) -> dict[str, Any]:
        items = self._tables.get("order_items", [])
        users = {u["id"]: u for u in self._tables.get("users", [])}
        state_filter = None
        for s in ["texas", "california", "new york", "florida"]:
            if s in sql_lower:
                state_filter = s
                break

        total, count = 0.0, 0
        for row in items:
            if row.get("status") in ("Cancelled", "Returned"):
                continue
            uid = row.get("user_id", "")
            user = users.get(uid, {})
            if state_filter and user.get("state", "").lower() != state_filter:
                continue
            total += float(row.get("sale_price", 0))
            count += 1

        avg = round(total / count, 2) if count else 0
        return {
            "columns": ["avg_spend"],
            "rows": [{"avg_spend": avg}],
            "row_count": 1,
            "bytes_scanned": 1024,
        }

    def _category_by_state(self, sql_lower: str) -> dict[str, Any]:
        items = self._tables.get("order_items", [])
        users = {u["id"]: u for u in self._tables.get("users", [])}
        products = {p["id"]: p for p in self._tables.get("products", [])}

        data: dict[tuple[str, str], float] = {}
        for row in items:
            if row.get("status") in ("Cancelled", "Returned"):
                continue
            uid = row.get("user_id", "")
            user = users.get(uid, {})
            state = user.get("state", "Unknown")
            pid = row.get("product_id", "")
            cat = products.get(pid, {}).get("category", "Unknown")
            key = (cat, state)
            data[key] = data.get(key, 0) + float(row.get("sale_price", 0))

        rows = [
            {"category": k[0], "state": k[1], "revenue": round(v, 2)}
            for k, v in sorted(data.items(), key=lambda x: x[1], reverse=True)
        ]
        return {
            "columns": ["category", "state", "revenue"],
            "rows": rows,
            "row_count": len(rows),
            "bytes_scanned": 1024,
        }

    def _revenue_by_month(self, sql_lower: str) -> dict[str, Any]:
        items = self._tables.get("order_items", [])
        monthly: dict[str, float] = {}
        for row in items:
            if row.get("status") in ("Cancelled", "Returned"):
                continue
            created = row.get("created_at", "")
            month = created[:7]
            if not month:
                continue
            if "texas" in sql_lower or ("state" in sql_lower and "'texas'" in sql_lower):
                users = {
                    u["id"]: u
                    for u in self._tables.get("users", [])
                    if u.get("state", "").lower() == "texas"
                }
                if row.get("user_id") not in users:
                    continue
            monthly[month] = monthly.get(month, 0) + float(row.get("sale_price", 0))

        rows = [{"month": m, "revenue": round(v, 2)} for m, v in sorted(monthly.items())]
        return {
            "columns": ["month", "revenue"],
            "rows": rows,
            "row_count": len(rows),
            "bytes_scanned": 1024,
        }

    def _top_customers(self) -> dict[str, Any]:
        items = self._tables.get("order_items", [])
        spend: dict[str, float] = {}
        for row in items:
            uid = row.get("user_id", "")
            spend[uid] = spend.get(uid, 0) + float(row.get("sale_price", 0))
        rows = [
            {"user_id": uid, "total_spend": round(val, 2)}
            for uid, val in sorted(spend.items(), key=lambda x: x[1], reverse=True)
        ]
        return {
            "columns": ["user_id", "total_spend"],
            "rows": rows,
            "row_count": len(rows),
            "bytes_scanned": 1024,
        }

    def _revenue_by_category(self) -> dict[str, Any]:
        items = self._tables.get("order_items", [])
        products = {p["id"]: p for p in self._tables.get("products", [])}
        cat_rev: dict[str, float] = {}
        for row in items:
            pid = row.get("product_id", "")
            prod = products.get(pid, {})
            cat = prod.get("category", "Unknown")
            cat_rev[cat] = cat_rev.get(cat, 0) + float(row.get("sale_price", 0))
        rows = [
            {"category": c, "revenue": round(v, 2)}
            for c, v in sorted(cat_rev.items(), key=lambda x: x[1], reverse=True)
        ]
        return {
            "columns": ["category", "revenue"],
            "rows": rows,
            "row_count": len(rows),
            "bytes_scanned": 1024,
        }

    def _order_status_counts(self) -> dict[str, Any]:
        orders = self._tables.get("orders", [])
        counts: dict[str, int] = {}
        for row in orders:
            status = row.get("status", "Unknown")
            counts[status] = counts.get(status, 0) + 1
        rows = [{"status": s, "cnt": c} for s, c in sorted(counts.items())]
        return {
            "columns": ["status", "cnt"],
            "rows": rows,
            "row_count": len(rows),
            "bytes_scanned": 1024,
        }

    def _generic_count(self) -> dict[str, Any]:
        orders = self._tables.get("orders", [])
        return {
            "columns": ["total"],
            "rows": [{"total": len(orders)}],
            "row_count": 1,
            "bytes_scanned": 1024,
        }

    async def get_table_schema(self, table: str) -> dict[str, str]:
        from agent.safety.ast_rules import TABLE_SCHEMA

        return TABLE_SCHEMA.get(table, {})
