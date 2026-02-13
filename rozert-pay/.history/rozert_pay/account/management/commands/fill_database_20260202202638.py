import contextlib
import traceback
from typing import Any, Generator

import factory  # type: ignore
from django.conf import settings
from django.core.management import BaseCommand, CommandParser
from django.db import IntegrityError
from pydantic import SecretStr
from rozert_pay.account import models as account_models
from rozert_pay.common.const import CallbackStatus, TransactionStatus
from rozert_pay.payment.controller_registry import PAYMENT_SYSTEMS
from rozert_pay.payment.models import Merchant, MerchantGroup, PaymentSystem, Wallet
from tests.factories import (
    CurrencyWalletFactory,
    DepositAccountFactory,
    MerchantFactory,
    MerchantGroupFactory,
    OutcomingCallbackFactory,
    PaymentTransactionFactory,
    WalletFactory,
)


class Command(BaseCommand):
    BETMASTER_MERCHANT_GROUP = "Betmaster (Test)"
    SANDBOX_MERCHANT = "Betmaster (Sandbox)"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--cleanup", action="store_true", help="Cleanup test data")
        parser.add_argument("--password", required=True)
        parser.add_argument("--email", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        self._create_user(options)
        self._create_system_user(options)
        self._create_systems_and_merchants(options)

    def _create_user(self, options: dict[str, Any]) -> MerchantGroup:
        DEFAULT_PASSWORD = options["password"]
        ADMIN_EMAIL = options["email"]

        admin, created = account_models.User.objects.get_or_create(
            email=ADMIN_EMAIL,
            defaults={
                "is_superuser": True,
                "is_staff": True,
            },
        )
        if created:
            admin.set_password(DEFAULT_PASSWORD)
            admin.save()
            self.stdout.write(self.style.SUCCESS("Superuser created"))
        else:
            self.stdout.write(self.style.WARNING("Superuser already exists"))

        try:
            mg = MerchantGroupFactory.create(
                name=self.BETMASTER_MERCHANT_GROUP, user=admin
            )
            self.stdout.write(self.style.SUCCESS("Merchant group created"))
        except IntegrityError:
            mg = MerchantGroup.objects.get(name=self.BETMASTER_MERCHANT_GROUP)
            self.stdout.write(self.style.WARNING("Merchant group already exists"))

        try:
            sandbox_merchant = MerchantFactory.create(
                name=self.SANDBOX_MERCHANT,
                merchant_group=mg,
                sandbox=True,
            )
            self.stdout.write(self.style.SUCCESS("Sandbox merchant created"))
        except IntegrityError:
            traceback.print_exc()
            sandbox_merchant = Merchant.objects.get(name=self.SANDBOX_MERCHANT)
            self.stdout.write(self.style.WARNING("Sandbox merchant already exists"))

        sandbox_merchant.login_users.add(admin)
        self.stdout.write(self.style.SUCCESS("Admin added to merchant"))
        return mg

    def _create_system_user(self, options: dict[str, Any]) -> None:
        user, created = account_models.User.objects.get_or_create(
            email=settings.SYSTEM_USER_EMAIL,
            defaults={
                "is_staff": True,
                "is_superuser": False,
                "first_name": "Rozert",
                "last_name": "System",
            },
        )
        if created:
            user.set_unusable_password()
            user.save()
            self.stdout.write(self.style.SUCCESS("System user created"))
        else:
            self.stdout.write(self.style.WARNING("System user already exists"))

    def _create_systems_and_merchants(self, options: dict[str, Any]) -> None:
        for type, cfg in PAYMENT_SYSTEMS.items():
            try:
                system, _ = PaymentSystem.objects.get_or_create(
                    name=cfg["name"],
                    type=type,
                )
            except IntegrityError:
                system = PaymentSystem.objects.get(
                    slug=PaymentSystem.make_slug(cfg["name"])
                )

            sandbox_merchant = Merchant.objects.get(name=self.SANDBOX_MERCHANT)

            sandbox_creds = cfg["controller"].default_credentials.model_dump()
            for k, v in sandbox_creds.items():
                if isinstance(v, SecretStr):
                    sandbox_creds[k] = v.get_secret_value()

            Wallet.objects.get_or_create(
                merchant=sandbox_merchant,
                system=system,
                defaults={"credentials_encrypted": sandbox_creds},
            )

    def _fill_dummy_data(self, merchants: list[Merchant]) -> None:
        assert not settings.IS_PRODUCTION
        for merchant in merchants:
            for i in range(5):
                w = WalletFactory.create(merchant=merchant)

                for i in range(20):
                    DepositAccountFactory.create(wallet=w)

                for currency in ["USD", "EUR", "RUB", "MXN"]:
                    currency_wallet = CurrencyWalletFactory.create(
                        wallet=w, currency=currency
                    )
                    for status in TransactionStatus.values:
                        decline_reason = decline_code = None
                        if status == TransactionStatus.FAILED:
                            decline_reason = factory.Faker("sentence")
                            decline_code = factory.Faker(
                                "random_int", min=1000, max=9999
                            )

                        for j in range(5):
                            trx = PaymentTransactionFactory.create(
                                wallet=currency_wallet,
                                currency=currency,
                                amount=factory.Faker("random_int", min=1, max=1000),
                                status=status,
                                decline_reason=decline_reason,
                                decline_code=decline_code,
                            )

                            for status in CallbackStatus.values:
                                OutcomingCallbackFactory.create(
                                    transaction=trx,
                                    status=status,
                                )

        self.stdout.write(self.style.SUCCESS("Wallets and transactions created"))

    @contextlib.contextmanager
    def handle_error(self) -> Generator[None, None, bool]:  # type: ignore[return]
        try:
            yield
        except Exception as e:
            self.log_error(e)
            return False

    def log_error(self, e: Exception) -> None:
        self.stdout.write(self.style.ERROR(str(e)))
