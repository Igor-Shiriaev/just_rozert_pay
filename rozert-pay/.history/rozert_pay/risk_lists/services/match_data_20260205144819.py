from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from rozert_pay.common.metrics import track_duration
from rozert_pay.payment import models as payment_models
from rozert_pay.risk_lists.const import MatchFieldKey, ParticipationType
from rozert_pay.risk_lists.models import RiskListEntry


class MatchData(BaseModel):
    """
    Snapshot of transaction attributes used for risk-list matching
    """

    model_config = ConfigDict(frozen=True)

    customer_id: int | None
    email: str | None
    phone: str | None
    customer_name: str | None
    masked_pan: str | None
    customer_wallet_id: str | None
    ip: str | None
    provider_code: str | None

    @classmethod
    @track_duration("MatchData.from_transaction")
    def from_transaction(cls, trx: payment_models.PaymentTransaction) -> MatchData:
        ud = trx.user_data
        card = trx.customer_card
        return cls(
            customer_id=trx.customer_id,
            email=ud.email if ud else None,
            phone=ud.phone if ud else None,
            customer_name=ud.full_name
            if ud and ud.first_name and ud.last_name
            else None,
            masked_pan=card.masked_card if card else None,
            customer_wallet_id=card.unique_identity if card else None,
            provider_code=trx.system_type or None,
            ip=trx.extra.get("ip_address") if trx.extra else None,
        )

    @staticmethod
    def _norm_str(v: str | int) -> str:
        """Returns a stripped, lowercase representation of a non-null value."""
        return str(v).strip().lower()

    def _is_field_match(self, entry: RiskListEntry, field: MatchFieldKey) -> bool:
        """
        Performs a strict, case-insensitive comparison for a single field
        """
        entry_value: str | None = getattr(entry, field.value, None)
        trx_value: str | None = getattr(self, field.value, None)

        if entry_value is None or trx_value is None:
            return False

        return self._norm_str(entry_value) == self._norm_str(trx_value)

    @track_duration("MatchData.matches")
    def matches(self, entry: RiskListEntry) -> bool:
        """
        Performs matching based on the entry's participation type and match_fields.
        - GLOBAL: Uses AND logic (all fields must match).
        - MERCHANT/WALLET: Uses OR logic (at least one field must match).
        """

        attrs_match = (
            self._is_field_match(entry, MatchFieldKey(f)) for f in entry.match_fields
        )

        if entry.participation_type == ParticipationType.GLOBAL:
            return bool(entry.match_fields) and all(attrs_match)

        is_customer_match = (entry.customer_id is not None) and (
            self.customer_id == entry.customer_id
        )

        return is_customer_match or any(attrs_match)
