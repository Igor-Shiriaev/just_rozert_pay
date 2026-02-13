from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rozert_pay.limits.const import LimitPeriod, LimitType
from rozert_pay.limits.models.common import LimitCategory
from rozert_pay.limits.models.merchant_limits import (
    GlobalRiskMerchantLimit,
    MerchantLimit,
    MerchantLimitScope,
)
from rozert_pay.payment.models import Merchant, Wallet
from tests.factories import MerchantLimitFactory


@pytest.mark.django_db
class TestGlobalRiskMerchantLimitModel:
    def test_global_risk_merchant_limit_manager_filters_correctly(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        risk_limit = MerchantLimitFactory.create(
            merchant=None,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
        )
        global_risk_limit = MerchantLimitFactory.create(
            merchant=None,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
        )
        business_limit = MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.BUSINESS,
            scope=MerchantLimitScope.MERCHANT,
        )

        global_risk_limits = GlobalRiskMerchantLimit.objects.all()

        assert global_risk_limits.count() == 1
        assert global_risk_limit.id in [limit.id for limit in global_risk_limits]
        assert risk_limit.id not in [limit.id for limit in global_risk_limits]
        assert business_limit.id not in [limit.id for limit in global_risk_limits]

    def test_global_risk_limit_created_via_proxy_model(self, wallet: Wallet) -> None:
        global_risk_limit = GlobalRiskMerchantLimit.objects.create(
            merchant=None,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
            period=LimitPeriod.ONE_HOUR,
            active=True,
        )

        assert global_risk_limit.category == LimitCategory.GLOBAL_RISK
        assert GlobalRiskMerchantLimit.objects.filter(id=global_risk_limit.id).exists()
        assert MerchantLimit.objects.filter(id=global_risk_limit.id).exists()

    def test_global_risk_limit_queryset_excludes_other_categories(
        self, merchant: Merchant, wallet: Wallet
    ) -> None:
        MerchantLimitFactory.create(
            merchant=None,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
        )
        MerchantLimitFactory.create(
            merchant=merchant,
            category=LimitCategory.BUSINESS,
            scope=MerchantLimitScope.MERCHANT,
        )

        assert GlobalRiskMerchantLimit.objects.count() == 0


@pytest.mark.django_db
class TestGlobalRiskMerchantLimitValidation:
    def test_global_risk_limit_requires_wallet_scope(self, merchant: Merchant) -> None

        with pytest.raises(
            ValidationError,
            match="Scope must be 'wallet' for global risk limit and wallet must be set",
        ):
            invalid_limit = MerchantLimitFactory.build(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.MERCHANT,
            wallet=None,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
            period=LimitPeriod.ONE_HOUR,
        )

    def test_global_risk_limit_requires_wallet_to_be_set(self) -> None:
        invalid_limit = MerchantLimitFactory.build(
            merchant=None,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=None,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
            period=LimitPeriod.ONE_HOUR,
        )

        with pytest.raises(
            ValidationError,
            match="Scope must be 'wallet' for global risk limit and wallet must be set",
        ):
            invalid_limit.clean()

    def test_global_risk_limit_with_merchant_scope_and_no_wallet(
        self, merchant: Merchant
    ) -> None:
        invalid_limit = MerchantLimitFactory.build(
            merchant=merchant,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.MERCHANT,
            wallet=None,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
            period=LimitPeriod.ONE_HOUR,
        )

        with pytest.raises(
            ValidationError,
            match="Scope must be 'wallet' for global risk limit and wallet must be set",
        ):
            invalid_limit.clean()

    def test_global_risk_limit_valid_with_wallet_scope_and_wallet(
        self, wallet: Wallet
    ) -> None:
        valid_limit = MerchantLimitFactory.build(
            merchant=None,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
            period=LimitPeriod.ONE_HOUR,
        )

        valid_limit.clean()
        valid_limit.save()

        assert valid_limit.id is not None
        assert valid_limit.category == LimitCategory.GLOBAL_RISK
        assert valid_limit.scope == MerchantLimitScope.WALLET
        assert valid_limit.wallet == wallet

    def test_risk_limit_not_affected_by_global_risk_validation(
        self, merchant: Merchant
    ) -> None:
        risk_limit = MerchantLimitFactory.build(
            merchant=merchant,
            category=LimitCategory.RISK,
            scope=MerchantLimitScope.MERCHANT,
            wallet=None,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
            period=LimitPeriod.ONE_HOUR,
        )

        risk_limit.clean()
        risk_limit.save()

        assert risk_limit.id is not None

    def test_business_limit_not_affected_by_global_risk_validation(
        self, merchant: Merchant
    ) -> None:
        business_limit = MerchantLimitFactory.build(
            merchant=merchant,
            category=LimitCategory.BUSINESS,
            scope=MerchantLimitScope.MERCHANT,
            wallet=None,
            limit_type=LimitType.MIN_AMOUNT_SINGLE_OPERATION,
            min_amount=Decimal("10.00"),
            period=LimitPeriod.ONE_HOUR,
        )

        business_limit.clean()
        business_limit.save()

        assert business_limit.id is not None

    def test_global_risk_limit_with_all_required_fields(self, wallet: Wallet) -> None:
        valid_limit = MerchantLimitFactory.create(
            merchant=None,
            category=LimitCategory.GLOBAL_RISK,
            scope=MerchantLimitScope.WALLET,
            wallet=wallet,
            limit_type=LimitType.MAX_AMOUNT_SINGLE_OPERATION,
            max_amount=Decimal("1000.00"),
            period=LimitPeriod.ONE_HOUR,
            active=True,
            is_critical=True,
        )

        assert valid_limit.id is not None
        assert valid_limit.category == LimitCategory.GLOBAL_RISK
        assert valid_limit.scope == MerchantLimitScope.WALLET
        assert valid_limit.wallet == wallet
        assert valid_limit.max_amount == Decimal("1000.00")
