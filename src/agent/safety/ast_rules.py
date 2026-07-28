from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from agent.safety.pii import is_pii_column, is_pii_column_name

ALLOWED_TABLES: frozenset[str] = frozenset({"users", "orders", "order_items", "products"})

DEFAULT_LIMIT = 1000

TABLE_SCHEMA: dict[str, dict[str, str]] = {
    "users": {
        "id": "INT64",
        "first_name": "STRING",
        "last_name": "STRING",
        "email": "STRING",
        "age": "INT64",
        "gender": "STRING",
        "state": "STRING",
        "street_address": "STRING",
        "postal_code": "STRING",
        "city": "STRING",
        "country": "STRING",
        "latitude": "FLOAT64",
        "longitude": "FLOAT64",
        "traffic_source": "STRING",
        "created_at": "TIMESTAMP",
        "user_geom": "GEOGRAPHY",
    },
    "orders": {
        "order_id": "INT64",
        "user_id": "INT64",
        "status": "STRING",
        "gender": "STRING",
        "created_at": "TIMESTAMP",
        "returned_at": "TIMESTAMP",
        "shipped_at": "TIMESTAMP",
        "delivered_at": "TIMESTAMP",
        "num_of_item": "INT64",
    },
    "order_items": {
        "id": "INT64",
        "order_id": "INT64",
        "user_id": "INT64",
        "product_id": "INT64",
        "inventory_item_id": "INT64",
        "status": "STRING",
        "created_at": "TIMESTAMP",
        "shipped_at": "TIMESTAMP",
        "delivered_at": "TIMESTAMP",
        "returned_at": "TIMESTAMP",
        "sale_price": "FLOAT64",
    },
    "products": {
        "id": "INT64",
        "cost": "FLOAT64",
        "category": "STRING",
        "name": "STRING",
        "brand": "STRING",
        "retail_price": "FLOAT64",
        "department": "STRING",
        "sku": "STRING",
        "distribution_center_id": "INT64",
    },
}


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str
    sql: str


def validate_sql(sql: str) -> ValidationResult:
    # --- parse ---------------------------------------------------------
    try:
        statements = sqlglot.parse(sql, dialect="bigquery")
    except sqlglot.errors.ParseError as e:
        return ValidationResult(valid=False, reason=f"SQL parse error: {e}", sql=sql)

    if len(statements) != 1 or statements[0] is None:
        return ValidationResult(valid=False, reason="Exactly one SQL statement allowed", sql=sql)

    parsed = statements[0]

    # --- root must be SELECT (WITH…SELECT is still exp.Select) ---------
    if not isinstance(parsed, exp.Select):
        return ValidationResult(
            valid=False,
            reason=f"Only SELECT queries allowed, got {type(parsed).__name__}",
            sql=sql,
        )

    # --- no SELECT * (Invariant 3) -------------------------------------
    for star in parsed.find_all(exp.Star):
        parent = star.parent
        if isinstance(parent, (exp.Count, exp.Anonymous)):
            continue
        return ValidationResult(valid=False, reason="SELECT * is not allowed", sql=sql)

    # --- collect virtual table names (CTEs, subquery aliases) ----------
    virtual_tables: set[str] = set()
    for cte in parsed.find_all(exp.CTE):
        name = cte.alias_or_name
        if name:
            virtual_tables.add(name.lower())
    for subq in parsed.find_all(exp.Subquery):
        alias = subq.alias_or_name
        if alias:
            virtual_tables.add(alias.lower())

    # --- check every real table ∈ allowed set --------------------------
    alias_map: dict[str, str] = {}
    for table in parsed.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name in virtual_tables:
            continue
        if table_name not in ALLOWED_TABLES:
            return ValidationResult(
                valid=False,
                reason=f"Table '{table.name}' is not allowed",
                sql=sql,
            )
        alias = (table.alias or table_name).lower()
        alias_map[alias] = table_name
        alias_map[table_name] = table_name

    # --- check every column against PII denylist -----------------------
    for col in parsed.find_all(exp.Column):
        col_name = col.name.lower()
        table_ref = col.table.lower() if col.table else ""

        if table_ref:
            real_table = alias_map.get(table_ref, table_ref)
            if real_table in ALLOWED_TABLES and is_pii_column(real_table, col_name):
                return ValidationResult(
                    valid=False,
                    reason=f"PII column '{real_table}.{col_name}' is not allowed",
                    sql=sql,
                )
            if real_table not in ALLOWED_TABLES and is_pii_column_name(col_name):
                return ValidationResult(
                    valid=False,
                    reason=f"Column '{col_name}' matches a PII column name",
                    sql=sql,
                )
        else:
            if is_pii_column_name(col_name):
                return ValidationResult(
                    valid=False,
                    reason=f"Unqualified column '{col_name}' matches a PII column name",
                    sql=sql,
                )

    # --- no CROSS JOIN without predicate -------------------------------
    for join in parsed.find_all(exp.Join):
        if str(join.args.get("kind", "")).upper() == "CROSS":
            has_on = join.args.get("on") is not None
            has_where = parsed.find(exp.Where) is not None
            if not has_on and not has_where:
                return ValidationResult(
                    valid=False,
                    reason="CROSS JOIN without predicate is not allowed",
                    sql=sql,
                )

    # --- LIMIT: check presence, but never rewrite the SQL -------------
    has_limit = parsed.args.get("limit") is not None
    if has_limit:
        return ValidationResult(valid=True, reason="pass", sql=sql)
    return ValidationResult(
        valid=True,
        reason="pass",
        sql=f"SELECT * FROM ({sql}) LIMIT {DEFAULT_LIMIT}",
    )
