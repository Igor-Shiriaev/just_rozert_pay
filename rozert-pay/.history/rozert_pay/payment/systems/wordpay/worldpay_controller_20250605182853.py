import datetime
import json
import logging
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Any, Dict, cast

from bm.datatypes import Money
from django.db import transaction
from django.http import QueryDict
from django.shortcuts import redirect
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rozert_pay.common import const
from rozert_pay.payment import entities, types
from rozert_pay.payment.entities import RemoteTransactionStatus
from rozert_pay.payment.models import IncomingCallback, PaymentTransaction
from rozert_pay.payment.services import (
    db_services,
    deposit_services,
    transaction_processing,
)
from rozert_pay.payment.systems import base_controller
from rozert_pay.payment.systems.wordpay.worldpay_client import (
    WorldpayClient,
    WorldpayCreds,
    WorldpaySandboxClient,
)
from rozert_pay.payment.systems.appex.appex_const import APPEX_FOREIGN_MD, APPEX_PARES

logger = logging.getLogger(__name__)


def xml_to_dict(xml_string: str) -> Dict[str, Any]:
    """Parse XML string into a dictionary."""
    try:
        root = ET.fromstring(xml_string)
        result = {}
        
        def parse_element(element: ET.Element) -> Any:
            if len(element) == 0:
                return element.text
            else:
                child_dict = {}
                for child in element:
                    if child.tag in child_dict:
                        if not isinstance(child_dict[child.tag], list):
                            child_dict[child.tag] = [child_dict[child.tag]]
                        child_dict[child.tag].append(parse_element(child))
                    else:
                        child_dict[child.tag] = parse_element(child)
                return child_dict
        
        result[root.tag] = parse_element(root)
        return result
    except ET.ParseError as e:
        logger.error(f"Failed to parse XML: {e}")
        return {}


class WorldpayController(
    base_controller.PaymentSystemController[WorldpayClient, WorldpaySandboxClient]
):
    client_cls = WorldpayClient
    sandbox_client_cls = WorldpaySandboxClient

    def _run_deposit(
        self, trx_id: int, client: WorldpaySandboxClient | WorldpayClient
    ) -> None:
        deposit_services.initiate_deposit(
            client=client,
            trx_id=types.TransactionId(trx_id),
        )

    def _run_withdraw(
        self, trx: PaymentTransaction, client: WorldpaySandboxClient | WorldpayClient
    ) -> None:
        self._execute_withdraw_query(trx, client)

        with transaction.atomic():
            transaction_processing.schedule_periodic_status_checks(
                trx=db_services.get_transaction(trx_id=trx.id, for_update=True),
                until=timezone.now()
                + datetime.timedelta(seconds=trx.system.withdrawal_allowed_ttl_seconds),
                schedule_check_immediately=True,
            )

    def _parse_callback(self, cb: IncomingCallback) -> RemoteTransactionStatus:
        # Parse XML body into dictionary
        data = xml_to_dict(cb.body)
        
        # Extract transaction details from parsed XML
        # Adjust these field names based on your actual XML structure
        trx = db_services.get_transaction_by_callback(cb)
        
        # Default values
        status = entities.OperationStatus.PENDING
        id_in_payment_system = None
        remote_amount = None
        
        # Parse status from XML data - adjust field names as needed
        if 'status' in data:
            xml_status = data.get('status', '').lower()
            if xml_status == 'success' or xml_status == 'ok':
                status = entities.OperationStatus.SUCCESS
            elif xml_status == 'failed' or xml_status == 'error':
                status = entities.OperationStatus.FAILED
        
        # Extract ID and amount - adjust field names based on actual XML structure
        if 'transactionId' in data:
            id_in_payment_system = data['transactionId']
        elif 'id' in data:
            id_in_payment_system = data['id']
            
        if 'amount' in data:
            try:
                remote_amount = float(data['amount'])
            except (ValueError, TypeError):
                remote_amount = None

        return entities.RemoteTransactionStatus(
            operation_status=status,
            id_in_payment_system=id_in_payment_system,
            raw_data=data,
            remote_amount=remote_amount,
            transaction_id=trx.id,
        )

    def _is_callback_signature_valid(self, cb: IncomingCallback) -> bool:
        if "json" in cb.headers.get("content-type", ""):
            data = json.loads(cb.body)
        else:
            data = QueryDict(cb.body)

        if "MD" in data and "PaRes" in data:
            # no signature check for PaRes 3d response
            return True

        signature_from_request = data["signature"]
        force_fields = None

        if data.get("percentplus"):
            # deposit success confirmation
            signature_keys = (
                "amount, amountcurr, currency, number, description, "
                "trtype, payamount, percentplus, percentminus, account, "
                "paytoken, backURL, transID, datetime".split(", ")
            )
        elif data.get("operator"):
            # withdraw confirmation
            signature_keys = (
                "account, operator, params, amount, "
                "amountcurr, number, transID, datetime".split(", ")
            )
        elif data.get("opertype") == "pay":
            # deposit confirmation
            signature_keys = (
                "PANmasked, cardholder, opertype, amount, amountcurr, "
                "number, description, trtype, account, cf1, cf2, cf3, "
                "paytoken, backURL, transID, datetime".split(", ")
            )
            force_fields = ["cardholder"]
        elif data.get("status") in ("OK", "error"):
            signature_keys = (
                "account, amount, amountcurr, number, transID, datetime, status".split(
                    ", "
                )
            )
        else:
            raise RuntimeError(f"Unknown format for signature validation! {data}")

        def signature_for_creds_callable(creds: WorldpayCreds) -> str:
            return self.client_cls._sign_payload(
                payload=data,
                fields_to_sign=signature_keys,
                secret1=creds.secret1,
                secret2=creds.secret2,
                force_fields=force_fields,
            )

        return transaction_processing.validate_signature_for_callback(
            payment_system=self.payment_system,
            creds_cls=WorldpayCreds,
            signature_from_request=signature_from_request,
            signature_for_creds_callable=signature_for_creds_callable,
        )

    def handle_redirect(
        self,
        request: Request,
    ) -> Response:
        transaction_id = request.query_params["transaction_id"]
        trx: PaymentTransaction = PaymentTransaction.objects.select_for_update().get(
            uuid=transaction_id
        )
        if trx.extra.get(APPEX_PARES):
            # Worldpay fails transaction in case we send duplicate deposit finalize.
            # So if pares has been already received, don't create second finalization task.
            logger.warning(
                "duplicated appex pares callback",
                extra={
                    "_request": request.POST,
                    "_trx": trx,
                    "_trx_uuid": trx.uuid,
                },
            )
            return Response("OK")

        trx.extra[APPEX_PARES] = request.POST["PaRes"]
        trx.extra[APPEX_FOREIGN_MD] = request.POST["MD"]
        trx.save(update_fields=["extra", "updated_at"])

        self.create_log(
            trx_id=trx.id,
            event_type=const.EventType.CUSTOMER_REDIRECT_RECEIVED,
            description="Customer redirect received",
            extra={
                "request": request.POST,
                "trx_uuid": trx.uuid,
            },
        )

        self.run_deposit_finalization(
            trx_id=trx.id,
        )
        assert trx.redirect_url
        return cast(Response, redirect(trx.redirect_url))

    def build_callback_response(self, cb: IncomingCallback) -> Response:
        data = QueryDict(cb.body)
        assert cb.transaction_id

        is_operation_confirmation = data.get("opertype") == "pay"
        if is_operation_confirmation:
            assert cb.transaction and cb.transaction.id_in_payment_system
            return Response(str(cb.transaction.id_in_payment_system))

        return super().build_callback_response(cb)


appex_controller = WorldpayController(
    payment_system=const.PaymentSystemType.APPEX,
    default_credentials={
        "account": "fake_account",
        "secret1": "fake_secret1",
        "secret2": "fake",
        "host": "http://appex",
        "operator": None,
    },
)
