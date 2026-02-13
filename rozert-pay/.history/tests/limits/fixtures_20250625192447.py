import pytest
from rozert_pay.limits.models import MerchantLimit, MerchantLimitScope
from rozert_pay.payment.models import CurrencyWallet
from tests.factories import (
    MerchantLimitFactory,
    WalletFactory,
    CurrencyWalletFactory,
)


@pytest.fixture
def merchant_scope_limit(merchant) -> MerchantLimit:
    wallet = WalletFactory.create(merchant=merchant)
    CurrencyWalletFactory.create(wallet=wallet)
    return MerchantLimitFactory.create(wallet=wallet, merchant=merchant, scope=MerchantLimitScope.MERCHANT)


@pytest.fixture
def merchant_wallet_scope_limit(merchant, wallet) -> MerchantLimit:
    wallet = WalletFactory.create(merchant=merchant)
    CurrencyWalletFactory.create(wallet=wallet)
    return MerchantLimitFactory.create(wallet=wallet, merchant=merchant, scope=MerchantLimitScope.WALLET)


def create_currency_wallet_from_second_wallet(merchant) -> CurrencyWallet:
    wallet = WalletFactory.create(merchant=merchant)
    currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
    return currency_wallet
