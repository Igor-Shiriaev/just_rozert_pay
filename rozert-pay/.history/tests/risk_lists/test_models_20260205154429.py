from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from rozert_pay.risk_lists.const import Scope, ValidFor
from tests.factories import CustomerFactory, MerchantFactory, WalletFactory
from tests.risk_lists.factories import (
    BlackListEntryFactory,
    GrayListEntryFactory,
    MerchantBlackListEntryFactory,
    WhiteListEntryFactory,
)


@pytest.mark.django_db
class TestRiskListEntryModel:
    def test_white_cannot_be_global_and_requires_reason(self):
        customer = CustomerFactory.create()
        # GLOBAL ban
        e = WhiteListEntryFactory.build(
            participation_type=Scope.GLOBAL,
            customer=customer,
        )
        with pytest.raises(ValidationError):
            e.clean()

        # reason
        e = WhiteListEntryFactory.build(
            customer=customer,
            reason="",
        )
        with pytest.raises(ValidationError):
            e.clean()

    def test_black_list_requires_reason(self):
        entry = BlackListEntryFactory.build(
            participation_type=Scope.MERCHANT,
            reason="",
            merchant=MerchantFactory(),
        )
        with pytest.raises(ValidationError, match="reason is mandatory"):
            entry.clean()

    def test_merchant_black_list_requires_reason(self):
        entry = MerchantBlackListEntryFactory.build(reason="")
        with pytest.raises(ValidationError, match="reason is mandatory"):
            entry.clean()

    @pytest.mark.parametrize(
        "participation_type, factory_kwargs, expected_error_match",
        [
            pytest.param(
                Scope.GLOBAL,
                {
                    "merchant": MerchantFactory.build(),
                    "customer": None,
                    "ip": "127.0.0.1",
                    "email": "test@example.com",
                },
                "For GLOBAL participation, 'merchant' must be empty",
                id="global_with_merchant_fails",
            ),
            pytest.param(
                Scope.GLOBAL,
                {
                    "wallet": WalletFactory.build(),
                    "customer": None,
                    "ip": "127.0.0.1",
                    "email": "test@example.com",
                },
                "For GLOBAL participation, 'wallet' must be empty",
                id="global_with_wallet_fails",
            ),
            pytest.param(
                Scope.MERCHANT,
                {"merchant": None},
                "'merchant' must be selected",
                id="merchant_without_merchant_fails",
            ),
            pytest.param(
                Scope.MERCHANT,
                {"merchant": MerchantFactory.build(), "wallet": WalletFactory.build()},
                "'wallet' must be empty",
                id="merchant_with_wallet_fails",
            ),
            pytest.param(
                Scope.WALLET,
                {"wallet": None},
                "'wallet' must be selected",
                id="wallet_without_wallet_fails",
            ),
            pytest.param(
                Scope.WALLET,
                {"wallet": WalletFactory.build(), "merchant": MerchantFactory.build()},
                "'merchant' must be empty",
                id="wallet_with_merchant_fails",
            ),
            pytest.param(
                Scope.MERCHANT,
                {
                    "merchant": MerchantFactory.build(),
                    "customer": None,
                },
                "Customer is required for Merchant participation",
                id="merchant_without_customer_fails",
            ),
            pytest.param(
                Scope.WALLET,
                {
                    "wallet": WalletFactory.build(),
                    "customer": None,
                },
                "Customer is required for Wallet participation",
                id="wallet_without_customer_fails",
            ),
        ],
    )
    def test_participation_scope_constraints(
        self,
        participation_type: Scope,
        factory_kwargs: dict[str, Any],
        expected_error_match: str,
    ) -> None:
        """
        Verifies validation constraints for different participation scopes.
        """
        with pytest.raises(ValidationError, match=expected_error_match):
            GrayListEntryFactory.build(
                participation_type=participation_type, **factory_kwargs
            ).clean()

    @pytest.mark.parametrize(
        "factory_cls",
        [
            BlackListEntryFactory,
            GrayListEntryFactory,
        ],
    )
    def test_global_black_or_gray_requires_two_identifying_fields(self, factory_cls):
        e = factory_cls.build(email="a@x.com", match_fields=["email"])
        with pytest.raises(ValidationError):
            e.clean()

    def test_save_sets_valid_for_defaults_and_flags(self):
        # WHITE> H24
        w = WhiteListEntryFactory.create()
        assert w.valid_for == ValidFor.H24

        # GRAY> PERMANENT
        g = GrayListEntryFactory.create()
        assert g.valid_for == ValidFor.PERMANENT
        assert g.expires_at is None

        # BLACK> PERMANENT
        b = BlackListEntryFactory.create()
        assert b.valid_for == ValidFor.PERMANENT
        assert b.expires_at is None

        # MERCHANT_BLACK> PERMANENT (MERCHANT)
        m = MerchantBlackListEntryFactory.create(
            participation_type=Scope.WALLET,
            wallet=WalletFactory.create(),
        )
        m.save()
        assert m.valid_for == ValidFor.PERMANENT
        assert m.scope == Scope.MERCHANT

    def test_soft_delete_and_delete(self):
        e = GrayListEntryFactory.create()
        with pytest.raises(ValueError):
            e.soft_delete(reason="")

        e.soft_delete(reason="no longer needed")
        assert e.is_deleted is True
        assert e.delete_reason == "no longer needed"

        e2 = GrayListEntryFactory.create()
        e2.delete(reason="cleanup")
        e2.refresh_from_db()
        assert e2.is_deleted is True
        assert e2.delete_reason == "cleanup"

    def test_set_expiration_h168_and_h720(self):
        base = datetime(2025, 1, 1, 12, 0, tzinfo=tz.utc)
        e1 = GrayListEntryFactory.build(valid_for=ValidFor.H168)
        e1.created_at = base
        e1.set_expiration()
        assert e1.expires_at == base + timedelta(hours=168)

        e2 = GrayListEntryFactory.build(valid_for=ValidFor.H720)
        e2.created_at = base
        e2.set_expiration()
        assert e2.expires_at == base + timedelta(hours=720)
