from typing import Any

import pytest
from pydantic import ValidationError
from rozert_pay.risk_lists.types import RiskCheckResult, RiskDecision


class TestRiskCheckResult:
    def test_fails_if_declined_without_decision(self) -> None:
        with pytest.raises(ValidationError, match="decision is required"):
            RiskCheckResult(is_declined=True, decision=None)

    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param(
                {"is_declined": True, "decision": RiskDecision.BLACKLIST},
                id="declined_with_decision",
            ),
            pytest.param(
                {"is_declined": False, "decision": None},
                id="not_declined_without_decision",
            ),
            pytest.param(
                {"is_declined": False, "decision": RiskDecision.WHITELIST},
                id="not_declined_with_decision_(whitelist)",
            ),
        ],
    )
    def test_valid_combinations(self, kwargs: dict[str, Any]) -> None:
        try:
            result = RiskCheckResult(**kwargs)
            for key, value in kwargs.items():
                assert getattr(result, key) == value
        except ValidationError as e:
            pytest.fail(f"Validation failed unexpectedly for args {kwargs}: {e}")
