from enum import StrEnum

from pydantic import BaseModel, model_validator


class RiskDecision(StrEnum):
    """Structured risk detail info"""

    MERCHANT_BLACKLIST = "User in Merchant Blacklist"
    GLOBAL_BLACKLIST = "User in Blacklist (global)"
    BLACKLIST = "User in Blacklist"
    GRAYLIST = "User in Graylist"
    GLOBAL_GRAYLIST = "User in Graylist (global)"
    WHITELIST = "User in Whitelist"


class RiskCheckResult(BaseModel):
    """Result of the risk list check for a transaction"""

    is_declined: bool
    decision: RiskDecision | None = None

    @model_validator(mode="after")
    def _check(self) -> "RiskCheckResult":
        if self.is_declined and self.decision is None:
            raise ValueError("decision is required when is_declined is True")
        return self
