from rozert_pay.common import const
from rozert_pay.common.const import TransactionStatus
from rozert_pay.payment.models import Merchant
from rozert_pay.payment.services.base_classes import BaseSandboxClientMixin
from tests.factories import PaymentTransactionFactory


class TestBaseSandboxClientMixin:
    def test_post_deposit_request(self, db, merchant: Merchant) -> None:
        trx = PaymentTransactionFactory.create(
            wallet__wallet__merchant=merchant,
            wallet__wallet__system__type=const.PaymentSystemType.STP_SPEI,
        )
        merchant.sandbox = True
        merchant.save()

        assert trx.status == TransactionStatus.PENDING

        BaseSandboxClientMixin(trx.id).post_deposit_request()

        trx.refresh_from_db()
        assert trx.status == TransactionStatus.SUCCESS
