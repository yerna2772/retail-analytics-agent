"""DuckDB-backed stand-in for BigQuery.

Executes the *actual* generated SQL instead of returning canned rows, so the
local harness exercises the AST validator, the repair loop, empty-result
diagnosis and semantic correctness for real. sqlglot transpiles the BigQuery
dialect the agent emits into DuckDB.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

import duckdb
import sqlglot

DATASET = "bigquery-public-data.thelook_ecommerce"
TABLES = ["users", "products", "orders", "order_items"]


@dataclass(frozen=True)
class DryRunResult:
    valid: bool
    estimated_bytes: int = 0
    error: str | None = None


@dataclass
class QueryOutcome:
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    row_count: int = 0
    bytes_billed: int = 0
    cache_hit: bool = False
    job_id: str | None = None


class SQLRepairableError(Exception): ...


class FakeBigQueryRunner:
    def __init__(self, fixtures: str = "fixtures"):
        self.con = duckdb.connect(":memory:")
        p = pathlib.Path(fixtures)
        for t in TABLES:
            self.con.execute(
                f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto('{p / f'{t}.csv'}')"
            )
        self._sizes = {
            t: self.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in TABLES
        }

    def _translate(self, sql: str) -> str:
        """BigQuery dialect -> DuckDB, dropping the project/dataset qualifier.

        Done on the parse tree, not with regex. The first version of this used
        re.sub and silently ate the opening backtick of a quoted identifier --
        exactly the class of bug the AST validator exists to avoid.
        """
        tree = sqlglot.parse_one(sql, read="bigquery")
        for tb in tree.find_all(sqlglot.exp.Table):
            tb.set("catalog", None)
            tb.set("db", None)
        return tree.sql(dialect="duckdb")

    def dry_run(self, sql: str) -> DryRunResult:
        try:
            translated = self._translate(sql)
            self.con.execute(f"EXPLAIN {translated}")
        except Exception as exc:
            return DryRunResult(valid=False, error=str(exc).split("\n")[0])
        est = sum(self._sizes[t] * 120 for t in TABLES if re.search(rf"\b{t}\b", sql))
        return DryRunResult(valid=True, estimated_bytes=est)

    def run(self, sql: str, *, estimate: DryRunResult | None = None) -> QueryOutcome:
        estimate = estimate or self.dry_run(sql)
        if not estimate.valid:
            raise SQLRepairableError(estimate.error or "dry_run failed")
        rel = self.con.execute(self._translate(sql))
        cols = [d[0] for d in rel.description]
        rows = [dict(zip(cols, r, strict=False)) for r in rel.fetchall()]
        return QueryOutcome(cols, rows, len(rows), estimate.estimated_bytes, False, "fake-job")


class DuckDBBigQuery:
    """Async adapter wrapping FakeBigQueryRunner to match BigQueryClient protocol."""

    def __init__(self, fixtures: str = "fixtures") -> None:
        self._runner = FakeBigQueryRunner(fixtures)

    async def dry_run(self, sql: str) -> dict:
        result = self._runner.dry_run(sql)
        return {
            "ok": result.valid,
            "estimated_bytes": result.estimated_bytes,
            "error": result.error,
        }

    async def execute(self, sql: str) -> dict:
        outcome = self._runner.run(sql)
        return {
            "columns": outcome.columns,
            "rows": outcome.rows,
            "row_count": outcome.row_count,
            "bytes_scanned": outcome.bytes_billed,
        }

    async def get_table_schema(self, table: str) -> dict[str, str]:
        from agent.safety.ast_rules import TABLE_SCHEMA

        return TABLE_SCHEMA.get(table, {})


if __name__ == "__main__":
    bq = FakeBigQueryRunner()
    Q = f"""
    SELECT
      FORMAT_TIMESTAMP('%Y-%m', oi.created_at) AS month,
      ROUND(SUM(oi.sale_price), 2) AS revenue
    FROM `{DATASET}.order_items` AS oi
    WHERE EXTRACT(YEAR FROM oi.created_at) = 2023
      AND oi.status NOT IN ('Cancelled', 'Returned')
    GROUP BY month ORDER BY month LIMIT 5
    """
    print("-- BigQuery dialect in, DuckDB out --")
    print(bq._translate(Q).strip()[:200], "...\n")
    out = bq.run(Q)
    for r in out.rows:
        print(f"  {r['month']}  {r['revenue']:>12,.2f}")
    print(f"\n  rows={out.row_count}  est_bytes={out.bytes_billed:,}")
