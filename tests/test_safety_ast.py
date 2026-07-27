import pytest

from agent.safety.ast_rules import ALLOWED_TABLES, DEFAULT_LIMIT, validate_sql

PII_COLUMNS = [
    ("users", "first_name"),
    ("users", "last_name"),
    ("users", "email"),
    ("users", "street_address"),
    ("users", "postal_code"),
    ("users", "latitude"),
    ("users", "longitude"),
    ("users", "user_geom"),
]


# ── Each denylisted column rejected individually ──────────────────────


class TestPIIColumnRejection:
    @pytest.mark.parametrize("table,col", PII_COLUMNS, ids=[c for _, c in PII_COLUMNS])
    def test_direct_reference(self, table: str, col: str) -> None:
        sql = f"SELECT {col} FROM {table} LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid, f"Should reject {table}.{col}"

    @pytest.mark.parametrize("table,col", PII_COLUMNS, ids=[c for _, c in PII_COLUMNS])
    def test_via_table_alias(self, table: str, col: str) -> None:
        sql = f"SELECT u.{col} FROM {table} AS u LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid, f"Should reject {table}.{col} via alias"

    @pytest.mark.parametrize("table,col", PII_COLUMNS, ids=[c for _, c in PII_COLUMNS])
    def test_via_subquery(self, table: str, col: str) -> None:
        sql = f"SELECT {col} FROM (SELECT {col}, id FROM {table}) AS sub LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid, f"Should reject {table}.{col} in subquery"

    @pytest.mark.parametrize("table,col", PII_COLUMNS, ids=[c for _, c in PII_COLUMNS])
    def test_via_cte(self, table: str, col: str) -> None:
        sql = f"WITH cte AS (SELECT {col}, id FROM {table}) SELECT {col} FROM cte LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid, f"Should reject {table}.{col} via CTE"


# ── SELECT * rejected on every table ──────────────────────────────────


class TestSelectStarRejection:
    @pytest.mark.parametrize("table", sorted(ALLOWED_TABLES))
    def test_select_star(self, table: str) -> None:
        sql = f"SELECT * FROM {table}"
        result = validate_sql(sql)
        assert not result.valid
        assert "SELECT *" in result.reason

    def test_table_qualified_star(self) -> None:
        sql = "SELECT users.* FROM users"
        result = validate_sql(sql)
        assert not result.valid


# ── DML / DDL rejected ────────────────────────────────────────────────


class TestDMLDDLRejection:
    @pytest.mark.parametrize(
        "sql,label",
        [
            ("INSERT INTO users (id) VALUES (1)", "INSERT"),
            ("UPDATE users SET age = 1 WHERE id = 1", "UPDATE"),
            ("DELETE FROM users WHERE id = 1", "DELETE"),
            ("DROP TABLE users", "DROP"),
            ("CREATE TABLE foo (id INT64)", "CREATE"),
            ("TRUNCATE TABLE users", "TRUNCATE"),
        ],
        ids=["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "TRUNCATE"],
    )
    def test_rejects_dml_ddl(self, sql: str, label: str) -> None:
        result = validate_sql(sql)
        assert not result.valid, f"Should reject {label}"

    def test_rejects_multiple_statements(self) -> None:
        result = validate_sql("SELECT id FROM users; DROP TABLE users")
        assert not result.valid


# ── Comment smuggling and mixed-case evasion ──────────────────────────


class TestEvasionAttempts:
    def test_comment_does_not_smuggle_pii(self) -> None:
        sql = "SELECT id /* email */ FROM users LIMIT 10"
        result = validate_sql(sql)
        assert result.valid, "Comment content is stripped by AST — should pass"

    def test_line_comment_does_not_smuggle_ddl(self) -> None:
        sql = "SELECT id FROM users LIMIT 10 -- DROP TABLE users"
        result = validate_sql(sql)
        assert result.valid, "Line comment is stripped by AST — should pass"

    def test_mixed_case_pii_rejected(self) -> None:
        sql = "SELECT EmAiL FROM Users LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid

    def test_mixed_case_table_rejected(self) -> None:
        sql = "SELECT id FROM UnKnOwN_TaBlE LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid

    def test_pii_in_where_clause(self) -> None:
        sql = "SELECT id FROM users WHERE email = 'x@y.com' LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid

    def test_pii_in_order_by(self) -> None:
        sql = "SELECT id FROM users ORDER BY first_name LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid

    def test_pii_in_group_by(self) -> None:
        sql = "SELECT email, COUNT(*) FROM users GROUP BY email LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid

    def test_pii_in_aggregate(self) -> None:
        sql = "SELECT COUNT(email) FROM users LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid


# ── Legitimate analysis queries pass ──────────────────────────────────


class TestLegitimateQueries:
    def test_state_level_aov(self) -> None:
        sql = (
            "SELECT u.state, AVG(oi.sale_price) AS aov "
            "FROM users u "
            "JOIN order_items oi ON u.id = oi.user_id "
            "GROUP BY u.state "
            "LIMIT 50"
        )
        result = validate_sql(sql)
        assert result.valid, result.reason

    def test_category_revenue(self) -> None:
        sql = (
            "SELECT p.category, SUM(oi.sale_price) AS revenue "
            "FROM products p "
            "JOIN order_items oi ON p.id = oi.product_id "
            "GROUP BY p.category "
            "ORDER BY revenue DESC "
            "LIMIT 20"
        )
        result = validate_sql(sql)
        assert result.valid, result.reason

    def test_cohort_retention(self) -> None:
        sql = (
            "SELECT "
            "  DATE_TRUNC(u.created_at, MONTH) AS cohort_month, "
            "  DATE_TRUNC(o.created_at, MONTH) AS order_month, "
            "  COUNT(DISTINCT u.id) AS users "
            "FROM users u "
            "JOIN orders o ON u.id = o.user_id "
            "GROUP BY cohort_month, order_month "
            "ORDER BY cohort_month, order_month "
            "LIMIT 100"
        )
        result = validate_sql(sql)
        assert result.valid, result.reason

    def test_top_customers_by_user_id(self) -> None:
        sql = (
            "SELECT oi.user_id, SUM(oi.sale_price) AS total_spend "
            "FROM order_items oi "
            "GROUP BY oi.user_id "
            "ORDER BY total_spend DESC "
            "LIMIT 10"
        )
        result = validate_sql(sql)
        assert result.valid, result.reason

    def test_monthly_revenue(self) -> None:
        sql = (
            "SELECT "
            "  DATE_TRUNC(oi.created_at, MONTH) AS month, "
            "  SUM(oi.sale_price) AS revenue "
            "FROM order_items oi "
            "WHERE oi.status NOT IN ('Cancelled', 'Returned') "
            "GROUP BY month "
            "ORDER BY month "
            "LIMIT 36"
        )
        result = validate_sql(sql)
        assert result.valid, result.reason

    def test_order_status_distribution(self) -> None:
        sql = "SELECT status, COUNT(*) AS cnt FROM orders GROUP BY status LIMIT 20"
        result = validate_sql(sql)
        assert result.valid, result.reason


# ── LIMIT injection ───────────────────────────────────────────────────


class TestLimitInjection:
    def test_injects_limit_when_missing(self) -> None:
        sql = "SELECT id FROM users"
        result = validate_sql(sql)
        assert result.valid
        assert str(DEFAULT_LIMIT) in result.sql

    def test_preserves_existing_limit(self) -> None:
        sql = "SELECT id FROM users LIMIT 50"
        result = validate_sql(sql)
        assert result.valid
        assert "50" in result.sql


# ── CROSS JOIN rejection ─────────────────────────────────────────────


class TestCrossJoin:
    def test_rejects_cross_join_without_predicate(self) -> None:
        sql = "SELECT o.order_id FROM orders o CROSS JOIN products p LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid
        assert "CROSS" in result.reason

    def test_allows_cross_join_with_where(self) -> None:
        sql = (
            "SELECT o.order_id, p.name "
            "FROM orders o CROSS JOIN products p "
            "WHERE o.num_of_item > 0 "
            "LIMIT 10"
        )
        result = validate_sql(sql)
        assert result.valid, result.reason


# ── Table allowlist ───────────────────────────────────────────────────


class TestTableAllowlist:
    def test_rejects_unknown_table(self) -> None:
        sql = "SELECT id FROM events LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid
        assert "not allowed" in result.reason

    def test_rejects_information_schema(self) -> None:
        sql = "SELECT table_name FROM INFORMATION_SCHEMA.TABLES LIMIT 10"
        result = validate_sql(sql)
        assert not result.valid
