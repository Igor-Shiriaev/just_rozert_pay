import hashlib
import json
import logging
import typing as ty
from uuid import UUID

import requests
from currency.utils import to_minor_units
from pydantic import BaseModel, SecretStr
from rozert_pay.common import const
from rozert_pay.common.helpers.validation_mexico import validate_clabe
from rozert_pay.payment import entities, models, types
from rozert_pay.payment.services import base_classes, errors
from rozert_pay.payment.services.errors import SafeFlowInterruptionError
from rozert_pay.payment.services.incoming_callbacks import get_rozert_callback_url
from rozert_pay.payment.systems.muwe_spei import (
    bank_service,
    muwe_spei_const,
    muwe_spei_helpers,
    tasks,
)

logger = logging.getLogger(__name__)


class MuweSpeiCreds(BaseModel):
    base_api_url: str  # https://test.sipelatam.mx or https://pay.sipelatam.mx
    app_id: str
    mch_id: str
    api_key: SecretStr


class MuweSpeiClient(base_classes.BasePaymentClient[MuweSpeiCreds]):
    payment_system_name = const.PaymentSystemType.MUWE_SPEI
    credentials_cls = MuweSpeiCreds

    _operation_status_by_foreign_status = muwe_spei_const.STATUS_MAP

    @classmethod
    def create_deposit_instruction(
        cls,
        *,
        external_customer_id: types.ExternalCustomerId,
        wallet: models.Wallet,
        creds: types.T_Credentials,
        notify_url: str,
    ) -> str | errors.Error:
        """
        Generate CLABE for customer deposits via MUWE API.

        Args:
            external_customer_id: Customer ID (for idempotency via uid)
            wallet: Customer wallet
            creds: MUWE API credentials
            notify_url: Webhook URL for deposit notifications

        Returns:
            CLABE (reference) or Error
        """
        muwe_creds = ty.cast(MuweSpeiCreds, creds)

        uid = str(UUID(external_customer_id).hex)

        mch_order_no = f"CLABE_{external_customer_id}_{wallet.id}"
        hash_32 = hashlib.sha256(mch_order_no.encode("utf-8")).hexdigest()[:32]
        payload = {
            "appId": muwe_creds.app_id,
            "mchId": muwe_creds.mch_id,
            "mchOrderNo": hash_32,
            "nonceStr": muwe_spei_helpers.generate_nonce_str(),
            "notifyUrl": notify_url,
            "payType": muwe_spei_const.PAYMENT_TYPE_SPEI,
            "currency": muwe_spei_const.CURRENCY_MXN,
            "channelInfo": "",
            "uid": uid,
        }

        payload["sign"] = muwe_spei_helpers.calculate_signature(
            payload, muwe_creds.api_key.get_secret_value()
        )

        response = cls._make_request(
            method="POST",
            url_path=muwe_spei_const.API_ENDPOINT_COLLECTION_CREATE,
            creds=muwe_creds,
            json_data=payload,
            headers={"tmId": "sipe_mx"},
        )

        if not response["success"]:
            return errors.Error(
                f"Failed to create deposit instruction: {response.get('error', 'Unknown error')}"
            )

        reference = response["data"].get("reference")
        if not reference:
            return errors.Error("No reference (CLABE) in API response")

        try:
            validate_clabe(reference)
        except ValueError:
            return errors.Error(f"Invalid CLABE format: {reference}")

        return reference

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        user_data = self.trx.user_data
        assert user_data, "User data is required for withdrawal"

        if not self.trx.customer_external_account:
            raise SafeFlowInterruptionError(
                "No customer external account found for withdrawal"
            )

        external_account = self.trx.customer_external_account
        clabe = external_account.unique_account_number

        try:
            validate_clabe(clabe)
        except ValueError:
            raise SafeFlowInterruptionError(f"Invalid CLABE for withdrawal: {clabe}")

        extra = external_account.extra or {}
        bank_code = extra.get("bankCode") or bank_service.get_bank_code_by_clabe(clabe)  # type: ignore[call-overload]
        account_name = extra.get("accountName") or user_data.full_name  # type: ignore[call-overload]

        bank_name = bank_service.get_bank_name_by_code(bank_code)
        if not bank_name:
            assert self.trx.customer, "Customer is required for withdrawal notification"
            tasks.send_bank_not_found_slack_notification.apply_async(  # type: ignore[attr-defined]
                kwargs={
                    "bank_code": bank_code,
                    "transaction_id": self.trx.id,
                    "transaction_uuid": str(self.trx.uuid),
                    "customer_id": self.trx.customer.id,
                    "customer_external_id": self.trx.customer.external_id,
                }
            )

            raise SafeFlowInterruptionError(
                f"Bank code {bank_code} not found in bank list. "
                "Please ensure bank list is synchronized."
            )

        amount_centavos = int(to_minor_units(self.trx.amount, "MXN"))
        notify_url = get_rozert_callback_url(self.trx.system)

        payload = {
            "appId": self.creds.app_id,
            "mchId": self.creds.mch_id,
            "mchOrderNo": str(
                self.trx.uuid.hex
            ),  # Use transaction UUID as order number
            "nonceStr": muwe_spei_helpers.generate_nonce_str(),
            "amount": amount_centavos,
            "currency": muwe_spei_const.CURRENCY_MXN,
            "accountType": 40,  # Always 40 for CLABE accounts
            "accountNo": clabe,
            "accountName": account_name,
            "bankCode": bank_code,
            "bankName": bank_name,
            "notifyUrl": notify_url,
        }

        payload["sign"] = muwe_spei_helpers.calculate_signature(
            payload, self.creds.api_key.get_secret_value()
        )

        response = self._make_request(
            method="POST",
            url_path=muwe_spei_const.API_ENDPOINT_PAYOUT_CREATE,
            creds=self.creds,
            json_data=payload,
            headers={"tmId": "sipe_mx"},
        )

        if not response["success"]:
            error_msg = response.get("error", None)
            return entities.PaymentClientWithdrawResponse(
                status=const.TransactionStatus.FAILED,
                id_in_payment_system=None,
                raw_response=response,
                decline_code=muwe_spei_const.DECLINE_REASON_API_ERROR,
                decline_reason=error_msg,
            )

        order_id = response["data"].get("orderId")
        if not order_id:
            return entities.PaymentClientWithdrawResponse(
                status=const.TransactionStatus.FAILED,
                id_in_payment_system=None,
                raw_response=response,
                decline_code=muwe_spei_const.DECLINE_REASON_API_ERROR,
                decline_reason="No orderId in withdrawal response",
            )

        return entities.PaymentClientWithdrawResponse(
            status=const.TransactionStatus.PENDING,
            id_in_payment_system=order_id,
            raw_response=response,
        )

    def _get_transaction_status(
        self,
    ) -> base_classes.RemoteTransactionStatus:
        if self.trx.type == const.TransactionType.DEPOSIT:
            url_path = muwe_spei_const.API_ENDPOINT_QUERY_PAYIN
        else:
            url_path = muwe_spei_const.API_ENDPOINT_QUERY_PAYOUT

        payload = {
            "mchId": self.creds.mch_id,
            "orderId": self.trx.id_in_payment_system,
            "nonceStr": muwe_spei_helpers.generate_nonce_str(),
        }

        payload["sign"] = muwe_spei_helpers.calculate_signature(
            payload, self.creds.api_key.get_secret_value()
        )

        response = self._make_request(
            method="POST",
            url_path=url_path,
            creds=self.creds,
            json_data=payload,
            headers={},
        )

        if not response["success"]:
            logger.warning(
                "MUWE API query failed, returning PENDING for retry",
                extra={
                    "error": response.get("error"),
                    "trx_id": self.trx.id,
                    "raw_data": response.get("data", {}),
                },
            )
            return base_classes.RemoteTransactionStatus(
                decline_code=None,
                operation_status=const.TransactionStatus.PENDING,
                raw_data=response.get("data", {}),
            )

        response_data = response["data"]
        order_info_str = response_data.get("orderInfo")

        if not order_info_str:
            return base_classes.RemoteTransactionStatus(
                decline_code=None,
                operation_status=const.TransactionStatus.PENDING,
                raw_data=response_data,
            )

        order_info = json.loads(order_info_str)

        if response_data.get("single", True):
            data = order_info
        else:
            if not isinstance(order_info, list):
                return base_classes.RemoteTransactionStatus(
                    decline_code=None,
                    operation_status=const.TransactionStatus.PENDING,
                    raw_data=response_data,
                )
            data = None
            for item in order_info:
                if item.get("orderId") == self.trx.id_in_payment_system:
                    data = item
                    break
            if not data:
                return base_classes.RemoteTransactionStatus(
                    decline_code=None,
                    operation_status=const.TransactionStatus.PENDING,
                    raw_data=response_data,
                )

        muwe_status = data.get("status")
        internal_status = self._operation_status_by_foreign_status[muwe_status]

        decline_code = None
        decline_reason = None
        if internal_status == const.TransactionStatus.FAILED:
            decline_code = (
                data.get("errMsgCode") or data.get("errCode") or str(muwe_status)
            )
            decline_reason = data.get("errMsg")

        return base_classes.RemoteTransactionStatus(
            decline_code=decline_code,
            decline_reason=decline_reason,
            operation_status=internal_status,
            raw_data=response_data,
        )

    @staticmethod
    def _make_request(
        *,
        method: str,
        url_path: str,
        creds: MuweSpeiCreds,
        json_data: dict[str, ty.Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, ty.Any]:
        url = f"{creds.base_api_url}{url_path}"
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)

        response = requests.request(
            method=method,
            url=url,
            json=json_data,
            headers=request_headers,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()

        if data.get("resCode") != muwe_spei_const.RESPONSE_CODE_SUCCESS:
            return {
                "success": False,
                "error": data.get("errDes", None),
                "data": data,
            }

        return {
            "success": True,
            "data": data,
        }


class MuweSpeiClientSandbox(
    base_classes.BaseSandboxClientMixin[MuweSpeiCreds], MuweSpeiClient
):
    pass
