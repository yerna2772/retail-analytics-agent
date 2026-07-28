import pytest

from agent.safety.pii import (
    enforce_k_anonymity,
    is_pii_column,
    is_pii_column_name,
    scrub_output,
)


class TestPIIDenylist:
    @pytest.mark.parametrize(
        "table,column",
        [
            ("users", "first_name"),
            ("users", "last_name"),
            ("users", "email"),
            ("users", "street_address"),
            ("users", "postal_code"),
            ("users", "latitude"),
            ("users", "longitude"),
            ("users", "user_geom"),
        ],
    )
    def test_each_pii_column_detected(self, table: str, column: str) -> None:
        assert is_pii_column(table, column)

    def test_case_insensitive(self) -> None:
        assert is_pii_column("Users", "Email")
        assert is_pii_column("USERS", "FIRST_NAME")

    def test_non_pii_columns_allowed(self) -> None:
        assert not is_pii_column("users", "id")
        assert not is_pii_column("users", "age")
        assert not is_pii_column("users", "gender")
        assert not is_pii_column("users", "state")
        assert not is_pii_column("orders", "order_id")
        assert not is_pii_column("products", "name")

    def test_pii_column_name_check(self) -> None:
        assert is_pii_column_name("email")
        assert is_pii_column_name("first_name")
        assert not is_pii_column_name("id")
        assert not is_pii_column_name("age")


class TestOutputScrubber:
    def test_scrubs_email(self) -> None:
        text = "Customer contact: john.doe@example.com placed an order"
        result = scrub_output(text)
        assert "john.doe@example.com" not in result
        assert "[REDACTED]" in result

    def test_scrubs_email_in_product_name(self) -> None:
        text = "Product: Contact support@shop.com for details — $29.99"
        result = scrub_output(text)
        assert "support@shop.com" not in result
        assert "[REDACTED]" in result
        assert "$29.99" in result

    def test_scrubs_phone(self) -> None:
        text = "Call (555) 123-4567 for support"
        result = scrub_output(text)
        assert "(555) 123-4567" not in result
        assert "[REDACTED]" in result

    def test_scrubs_street_address(self) -> None:
        text = "Ships from 123 Main Street warehouse"
        result = scrub_output(text)
        assert "123 Main Street" not in result
        assert "[REDACTED]" in result

    def test_scrubs_postal_code(self) -> None:
        text = "Ships from Beverly Hills, CA 90210"
        result = scrub_output(text)
        assert "90210" not in result

    def test_numeric_id_not_scrubbed_as_postal(self) -> None:
        text = "User ID 10345 spent $200"
        result = scrub_output(text)
        assert result == text

    def test_clean_text_unchanged(self) -> None:
        text = "Revenue was $1.2M across 15 categories in Q4"
        assert scrub_output(text) == text

    def test_multiple_pii_scrubbed(self) -> None:
        text = "john@example.com lives at 456 Oak Avenue, call (555) 987-6543"
        result = scrub_output(text)
        assert "john@example.com" not in result
        assert "456 Oak Avenue" not in result
        assert "(555) 987-6543" not in result


class TestKAnonymity:
    def test_suppresses_small_groups(self) -> None:
        rows = [
            {"state": "CA", "revenue": 1000, "user_count": 10},
            {"state": "WY", "revenue": 50, "user_count": 3},
            {"state": "NY", "revenue": 800, "user_count": 20},
        ]
        result = enforce_k_anonymity(rows)
        assert len(result) == 2
        assert all(r["user_count"] >= 5 for r in result)

    def test_passes_all_above_threshold(self) -> None:
        rows = [
            {"state": "CA", "revenue": 1000, "user_count": 10},
            {"state": "NY", "revenue": 800, "user_count": 20},
        ]
        assert enforce_k_anonymity(rows) == rows

    def test_empty_rows(self) -> None:
        assert enforce_k_anonymity([]) == []

    def test_no_count_column_passes_through(self) -> None:
        rows = [{"state": "CA", "revenue": 1000}]
        assert enforce_k_anonymity(rows) == rows

    def test_custom_count_column(self) -> None:
        rows = [
            {"state": "CA", "distinct_users": 2},
            {"state": "NY", "distinct_users": 10},
        ]
        result = enforce_k_anonymity(rows, count_column="distinct_users")
        assert len(result) == 1
        assert result[0]["state"] == "NY"
