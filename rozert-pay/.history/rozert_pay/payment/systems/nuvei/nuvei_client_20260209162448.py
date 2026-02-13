import hashlib
import typing as ty
from uuid import uuid4

from bm.datatypes import Money
from bm.utils import quantize_decimal
from django.utils import timezone
from pydantic import BaseModel, SecretStr
from rozert_pay.common import const
from rozert_pay.payment import entities
from rozert_pay.payment.services import (
    base_classes,
    db_services,
    deposit_services,
    errors,
)
from rozert_pay.payment.systems.nuvei import nuvei_const


class NuveiApiError(BaseModel):
    decline_code: str
    decline_reason: str
    raw_data: dict[str, ty.Any]

    @property
    def is_session_token_expired_error(self) -> bool:
        return self.decline_code == "1069" and self.decline_reason == "Session expired"

    @property
    def is_payment_was_not_performed(self) -> bool:
        return (
            self.decline_code == "1140"
            and self.decline_reason == "A payment was not performed during this session"
        )


class NuveiCredentials(BaseModel):
    merchant_id: str
    merchant_site_id: str
    base_url: str
    secret_key: SecretStr


class NuveiClient(base_classes.BasePaymentClient[NuveiCredentials]):
    credentials_cls = NuveiCredentials

    def deposit(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.customer_card
        assert self.trx.customer_card.card_data_entity
        card_data: entities.CardData = self.trx.customer_card.card_data_entity

        assert card_data.card_cvv

        assert self.trx.user_data
        user_data = self.trx.user_data
        assert user_data.email
        assert user_data.country
        assert user_data.ip_address
        assert card_data.card_cvv

        assert self.trx.customer
        session_token = self._get_payment_session_token(self.creds)
        if isinstance(session_token, NuveiApiError):
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=session_token.raw_data,
                decline_code=session_token.decline_code,
                decline_reason=session_token.decline_reason,
            )

        db_services.save_extra_field(
            trx=self.trx,
            field=nuvei_const.TRX_EXTRA_FIELD_SESSION_TOKEN,
            value=session_token,
        )
        self.trx.extra[nuvei_const.TRX_EXTRA_FIELD_SESSION_TOKEN] = session_token

        request_id = str(uuid4())
        ts = timezone.now().strftime("%Y%m%d%H%M%S")
        amount = str(quantize_decimal(self.trx.amount, 2))

        init_request = {
            "sessionToken": session_token,
            "userTokenId": str(self.trx.customer.uuid),
            "clientUniqueId": str(self.trx.uuid),
            "currency": self.trx.currency,
            "amount": amount,
            "paymentOption": {
                "card": {
                    "cardNumber": card_data.card_num.get_secret_value(),
                    "cardHolderName": card_data.card_holder,
                    "expirationMonth": card_data.expiry_month,
                    "expirationYear": card_data.expiry_year,
                    "CVV": card_data.card_cvv.get_secret_value(),
                }
            },
            "deviceDetails": {
                "ipAddress": user_data.ip_address,
            },
            "clientRequestId": request_id,
            "merchantId": self.creds.merchant_id,
            "merchantSiteId": self.creds.merchant_site_id,
            "timeStamp": ts,
        }
        self._sign_payload(init_request, self.creds)

        init_response = self._make_request(
            url=f"{self.creds.base_url}/initPayment.do",
            payload=init_request,
        )
        if isinstance(init_response, NuveiApiError):
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=init_response.raw_data,
                decline_code=init_response.decline_code,
                decline_reason=init_response.decline_reason,
            )

        if init_response["status"] == nuvei_const.DEPOSIT_ERROR_API_STATUS:
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=init_response,
                decline_code=init_response.get("errCode"),
                decline_reason=init_response.get("reason"),
            )

        trx_gw_status = init_response["transactionStatus"]
        if trx_gw_status in nuvei_const.DEPOSIT_ERROR_GW_STATUSES:
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=init_response,
                decline_code=init_response.get("gwErrorReason"),
                decline_reason=init_response.get("gwErrorCode"),
            )

        db_services.save_extra_field(
            trx=self.trx,
            field=nuvei_const.TRX_EXTRA_FIELD_INIT_TRANSACTION_ID,
            value=init_response.get("transactionId"),
        )

        payment_request: dict[str, ty.Any] = {
            "sessionToken": session_token,
            "merchantId": self.creds.merchant_id,
            "merchantSiteId": self.creds.merchant_site_id,
            "clientRequestId": str(uuid4()),
            "amount": amount,
            "currency": self.trx.currency,
            "userTokenId": str(self.trx.customer.uuid),
            "clientUniqueId": str(self.trx.uuid),
            "paymentOption": {
                "card": {
                    "cardNumber": card_data.card_num.get_secret_value(),
                    "cardHolderName": card_data.card_holder,
                    "expirationMonth": card_data.expiry_month,
                    "expirationYear": card_data.expiry_year,
                    "CVV": card_data.card_cvv.get_secret_value(),
                }
            },
            "billingAddress": {
                "country": user_data.country,
                "email": user_data.email,
            },
            "deviceDetails": {"ipAddress": user_data.ip_address},
            "timeStamp": ts,
        }

        if init_response["paymentOption"]["card"]["threeD"]["v2supported"] == "true":
            redirect_url = deposit_services.get_return_url(
                const.PaymentSystemType.NUVEI,
                trx_id=self.trx.uuid,
            )
            payment_request["paymentOption"]["card"]["threeD"] = {
                "methodCompletionInd": "U",
                "version": "2.1.0",
                "notificationURL": redirect_url,
                "merchantURL": redirect_url,
                "platformType": "02",
                "v2AdditionalParams": {"challengeWindowSize": "05"},
                "browserDetails": {
                    "acceptHeader": "text/html,application/xhtml+xml",
                    "ip": user_data.ip_address,
                    "javaEnabled": "TRUE",
                    "javaScriptEnabled": "TRUE",
                    "language": "EN",
                    "colorDepth": "48",
                    "screenHeight": "400",
                    "screenWidth": "600",
                    "timeZone": "0",
                    "userAgent": "Mozilla",
                },
            }
            payment_request["relatedTransactionId"] = init_response.get("transactionId")

        self._sign_payload(payment_request, self.creds)

        payment_response = self._make_request(
            url=f"{self.creds.base_url}/payment",
            payload=payment_request,
        )
        return self._parse_payment_response(payment_response)

    def _parse_payment_response(
        self, response: dict[str, ty.Any] | NuveiApiError
    ) -> entities.PaymentClientDepositResponse:
        if isinstance(response, NuveiApiError):
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=response.raw_data,
                decline_code=response.decline_code,
                decline_reason=response.decline_reason,
            )

        id_in_payment_system = response.get("transactionId")

        if response["status"] == nuvei_const.DEPOSIT_ERROR_API_STATUS:
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=response,
                decline_code=response.get("errCode"),
                decline_reason=response.get("reason"),
                id_in_payment_system=id_in_payment_system,
            )

        if response.get("transactionStatus") == "APPROVED":
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.PENDING,
                raw_response=response,
                id_in_payment_system=id_in_payment_system,
            )

        if response.get("transactionStatus") == "REDIRECT":
            three_d = response["paymentOption"]["card"]["threeD"]
            db_services.save_extra_field(
                trx=self.trx,
                field=nuvei_const.TRX_EXTRA_FIELD_THREEDS_PAYMENT_RELATED_TRANSACTION_ID,
                value=id_in_payment_system,
            )
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.PENDING,
                raw_response=response,
                id_in_payment_system=id_in_payment_system,
                customer_redirect_form_data=entities.TransactionExtraFormData(
                    action_url=three_d["acsUrl"],
                    method="post",
                    fields={"creq": three_d["cReq"]},
                ),
            )

        return entities.PaymentClientDepositResponse(
            status=entities.TransactionStatus.FAILED,
            raw_response=response,
            decline_code=str(response.get("gwErrorReason")),
            decline_reason=str(response.get("gwErrorCode")),
            id_in_payment_system=id_in_payment_system,
        )

    def deposit_finalize(self) -> entities.PaymentClientDepositFinalizeResponse:
        related_transaction_id = self.trx.extra.get(
            nuvei_const.TRX_EXTRA_FIELD_THREEDS_PAYMENT_RELATED_TRANSACTION_ID
        )
        if not related_transaction_id:
            return entities.PaymentClientDepositFinalizeResponse(
                status=const.TransactionStatus.FAILED,
                raw_response={},
                decline_code=const.TransactionDeclineCodes.INTERNAL_ERROR,
                decline_reason="Missing relatedTransactionId for 3DS finalize",
            )

        session_token = self.trx.extra.get(nuvei_const.TRX_EXTRA_FIELD_SESSION_TOKEN)
        if not session_token:
            return entities.PaymentClientDepositFinalizeResponse(
                status=const.TransactionStatus.FAILED,
                raw_response={},
                decline_code=const.TransactionDeclineCodes.INTERNAL_ERROR,
                decline_reason="Missing session token for 3DS finalize",
            )

        assert self.trx.customer_card
        assert self.trx.customer_card.card_data_entity
        card_data: entities.CardData = self.trx.customer_card.card_data_entity

        assert self.trx.customer

        payment_request = {
            "sessionToken": session_token,
            "merchantId": self.creds.merchant_id,
            "merchantSiteId": self.creds.merchant_site_id,
            "clientRequestId": str(uuid4()),
            "amount": str(quantize_decimal(self.trx.amount, 2)),
            "currency": self.trx.currency,
            "userTokenId": str(self.trx.customer.uuid),
            "clientUniqueId": str(self.trx.uuid),
            "relatedTransactionId": related_transaction_id,
            "deviceDetails": {"ipAddress": "127.0.0.1"},
            "timeStamp": timezone.now().strftime("%Y%m%d%H%M%S"),
            "paymentOption": {
                "card": {
                    "cardNumber": card_data.card_num.get_secret_value(),
                    "cardHolderName": card_data.card_holder,
                    "expirationMonth": card_data.expiry_month,
                    "expirationYear": card_data.expiry_year,
                }
            },
        }
        self._sign_payload(payment_request, self.creds)

        response = self._make_request(
            url=f"{self.creds.base_url}/payment",
            payload=payment_request,
        )
        if isinstance(response, NuveiApiError):
            return entities.PaymentClientDepositFinalizeResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=response.raw_data,
                decline_code=response.decline_code,
                decline_reason=response.decline_reason,
            )

        remote_status = self.get_transaction_status()
        if isinstance(remote_status, errors.Error):
            return entities.PaymentClientDepositFinalizeResponse(
                status=entities.TransactionStatus.PENDING,
                raw_response=response,
            )

        if remote_status.operation_status == entities.TransactionStatus.FAILED:
            return entities.PaymentClientDepositFinalizeResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=response,
                decline_code=remote_status.decline_code,
                decline_reason=remote_status.decline_reason,
            )

        return entities.PaymentClientDepositFinalizeResponse(
            status=entities.TransactionStatus.SUCCESS,
            raw_response=response,
        )

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        assert self.trx.customer
        assert self.trx.customer_card
        assert self.trx.customer_card.card_data_entity
        card_data: entities.CardData = self.trx.customer_card.card_data_entity

        ts = timezone.now().strftime("%Y%m%d%H%M%S")
        client_request_id = str(uuid4())
        amount = str(quantize_decimal(self.trx.amount, 2))

        device_details = (
            {"ipAddress": self.trx.user_data.ip_address}
            if self.trx.user_data and self.trx.user_data.ip_address
            else None
        )
        payload = {
            "merchantId": self.creds.merchant_id,
            "clientRequestId": client_request_id,
            "merchantSiteId": self.creds.merchant_site_id,
            "userTokenId": str(self.trx.customer.uuid),
            "clientUniqueId": str(self.trx.uuid),
            "amount": amount,
            "currency": self.trx.currency,
            "deviceDetails": device_details,
            "timeStamp": ts,
            "checksum": hashlib.sha256(
                (
                    f"{self.creds.merchant_id}{self.creds.merchant_site_id}"
                    f"{client_request_id}{amount}{self.trx.currency}{ts}"
                    f"{self.creds.secret_key.get_secret_value()}"
                ).encode()
            ).hexdigest(),
            "cardData": {
                "cardNumber": card_data.card_num.get_secret_value(),
                "cardHolderName": card_data.card_holder,
                "expirationMonth": card_data.expiry_month,
                "expirationYear": card_data.expiry_year,
            },
        }
        if not device_details:
            payload.pop("deviceDetails")

        db_services.save_extra_field(
            trx=self.trx,
            field=nuvei_const.TRX_EXTRA_FIELD_PAYOUT_REQUEST_ID,
            value=client_request_id,
        )

        response = self._make_request(
            url=f"{self.creds.base_url}/payout.do",
            payload=payload,
        )
        if isinstance(response, NuveiApiError):
            return entities.PaymentClientWithdrawResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=response.raw_data,
                decline_code=response.decline_code,
                decline_reason=response.decline_reason,
                id_in_payment_system=None,
            )

        status = {
            "APPROVED": entities.TransactionStatus.PENDING,
            "ERROR": entities.TransactionStatus.FAILED,
            "DECLINED": entities.TransactionStatus.FAILED,
        }[response["transactionStatus"]]

        return entities.PaymentClientWithdrawResponse(
            status=status,  # type: ignore[arg-type]
            raw_response=response,
            id_in_payment_system=response.get("transactionId"),
            decline_reason=str(response.get("reason") or response.get("gwErrorReason")),
            decline_code=str(response.get("errCode") or response.get("gwErrorReason")),
        )

    def _get_transaction_status(self) -> entities.RemoteTransactionStatus:
        if self.trx.type == const.TransactionType.DEPOSIT:
            session_token = self.trx.extra.get(
                nuvei_const.TRX_EXTRA_FIELD_SESSION_TOKEN
            )
            if not session_token:
                return entities.RemoteTransactionStatus(
                    operation_status=entities.TransactionStatus.FAILED,
                    transaction_id=self.trx.id,
                    decline_code=const.TransactionDeclineCodes.INTERNAL_ERROR,
                    decline_reason="No session token found",
                    raw_data={},
                )

            resp = self._make_request(
                url=f"{self.creds.base_url}/getPaymentStatus.do",
                payload={"sessionToken": session_token},
                raise_if_no_success=False,
            )
            if isinstance(resp, NuveiApiError) and resp.is_session_token_expired_error:
                return entities.RemoteTransactionStatus(
                    operation_status=entities.TransactionStatus.PENDING,
                    transaction_id=self.trx.id,
                    raw_data={
                        **resp.raw_data,
                        "actualization_note": "Session token is expired",
                    },
                )
            if isinstance(resp, NuveiApiError):
                return entities.RemoteTransactionStatus(
                    operation_status=self._get_transaction_status_from_error(resp),
                    transaction_id=self.trx.id,
                    decline_code=resp.decline_code,
                    decline_reason=resp.decline_reason,
                    raw_data=resp.raw_data,
                )
        elif self.trx.type == const.TransactionType.WITHDRAWAL:
            client_request_id = self.trx.extra.get(
                nuvei_const.TRX_EXTRA_FIELD_PAYOUT_REQUEST_ID
            )
            if not client_request_id:
                return entities.RemoteTransactionStatus(
                    operation_status=entities.TransactionStatus.FAILED,
                    transaction_id=self.trx.id,
                    decline_code=const.TransactionDeclineCodes.INTERNAL_ERROR,
                    decline_reason="No payout request id found",
                    raw_data={},
                )

            ts = timezone.now().strftime("%Y%m%d%H%M%S")
            resp = self._make_request(
                url=f"{self.creds.base_url}/getPayoutStatus.do",
                payload={
                    "merchantId": self.creds.merchant_id,
                    "merchantSiteId": self.creds.merchant_site_id,
                    "clientRequestId": client_request_id,
                    "timeStamp": ts,
                    "checksum": hashlib.sha256(
                        (
                            f"{self.creds.merchant_id}{self.creds.merchant_site_id}"
                            f"{client_request_id}{ts}"
                            f"{self.creds.secret_key.get_secret_value()}"
                        ).encode()
                    ).hexdigest(),
                },
            )
            if isinstance(resp, NuveiApiError) and resp.is_session_token_expired_error:
                return entities.RemoteTransactionStatus(
                    operation_status=entities.TransactionStatus.PENDING,
                    transaction_id=self.trx.id,
                    raw_data={
                        **resp.raw_data,
                        "actualization_note": "Session token is expired",
                    },
                )
            if isinstance(resp, NuveiApiError):
                return entities.RemoteTransactionStatus(
                    operation_status=self._get_transaction_status_from_error(resp),
                    transaction_id=self.trx.id,
                    decline_code=resp.decline_code,
                    decline_reason=resp.decline_reason,
                    raw_data=resp.raw_data,
                )
        else:
            raise NotImplementedError

        assert isinstance(resp, dict)
        if resp["transactionStatus"] in nuvei_const.DEPOSIT_ERROR_GW_STATUSES:
            decline_code = resp.get("gwErrorReason")
            decline_reason = resp.get("gwErrorCode")
            operation_status = entities.TransactionStatus.FAILED
        else:
            decline_code = resp.get("errCode")
            decline_reason = resp.get("reason")
            operation_status = entities.TransactionStatus.SUCCESS

<<<<<<< HEAD
        if resp.get("errCode") == "1140":
            return entities.RemoteTransactionStatus(
                operation_status=entities.TransactionStatus.FAILED,
                transaction_id=self.trx.id,
                decline_code=str(decline_code),
                decline_reason=str(decline_reason),
                raw_data=resp,
            )

=======
>>>>>>> origin/igorshiryaev/sc-302275/rozert-worldpay-add-a-feature-flag-to-disable
        return entities.RemoteTransactionStatus(
            operation_status=operation_status,
            transaction_id=self.trx.id,
            id_in_payment_system=resp.get("transactionId")
            or self.trx.id_in_payment_system,
            decline_code=str(decline_code),
            decline_reason=str(decline_reason),
            raw_data=resp,
            remote_amount=Money(resp["amount"], resp["currency"])
            if "amount" in resp and "currency" in resp
            else None,
        )

    def _get_payment_session_token(
        self, creds: NuveiCredentials
    ) -> str | NuveiApiError:
        request_id = str(uuid4())
        ts = timezone.now().strftime("%Y%m%d%H%M%S")
        data = {
            "clientRequestId": request_id,
            "merchantId": creds.merchant_id,
            "merchantSiteId": creds.merchant_site_id,
            "timeStamp": ts,
            "checksum": hashlib.sha256(
                (
                    f"{creds.merchant_id}{creds.merchant_site_id}"
                    f"{request_id}{ts}{creds.secret_key.get_secret_value()}"
                ).encode()
            ).hexdigest(),
        }
        response = self._make_request(f"{creds.base_url}/getSessionToken", data)
        if isinstance(response, NuveiApiError):
            return response

        session_token = response.get("sessionToken")
        if session_token:
            return ty.cast(str, session_token)

        raise RuntimeError(f"No session token found in response: {response}")

    def _make_request(
        self,
        url: str,
        payload: dict[str, ty.Any],
        raise_if_no_success: bool = True,
    ) -> dict[str, ty.Any] | NuveiApiError:
        resp = self.session.post(url=url, json=payload)
        if raise_if_no_success:
            resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "ERROR":
            error_code = data.get("errorCode") or data.get("errCode")
            error_reason = data.get("errorDescription") or data.get("reason")
            return NuveiApiError(
                decline_code=str(error_code),
                decline_reason=str(error_reason),
                raw_data=data,
            )

        return data

    def _get_transaction_status_from_error(
        self, err_resp: NuveiApiError
    ) -> entities.TransactionStatus:
        if err_resp.is_payment_was_not_performed:
            is_recent = (
                timezone.now() - self.trx.created_at
                < nuvei_const.PAYMENT_NOT_PERFORMED_PENDING_WINDOW
            )
            return (
                entities.TransactionStatus.PENDING
                if is_recent
                else entities.TransactionStatus.FAILED
            )

        return entities.TransactionStatus.FAILED

    @staticmethod
    def _sign_payload(request_data: dict[str, ty.Any], creds: NuveiCredentials) -> None:
        request_data["checksum"] = hashlib.sha256(
            (
                f"{creds.merchant_id}{creds.merchant_site_id}"
                f"{request_data['clientRequestId']}{request_data['amount']}"
                f"{request_data['currency']}{request_data['timeStamp']}"
                f"{creds.secret_key.get_secret_value()}"
            ).encode()
        ).hexdigest()


class NuveiSandboxClient(
    base_classes.BaseSandboxClientMixin[NuveiCredentials], NuveiClient
):
    pass
