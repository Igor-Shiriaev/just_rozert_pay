


    @pytest.fixture
    def merchant_limit(self, merchant, wallet) -> MerchantLimit:
        wallet = WalletFactory.create(merchant=merchant)
        CurrencyWalletFactory.create(wallet=wallet)
        return MerchantLimitFactory.create(wallet=wallet, merchant=merchant, scope=MerchantLimitScope.WALLET)

    def create_currency_wallet_from_second_wallet(self, merchant) -> CurrencyWallet:
        wallet = WalletFactory.create(merchant=merchant)
        currency_wallet = CurrencyWalletFactory.create(wallet=wallet)
        return currency_wallet