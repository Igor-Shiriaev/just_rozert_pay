import logging

from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.payment import types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import deposit_services, withdraw_services
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.ilixium.ilixium_client import (
    IlixiumClient,
    IlixiumSandboxClient,
)

logger = logging.getLogger(__name__)


class IlixiumController(
    base_controller.PaymentSystemController[IlixiumClient, IlixiumSandboxClient]
):
    client_cls = IlixiumClient
    sandbox_client_cls = IlixiumSandboxClient

    def _run_deposit(
        self, trx_id: types.TransactionId, client: IlixiumClient | IlixiumSandboxClient
    ) -> None:
        with deposit_services.initiate_deposit(
            client=client,
            trx_id=types.TransactionId(trx_id),
            controller=self,
            allow_immediate_fail=True,
        ):
            pass

    def _run_withdraw(
        self, trx: PaymentTransaction, client: IlixiumClient | IlixiumSandboxClient
    ) -> None:
        with withdraw_services.execute_withdraw_query_and_schedule_status_checks(
            trx=trx,
            controller=self,
        ):
            pass

    def handle_redirect(
        self,
        request: Request,
    ) -> Response:
        return deposit_services.handle_deposit_redirect(
            request=request,
            controller=self,
        )

    def _parse_callback(
        self, cb: IncomingCallback
    ) -> RemoteTransactionStatus | Response:
        return Response({})

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        return False


ilixium_controller = IlixiumController(
    payment_system=const.PaymentSystemType.ILIXIUM,
    default_credentials={
        "merchant_id": "fake",
        "account_id": "fake",
        "api_key": "fake",
        "withdrawal_api_key": "fake",
        "withdrawal_merchant_name": "fake",
    },
)
