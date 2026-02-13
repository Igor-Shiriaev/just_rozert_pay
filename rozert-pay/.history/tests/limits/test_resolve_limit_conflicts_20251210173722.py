from decimal import Decimal

import pytest
from rozert_pay.limits.const import LimitPeriod, LimitType
from rozert_pay.limits.models.customer_limits import CustomerLimit
from rozert_pay.limits.models.merchant_limits import MerchantLimit, MerchantLimitScope
from rozert_pay.limits.services.limits import (
    _resolve_customer_and_merchant_limit_conflicts,
)
from rozert_pay.payment.models import Merchant
from tests.factories import CustomerLimitFactory, MerchantLimitFactory


@pytest.mark.django_db
class TestResolveLimitConflicts:
    def test_no_conflicts_no_customer_limits(self, merchant: Merchant):
        merchant_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        merchant_max_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )
        merchant_other_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=5,
        )

        limits = [merchant_min_limit, merchant_max_limit, merchant_other_limit]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)  # type: ignore[arg-type]

        assert len(resolved_limits) == 3
        assert len(filtered) == 0
        assert merchant_min_limit in resolved_limits
        assert merchant_max_limit in resolved_limits
        assert merchant_other_limit in resolved_limits

    def test_customer_min_operation_limit_removes_merchant_min_limit(
        self, customer, merchant
    ):
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("20.00"),
            max_operation_amount=None,
        )
        merchant_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        merchant_max_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            customer_limit,
            merchant_min_limit,
            merchant_max_limit,
        ]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)

        assert len(resolved_limits) == 2
        assert customer_limit in resolved_limits
        assert merchant_max_limit in resolved_limits
        assert merchant_min_limit not in resolved_limits

    def test_customer_max_operation_limit_removes_merchant_max_limit(
        self, customer, merchant
    ):
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            max_operation_amount=Decimal("500.00"),
            min_operation_amount=None,
        )
        merchant_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        merchant_max_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            customer_limit,
            merchant_min_limit,
            merchant_max_limit,
        ]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)

        assert len(resolved_limits) == 2
        assert customer_limit in resolved_limits
        assert merchant_min_limit in resolved_limits
        assert merchant_max_limit not in resolved_limits

    def test_both_customer_limits_remove_both_merchant_limits(self, customer, merchant):
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("20.00"),
            max_operation_amount=Decimal("500.00"),
        )
        merchant_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        merchant_max_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )
        merchant_other_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=5,
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            customer_limit,
            merchant_min_limit,
            merchant_max_limit,
            merchant_other_limit,
        ]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)

        assert len(resolved_limits) == 2
        assert customer_limit in resolved_limits
        assert merchant_other_limit in resolved_limits
        assert merchant_min_limit not in resolved_limits
        assert merchant_max_limit not in resolved_limits

    def test_multiple_customer_limits_same_type(self, merchant):
        customer1 = CustomerLimitFactory.create(
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("15.00"),
        )
        customer2 = CustomerLimitFactory.create(
            period=LimitPeriod.TWENTY_FOUR_HOURS,
            min_operation_amount=Decimal("25.00"),
        )
        merchant_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            customer1,
            customer2,
            merchant_min_limit,
        ]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)

        assert len(resolved_limits) == 2
        assert customer1 in resolved_limits
        assert customer2 in resolved_limits
        assert merchant_min_limit not in resolved_limits

    def test_customer_limits_without_operation_amounts_dont_affect_merchant_limits(
        self, customer, merchant
    ):
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            max_successful_operations=3,
            total_successful_amount=Decimal("2000.00"),
            min_operation_amount=None,
            max_operation_amount=None,
        )
        merchant_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        merchant_max_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            customer_limit,
            merchant_min_limit,
            merchant_max_limit,
        ]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)

        assert len(resolved_limits) == 3
        assert customer_limit in resolved_limits
        assert merchant_min_limit in resolved_limits
        assert merchant_max_limit in resolved_limits

    def test_non_conflicting_merchant_limits_preserved(self, customer, merchant):
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("20.00"),
            max_operation_amount=Decimal("500.00"),
        )
        merchant_deposits_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=5,
        )
        merchant_decline_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_OVERALL_DECLINE_PERCENT,
            max_overall_decline_percent=Decimal("25.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            customer_limit,
            merchant_deposits_limit,
            merchant_decline_limit,
        ]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)

        assert len(resolved_limits) == 3
        assert customer_limit in resolved_limits
        assert merchant_deposits_limit in resolved_limits
        assert merchant_decline_limit in resolved_limits

    def test_wallet_scope_merchant_limits_also_removed(
        self, customer, merchant, wallet
    ):
        customer_limit = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("20.00"),
        )
        merchant_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            scope=MerchantLimitScope.WALLET,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            customer_limit,
            merchant_min_limit,
        ]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)

        assert len(resolved_limits) == 1
        assert customer_limit in resolved_limits
        assert merchant_min_limit not in resolved_limits

    def test_empty_limits_list(self):
        limits: list[CustomerLimit | MerchantLimit] = []
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)
        assert resolved_limits == []

    def test_only_customer_limits(self, customer):
        customer_limit1 = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("20.00"),
        )
        customer_limit2 = CustomerLimitFactory.create(
            period=LimitPeriod.TWENTY_FOUR_HOURS,
            max_operation_amount=Decimal("500.00"),
        )

        limits = [customer_limit1, customer_limit2]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)  # type: ignore[arg-type]

        assert len(resolved_limits) == 2
        assert customer_limit1 in resolved_limits
        assert customer_limit2 in resolved_limits

    def test_complex_scenario_mixed_limits(self, customer, merchant, wallet):
        # Customer limits with operation amounts
        customer_limit1 = CustomerLimitFactory.create(
            customer=customer,
            period=LimitPeriod.ONE_HOUR,
            min_operation_amount=Decimal("20.00"),
            max_successful_operations=3,
        )
        customer_limit2 = CustomerLimitFactory.create(
            period=LimitPeriod.TWENTY_FOUR_HOURS,
            max_operation_amount=Decimal("500.00"),
            total_successful_amount=Decimal("2000.00"),
        )

        # Customer limit without operation amounts
        customer_limit3 = CustomerLimitFactory.create(
            period=LimitPeriod.ONE_HOUR,
            max_failed_operations=5,
            min_operation_amount=None,
            max_operation_amount=None,
        )

        # Conflicting merchant limits (should be removed)
        merchant_min_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
        )
        merchant_max_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            scope=MerchantLimitScope.WALLET,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
        )

        # Non-conflicting merchant limits (should be preserved)
        merchant_deposits_limit = MerchantLimitFactory.create(
            merchant=merchant,
            scope=MerchantLimitScope.MERCHANT,
            limit_type=LimitType.MAX_SUCCESSFUL_DEPOSITS,
            max_operations=10,
        )
        merchant_ratio_limit = MerchantLimitFactory.create(
            merchant=merchant,
            wallet=wallet,
            scope=MerchantLimitScope.WALLET,
            limit_type=LimitType.MAX_WITHDRAWAL_TO_DEPOSIT_RATIO,
            max_ratio=Decimal("75.00"),
        )

        limits: list[CustomerLimit | MerchantLimit] = [
            customer_limit1,
            customer_limit2,
            customer_limit3,
            merchant_min_limit,
            merchant_max_limit,
            merchant_deposits_limit,
            merchant_ratio_limit,
        ]
        resolved_limits, filtered = _resolve_customer_and_merchant_limit_conflicts(limits)

        assert len(resolved_limits) == 5

        # Customer limits should all be preserved
        assert customer_limit1 in resolved_limits
        assert customer_limit2 in resolved_limits
        assert customer_limit3 in resolved_limits

        # Conflicting merchant limits should be removed
        assert merchant_min_limit not in resolved_limits
        assert merchant_max_limit not in resolved_limits

        # Non-conflicting merchant limits should be preserved
        assert merchant_deposits_limit in resolved_limits
        assert merchant_ratio_limit in resolved_limits
