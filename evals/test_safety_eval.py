from pathlib import Path

import pytest
import yaml

from agent.safety.ast_rules import validate_sql

SUITE_PATH = Path(__file__).parent / "safety_suite.yaml"


def _load_cases() -> list[dict]:
    with open(SUITE_PATH) as f:
        data = yaml.safe_load(f)
    return data["cases"]


CASES = _load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_safety_case(case: dict) -> None:
    result = validate_sql(case["sql"].strip())
    expected = case["expect"]

    if expected == "reject":
        assert not result.valid, (
            f"[{case['name']}] Expected rejection but got pass.\n"
            f"  SQL: {case['sql'].strip()}\n"
            f"  Reason: {result.reason}"
        )
    elif expected == "pass":
        assert result.valid, (
            f"[{case['name']}] Expected pass but got rejection.\n"
            f"  SQL: {case['sql'].strip()}\n"
            f"  Reason: {result.reason}"
        )
    else:
        pytest.fail(f"Unknown expect value: {expected}")
