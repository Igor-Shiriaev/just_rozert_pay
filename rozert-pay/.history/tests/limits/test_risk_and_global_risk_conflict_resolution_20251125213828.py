from decimal import Decimal

import pytest
from rozert_pay.limits.const import LimitPeriod, LimitType
from rozert_pay.limits.models.common import LimitCategory
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit, MerchantLimitScope
from rozert_pay.limits.services.limits import (
    _resolve_risk_and_global_risk_limit_for_merchant_conflicts,
)
from rozert_pay.payment.models import Merchant, Wallet
from tests.factories import CustomerLimitFactory, MerchantLimitFactory, WalletFactory


@pytest.mark.django_db
class TestResolveRiskAndGlobalRiskLimitConflicts:
    def test_risk_limit_overrides_global_risk_limit_same_type(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        global_risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("5.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [risk_limit, global_risk_limit]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 1
        assert risk_limit in resolved_limits
        assert global_risk_limit not in resolved_limits

    def test_no_conflict_when_different_limit_types(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        global_risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [risk_limit, global_risk_limit]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 2
        assert risk_limit in resolved_limits
        assert global_risk_limit in resolved_limits

    def test_multiple_global_risk_limits_removed_when_matching_risk_limits_exist(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        risk_limit_1 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        risk_limit_2 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )
        global_risk_limit_1 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("5.00"),
        )
        global_risk_limit_2 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("2000.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            risk_limit_1,
            risk_limit_2,
            global_risk_limit_1,
            global_risk_limit_2,
        ]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 2
        assert risk_limit_1 in resolved_limits
        assert risk_limit_2 in resolved_limits
        assert global_risk_limit_1 not in resolved_limits
        assert global_risk_limit_2 not in resolved_limits

    def test_global_risk_limits_preserved_when_no_matching_risk_limits(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        global_risk_limit_1 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("5.00"),
        )
        global_risk_limit_2 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("2000.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            global_risk_limit_1,
            global_risk_limit_2,
        ]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 2
        assert global_risk_limit_1 in resolved_limits
        assert global_risk_limit_2 in resolved_limits

    def test_business_limits_not_affected_by_risk_conflict_resolution(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        global_risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("5.00"),
        )
        business_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.BUSINESS,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("20.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            risk_limit,
            global_risk_limit,
            business_limit,
        ]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 2
        assert risk_limit in resolved_limits
        assert business_limit in resolved_limits
        assert global_risk_limit not in resolved_limits

    def test_customer_limits_not_affected_by_risk_conflict_resolution(
        self, customer, merchant: Merchant, wallet: Wallet
    ) -> None:
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("15.00"),
        )
        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        global_risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("5.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            customer_limit,
            risk_limit,
            global_risk_limit,
        ]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 2
        assert customer_limit in resolved_limits
        assert risk_limit in resolved_limits
        assert global_risk_limit not in resolved_limits

    def test_merchant_scope_limits_not_affected_by_conflict_resolution(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.MERCHANT,
            wallet=None,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        global_risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("5.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [risk_limit, global_risk_limit]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 2
        assert risk_limit in resolved_limits
        assert global_risk_limit in resolved_limits

    def test_empty_limits_list(self) -> None:
        limits: list[CustomerLimit | MerchantLimit] = []
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert resolved_limits == []

    def test_only_risk_limits(self, merchant: Merchant, wallet: Wallet) -> None:
        risk_limit_1 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        risk_limit_2 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [risk_limit_1, risk_limit_2]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 2
        assert risk_limit_1 in resolved_limits
        assert risk_limit_2 in resolved_limits

    def test_only_global_risk_limits(self, merchant: Merchant, wallet: Wallet) -> None:
        global_risk_limit_1 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        global_risk_limit_2 = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            global_risk_limit_1,
            global_risk_limit_2,
        ]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 2
        assert global_risk_limit_1 in resolved_limits
        assert global_risk_limit_2 in resolved_limits

    def test_complex_scenario_with_multiple_limit_types(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        # Risk limits for wallet scope
        risk_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        risk_max_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )

        # Global risk limits (conflicting with risk limits)
        global_risk_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("5.00"),
        )
        global_risk_max_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("2000.00"),
        )

        # Global risk limit without conflicting risk limit
        global_risk_operations_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=10,
            period=LimitPeriod.ONE_HOUR,
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            risk_min_limit,
            risk_max_limit,
            global_risk_min_limit,
            global_risk_max_limit,
            global_risk_operations_limit,
        ]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 3
        assert risk_min_limit in resolved_limits
        assert risk_max_limit in resolved_limits
        assert global_risk_operations_limit in resolved_limits
        assert global_risk_min_limit not in resolved_limits
        assert global_risk_max_limit not in resolved_limits

    def test_different_wallets_no_conflict(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        second_wallet = WalletFactory.create(merchant=merchant)

        risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        global_risk_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=second_wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("5.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [risk_limit, global_risk_limit]
        resolved_limits = _resolve_risk_and_global_risk_limit_for_merchant_conflicts(
            limits
        )

        assert len(resolved_limits) == 2
        assert risk_limit in resolved_limits
        assert global_risk_limit in resolved_limits

