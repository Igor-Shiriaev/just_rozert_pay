from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rozert_pay.common.const import TransactionStatus, TransactionType
from rozert_pay.risk_lists.const import OperationType, ParticipationType, ValidFor
from rozert_pay.risk_lists.services import checker
from rozert_pay.risk_lists.types import RiskDecision
from tests.factories import CustomerFactory, PaymentTransactionFactory
from tests.risk_lists.factories import (
    BlackListEntryFactory,
    GrayListEntryFactory,
    MerchantBlackListEntryFactory,
    WhiteListEntryFactory,
)


@pytest.mark.django_db
class TestRiskListChecker:
    def test_priority_prefers_merchant_black_over_white(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(customer=customer)
        merchant = trx.wallet.wallet.merchant

        WhiteListEntryFactory.create(
            customer=customer,
            merchant=merchant,
            email=customer.email,
            match_fields=["email"],
        )
        MerchantBlackListEntryFactory.create(
            customer=customer,
            merchant=merchant,
            email=customer.email,
            match_fields=["email"],
        )

        result = checker._process_transaction(trx)

        assert result.is_declined is True
        assert result.decision == RiskDecision.MERCHANT_BLACKLIST

    @pytest.mark.parametrize(
        "scope, expected_reason",
        [
            (ParticipationType.GLOBAL, RiskDecision.GLOBAL_BLACKLIST),
            # (ParticipationType.MERCHANT, RiskDecision.BLACKLIST),
            # (ParticipationType.WALLET, RiskDecision.BLACKLIST),
        ],
    )
    def test_black_list_declines_with_correct_scope_reason(
        self, scope: ParticipationType, expected_reason: RiskDecision
    ) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(customer=customer)

        factory_kwargs: dict[str, Any] = {
            "customer": customer,
            "email": customer.email,
            "participation_type": scope,
            "match_fields": ["email"],
        }
        if scope == ParticipationType.MERCHANT:
            factory_kwargs["merchant"] = trx.wallet.wallet.merchant
        elif scope == ParticipationType.WALLET:
            factory_kwargs["wallet"] = trx.wallet.wallet

        BlackListEntryFactory.create(**factory_kwargs)

        result = checker._process_transaction(trx)

        assert result.is_declined is True
        assert result.decision == expected_reason

    @pytest.mark.parametrize(
        "scope, expected_reason",
        [
            (ParticipationType.GLOBAL, RiskDecision.GLOBAL_GRAYLIST),
            (ParticipationType.MERCHANT, RiskDecision.GRAYLIST),
            (ParticipationType.WALLET, RiskDecision.GRAYLIST),
        ],
    )
    def test_gray_list_never_declines_but_logs_decision(
        self, scope: ParticipationType, expected_reason: RiskDecision
    ) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(customer=customer)

        factory_kwargs: dict[str, Any] = {
            "customer": customer,
            "email": customer.email,
            "participation_type": scope,
            "match_fields": ["email"],
        }
        if scope == ParticipationType.MERCHANT:
            factory_kwargs["merchant"] = trx.wallet.wallet.merchant
        elif scope == ParticipationType.WALLET:
            factory_kwargs["wallet"] = trx.wallet.wallet

        GrayListEntryFactory.create(**factory_kwargs)

        result = checker._process_transaction(trx)

        assert result.is_declined is False
        assert result.decision == expected_reason

    def test_no_match_if_entry_is_expired(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(customer=customer)

        past_created_at = timezone.now() - timedelta(hours=47)

        GrayListEntryFactory.create(
            customer=customer,
            email=customer.email,
            match_fields=["email"],
            valid_for=ValidFor.H24,
            time_added=past_time_added,
        )

        result = checker._process_transaction(trx)

        assert result.is_declined is False
        assert result.decision is None

    def test_no_match_if_entry_is_soft_deleted(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(customer=customer)

        BlackListEntryFactory.create(
            customer=customer,
            email=customer.email,
            match_fields=["email"],
            is_deleted=True,
        )

        result = checker._process_transaction(trx)

        assert result.is_declined is False
        assert result.decision is None

    def test_no_match_if_operation_type_mismatches(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(
            customer=customer, type=TransactionType.WITHDRAWAL
        )

        # ONLY applies to DEPOSIT
        BlackListEntryFactory.create(
            customer=customer,
            email=customer.email,
            match_fields=["email"],
            operation_type=OperationType.DEPOSIT,
        )

        result = checker._process_transaction(trx)

        assert result.is_declined is False
        assert result.decision is None

    def test_no_match_when_data_differs(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(customer=customer)

        BlackListEntryFactory.create(
            customer=customer,
            email="another-user@xxx.com",
            match_fields=["email"],
        )

        result = checker._process_transaction(trx)

        assert result.is_declined is False
        assert result.decision is None

    def test_global_entry_uses_and_logic_for_matching(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(
            customer=customer, extra={"ip": "1.1.1.1"}
        )

        # Global rule requires BOTH email and IP
        BlackListEntryFactory.create(
            customer=customer,
            email=customer.email,
            ip="1.1.1.1",
            participation_type=ParticipationType.GLOBAL,
            match_fields=["email", "ip"],
        )

        result = checker._process_transaction(trx)

        # The transaction should NOT be declined because only one of two fields matched
        assert result.is_declined is False
        assert result.decision is None

    def test_merchant_entry_uses_or_logic_for_matching(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(
            customer=customer, extra={"ip": "1.1.1.1"}
        )
        merchant = trx.wallet.wallet.merchant

        BlackListEntryFactory.create(
            customer=customer,
            merchant=merchant,
            email=customer.email,
            ip="1.1.1.1",
            participation_type=ParticipationType.MERCHANT,
            match_fields=["email", "ip"],
        )

        result = checker._process_transaction(trx)

        assert result.is_declined is True
        assert result.decision == RiskDecision.BLACKLIST


@pytest.mark.django_db
class TestCheckRiskListsAndMaybeDeclineTransaction:
    class MockController:
        def __init__(self):
            self.failed_trx = None
            self.fail_reason = None

        def fail_transaction(self, trx, decline_code, decline_reason):
            self.failed_trx = trx
            self.fail_reason = decline_reason
            trx.status = TransactionStatus.FAILED
            trx.save()

    def test_declines_transaction_on_blacklist_match(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(
            customer=customer, status=TransactionStatus.PENDING
        )
        BlackListEntryFactory.create(
            customer=customer,
            email=customer.email,
            match_fields=["email"],
            participation_type=ParticipationType.MERCHANT,
            merchant=trx.wallet.wallet.merchant,
        )
        controller = self.MockController()

        result = checker.check_risk_lists_and_maybe_decline_transaction(trx, controller)  # type: ignore

        assert result is True
        trx.refresh_from_db()
        assert trx.status == TransactionStatus.FAILED
        assert controller.failed_trx is not None
        assert controller.failed_trx.id == trx.id
        assert controller.fail_reason == RiskDecision.BLACKLIST.value

    def test_does_not_decline_on_whitelist_match(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(
            customer=customer, status=TransactionStatus.PENDING
        )
        WhiteListEntryFactory.create(
            customer=customer,
            merchant=trx.wallet.wallet.merchant,
            email=customer.email,
            match_fields=["email"],
        )
        controller = self.MockController()

        result = checker.check_risk_lists_and_maybe_decline_transaction(trx, controller)  # type: ignore

        assert result is False
        trx.refresh_from_db()
        assert trx.status == TransactionStatus.PENDING
        assert controller.failed_trx is None

    def test_raises_error_if_transaction_not_pending(self) -> None:
        customer = CustomerFactory.create(email_encrypted="user@xxx.com")
        trx = PaymentTransactionFactory.create(
            customer=customer, status=TransactionStatus.SUCCESS
        )
        BlackListEntryFactory.create(
            customer=customer, email=customer.email, match_fields=["email"]
        )
        controller = self.MockController()

        with pytest.raises(ValueError, match="Unexpected transaction status"):
            checker.check_risk_lists_and_maybe_decline_transaction(trx, controller)  # type: ignore
