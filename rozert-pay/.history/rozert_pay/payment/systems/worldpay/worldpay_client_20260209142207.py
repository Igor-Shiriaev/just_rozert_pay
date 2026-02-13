import logging
import typing as ty
from decimal import Decimal
from typing import Any

import requests
import xmltodict
from bm.datatypes import Money
from currency.utils import from_minor_units, to_minor_units
from pydantic import BaseModel, SecretStr
from rozert_pay.common import const
from rozert_pay.payment import entities
from rozert_pay.payment.api_v1.serializers.card_serializers import (
    CardBrowserDataSerializer,
    CardBrowserDataSerializerModel,
)
from rozert_pay.payment.services import (
    base_classes,
    db_services,
    deposit_services,
    event_logs,
)
from rozert_pay.payment.systems.worldpay.const import (
    NOT_READY_ERROR_MESSAGES,
    TIMEOUT_SECONDS,
    WORLDPAY_COOKIES_KEY,
    WorldpayPayloadType,
    WorldpayTransactionExtraFields,
)
from rozert_pay.payment.systems.worldpay.helpers import (
    generate_3ds_jwt,
    generate_worldpay_xml,
)
from rozert_pay.payment.types import TransactionId
from rozert_pay_shared.rozert_client import TransactionExtraFormData

logger = logging.getLogger(__name__)


class WorldpayCreds(BaseModel):
    base_url: str
    username: SecretStr
    password: SecretStr
    merchant_code: SecretStr
    # 3DS Flex JWT credentials
    jwt_issuer: SecretStr  # API ID
    jwt_org_unit_id: SecretStr  # Organizational Unit ID
    jwt_mac_key: SecretStr  # JWT signing key
    three_ds_challenge_action_url: str


class WorldpayClient(base_classes.BasePaymentClient[WorldpayCreds]):
    payment_system_name = const.PaymentSystemType.WORLDPAY
    credentials_cls = WorldpayCreds

    def _post_init(self) -> None:
        super()._post_init()
        self.session.response_parsers = [xmltodict.parse]
        self.session.on_request_parser = xmltodict.parse

    _deposit_status_by_foreign_status = {
        "SETTLED_BY_MERCHANT": entities.TransactionStatus.SUCCESS,
        "SETTLED": entities.TransactionStatus.SUCCESS,
        "CAPTURED": entities.TransactionStatus.SUCCESS,
        "AUTHORISED": entities.TransactionStatus.SUCCESS,
        "SENT_FOR_AUTHORISATION": entities.TransactionStatus.PENDING,
        "REFUSED": entities.TransactionStatus.FAILED,
        "CANCELLED": entities.TransactionStatus.FAILED,
        "ERROR": entities.TransactionStatus.FAILED,
        "EXPIRED": entities.TransactionStatus.FAILED,
    }
    # _withdrawal_status_by_foreign_status = {
    #     "AUTHORISED": entities.TransactionStatus.PENDING,
    #     "SENT_FOR_AUTHORISATION": entities.TransactionStatus.PENDING,
    #     "REFUSED": entities.TransactionStatus.FAILED,
    #     "CANCELLED": entities.TransactionStatus.FAILED,
    # }

    def deposit(self) -> entities.PaymentClientDepositResponse:
        assert self.trx.user_data
        assert self.trx.customer_card
        assert self.trx.customer_card.card_data_entity
        assert self.trx.redirect_url
        assert self.trx.extra.get(WorldpayTransactionExtraFields.SESSION_ID)

        card_data: entities.CardData = self.trx.customer_card.card_data_entity

        assert self.trx.customer
        browser_data = CardBrowserDataSerializer.from_trx(self.trx)

        xml_payload: str = generate_worldpay_xml(
            self._build_deposit_payload(card_data, self.trx.user_data, browser_data, request_3ds_challenge)
        )

        resp: requests.Response = self.session.post(
            url=f"{self.creds.base_url}/jsp/merchant/xml/paymentService.jsp",
            headers={"Content-Type": "text/plain"},
            data=xml_payload,
            timeout=TIMEOUT_SECONDS,
            auth=(
                self.creds.username.get_secret_value(),
                self.creds.password.get_secret_value(),
            ),
        )
        resp.raise_for_status()

        parsed_data: dict[str, ty.Any] = xmltodict.parse(resp.text)

        error_code: str | None
        error_reason: str | None
        error_code, error_reason = self._get_error_details(
            parsed_data,
            payload_type=WorldpayPayloadType.GET_STATUS,
        )
        if error_code:
            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=parsed_data,
                id_in_payment_system=self.trx.uuid.hex,
                decline_code=error_code,
                decline_reason=error_reason,
            )

        order_status = parsed_data["paymentService"]["reply"]["orderStatus"]
        id_in_payment_system = order_status["@orderCode"]

        # Check for 3DS challenge
        if "challengeRequired" in order_status:
            logger.info(
                "3DS challenge required for Worldpay transaction",
                extra={
                    "trx_id": self.trx.id,
                    "order_code": order_status["@orderCode"],
                },
            )
            cookies = resp.cookies.get_dict()
            logger.info(
                "Extracted Worldpay cookies from deposit response",
                extra={"trx_id": self.trx.id, "extracted_cookies": cookies},
            )
            db_services.save_extra_field(
                trx=self.trx,
                field=WORLDPAY_COOKIES_KEY,
                value=cookies,
            )

            three_ds_challenge_details = order_status["challengeRequired"][
                "threeDSChallengeDetails"
            ]
            iframe_height, iframe_width = self._get_iframe_size(
                browser_data,
                three_ds_challenge_details,
            )

            return_url = deposit_services.get_return_url(
                const.PaymentSystemType.WORLDPAY,
                trx_id=self.trx.uuid,
            )
            action_url_for_token = three_ds_challenge_details["acsURL"]

            jwt_token = generate_3ds_jwt(
                jwt_issuer=self.creds.jwt_issuer,
                jwt_org_unit_id=self.creds.jwt_org_unit_id,
                jwt_mac_key=self.creds.jwt_mac_key,
                return_url=return_url,
                acs_url=action_url_for_token,
                cardinal_payload=three_ds_challenge_details["payload"],
                transaction_id=three_ds_challenge_details["transactionId3DS"],
            )

            return entities.PaymentClientDepositResponse(
                status=entities.TransactionStatus.PENDING,
                raw_response=parsed_data,
                id_in_payment_system=id_in_payment_system,
                customer_redirect_form_data=TransactionExtraFormData(
                    action_url=self.creds.three_ds_challenge_action_url,
                    method="post",
                    fields={
                        "TermUrl": return_url,
                        "JWT": jwt_token,
                        "iframeHeight": iframe_height,
                        "iframeWidth": iframe_width,
                        # "MD": self.trx.uuid.hex,  # NOTE: it's optional. Trying without it
                    },
                ),
            )

        logger.error(
            "3DS challenge NOT required for Worldpay transaction",
            extra={
                "trx_id": self.trx.id,
                "order_code": order_status["@orderCode"],
            },
        )

        foreign_status = parsed_data["paymentService"]["reply"]["orderStatus"][
            "payment"
        ]["lastEvent"]
        status = self._deposit_status_by_foreign_status[foreign_status]
        if status == entities.TransactionStatus.SUCCESS:
            status = entities.TransactionStatus.PENDING

        decline_code = None
        decline_reason = None
        if status == entities.TransactionStatus.FAILED:
            decline_code = parsed_data["paymentService"]["reply"]["orderStatus"][
                "payment"
            ]["ISO8583ReturnCode"]["@code"]
            decline_reason = parsed_data["paymentService"]["reply"]["orderStatus"][
                "payment"
            ]["ISO8583ReturnCode"]["@description"]

        assert status in {
            entities.TransactionStatus.PENDING,
            entities.TransactionStatus.FAILED,
        }
        status_for_response = ty.cast(
            ty.Literal[
                entities.TransactionStatus.PENDING, entities.TransactionStatus.FAILED
            ],
            status,
        )

        return entities.PaymentClientDepositResponse(
            status=status_for_response,
            raw_response=parsed_data,
            # NOTE: `id_in_payment_system` is equal to `trx.uuid.hex`
            id_in_payment_system=id_in_payment_system,
            decline_code=decline_code,
            decline_reason=decline_reason,
        )

    def deposit_finalize(self) -> entities.PaymentClientDepositFinalizeResponse:
        """Send second XML request with 3DS authentication result."""
        xml_payload: str = generate_worldpay_xml(self._build_deposit_finalize_payload())

        headers = {"Content-Type": "text/plain"}
        stored_cookies = self.trx.extra[WORLDPAY_COOKIES_KEY]
        cookie_header = self._format_cookies_for_header(stored_cookies)
        headers["Cookie"] = cookie_header

        resp = self.session.post(
            url=f"{self.creds.base_url}/jsp/merchant/xml/paymentService.jsp",
            headers=headers,
            data=xml_payload,
            timeout=TIMEOUT_SECONDS,
            auth=(
                self.creds.username.get_secret_value(),
                self.creds.password.get_secret_value(),
            ),
        )
        resp.raise_for_status()
        parsed_data: dict[str, ty.Any] = xmltodict.parse(resp.text)

        error_code: str | None
        error_reason: str | None
        error_code, error_reason = self._get_error_details(
            parsed_data,
            payload_type=WorldpayPayloadType.GET_STATUS,
        )
        if error_code:
            return entities.PaymentClientDepositFinalizeResponse(
                status=entities.TransactionStatus.FAILED,
                raw_response=parsed_data,
                decline_code=error_code,
                decline_reason=error_reason,
            )

        if "challengeRequired" in parsed_data["paymentService"]["reply"]["orderStatus"]:
            # NOTE: Case when user cancelled 3DS challenge
            event_logs.create_transaction_log(
                trx_id=self.trx.id,
                event_type=const.EventType.INFO,
                description="User cancelled 3DS challenge",
                extra={},
            )
            return entities.PaymentClientDepositFinalizeResponse(
                status=entities.TransactionStatus.PENDING,
                raw_response=parsed_data,
            )

        foreign_status = parsed_data["paymentService"]["reply"]["orderStatus"][
            "payment"
        ]["lastEvent"]
        status = self._deposit_status_by_foreign_status[foreign_status]
        if status == entities.TransactionStatus.SUCCESS:
            status = entities.TransactionStatus.PENDING

        decline_code = None
        decline_reason = None
        if status == entities.TransactionStatus.FAILED:
            decline_code = parsed_data["paymentService"]["reply"]["orderStatus"][
                "payment"
            ]["ISO8583ReturnCode"]["@code"]
            decline_reason = parsed_data["paymentService"]["reply"]["orderStatus"][
                "payment"
            ]["ISO8583ReturnCode"]["@description"]

        assert status in {
            entities.TransactionStatus.PENDING,
            entities.TransactionStatus.FAILED,
        }
        status_for_response = ty.cast(
            ty.Literal[
                entities.TransactionStatus.PENDING, entities.TransactionStatus.FAILED
            ],
            status,
        )

        return entities.PaymentClientDepositFinalizeResponse(
            status=status_for_response,
            raw_response=parsed_data,
            decline_code=decline_code,
            decline_reason=decline_reason,
        )

    def withdraw(self) -> entities.PaymentClientWithdrawResponse:
        # NOTE: For the first iteration, we don't support withdrawals. But the code is correct.
        raise NotImplementedError()
        # assert self.trx.user_data
        # assert self.trx.customer_card
        # card_data: entities.CardData = self.trx.customer_card.card_data_entity
        # assert card_data.card_cvv

        # assert self.trx.customer

        # xml_payload: str = generate_worldpay_xml(
        #     self._build_withdraw_payload(card_data, self.trx.user_data)
        # )

        # resp = self.session.post(
        #     url=f"{self.creds.base_url}/jsp/merchant/xml/paymentService.jsp",
        #     headers={"Content-Type": "text/xml"},
        #     data=xml_payload.encode("utf-8"),
        #     timeout=TIMEOUT_SECONDS,
        # )
        # resp.raise_for_status()
        # parsed_data: dict[str, ty.Any] = xmltodict.parse(resp.text)

        # return entities.PaymentClientWithdrawResponse(
        #     status=entities.TransactionStatus.PENDING,
        #     # `id_in_payment_system` is equal to `trx.uuid.hex`
        #     id_in_payment_system=parsed_data["paymentService"]["reply"]["ok"][
        #         "refundReceived"
        #     ]["@orderCode"],
        #     raw_response=parsed_data,
        #     decline_code=None,
        #     decline_reason=None,
        # )

    def _get_transaction_status(self) -> entities.RemoteTransactionStatus:
        xml_payload: str = generate_worldpay_xml(self._build_get_status_payload())

        resp = self.session.post(
            url=f"{self.creds.base_url}/jsp/merchant/xml/paymentService.jsp",
            headers={"Content-Type": "text/plain"},
            data=xml_payload,
            timeout=TIMEOUT_SECONDS,
            auth=(
                self.creds.username.get_secret_value(),
                self.creds.password.get_secret_value(),
            ),
        )
        resp.raise_for_status()
        parsed_data: dict[str, ty.Any] = xmltodict.parse(resp.text)
        return self.get_remote_transaction_status_from_payload(
            parsed_data,
            payload_type=WorldpayPayloadType.GET_STATUS,
        )

    def get_remote_transaction_status_from_payload(
        self,
        parsed_data: dict[str, Any],
        *,
        payload_type: WorldpayPayloadType,
    ) -> entities.RemoteTransactionStatus:
        if payload_type in {
            WorldpayPayloadType.CREATE_ORDER,
            WorldpayPayloadType.GET_STATUS,
        }:
            id_in_payment_system: str = parsed_data["paymentService"]["reply"][
                "orderStatus"
            ]["@orderCode"]
        elif payload_type == WorldpayPayloadType.CALLBACK:
            id_in_payment_system = parsed_data["paymentService"]["notify"][
                "orderStatusEvent"
            ]["@orderCode"]
        else:
            raise ValueError(f"Unknown payload type: {payload_type}")

        error_code: str | None
        error_reason: str | None
        error_code, error_reason = self._get_error_details(
            parsed_data,
            payload_type=payload_type,
        )
        if error_code:
            assert error_reason
            if error_reason in NOT_READY_ERROR_MESSAGES:
                return entities.RemoteTransactionStatus(
                    operation_status=entities.TransactionStatus.PENDING,
                    raw_data=parsed_data,
                    transaction_id=self.trx.id,
                    id_in_payment_system=id_in_payment_system,
                    remote_amount=Money(
                        value=self.trx.amount,
                        currency=self.trx.currency,
                    ),
                )
            else:
                return entities.RemoteTransactionStatus(
                    operation_status=entities.TransactionStatus.FAILED,
                    raw_data=parsed_data,
                    transaction_id=self.trx.id,
                    id_in_payment_system=id_in_payment_system,
                    decline_code=error_code,
                    decline_reason=error_reason,
                )

        if "challengeRequired" in parsed_data["paymentService"]["reply"]["orderStatus"]:
            return entities.RemoteTransactionStatus(
                operation_status=entities.TransactionStatus.PENDING,
                raw_data=parsed_data,
                transaction_id=self.trx.id,
                id_in_payment_system=id_in_payment_system,
            )

        if payload_type in {
            WorldpayPayloadType.CREATE_ORDER,
            WorldpayPayloadType.GET_STATUS,
        }:
            payment_info: dict[str, Any] = parsed_data["paymentService"]["reply"][
                "orderStatus"
            ]["payment"]
        elif payload_type == WorldpayPayloadType.CALLBACK:
            payment_info = parsed_data["paymentService"]["notify"]["orderStatusEvent"][
                "payment"
            ]
        else:
            raise ValueError(f"Unknown payload type: {payload_type}")

        foreign_status = payment_info["lastEvent"]
        if self.trx.type == const.TransactionType.DEPOSIT:
            status = self._deposit_status_by_foreign_status[foreign_status]
        else:
            raise NotImplementedError("Withdrawals are not supported yet")

        decline_code: str | None = None
        decline_reason: str | None = None
        remote_amount: Money | None = None
        if status == entities.TransactionStatus.FAILED:
            decline_code = payment_info["ISO8583ReturnCode"]["@code"]
            decline_reason = payment_info["ISO8583ReturnCode"]["@description"]
        else:
            balance_data = payment_info["balance"]
            remote_amount_value, remote_amount_currency = self._handle_foreign_amounts(
                trx_id=self.trx.id,
                id_in_payment_system=id_in_payment_system,
                balance_data=balance_data,
            )
            remote_amount = Money(
                value=from_minor_units(remote_amount_value, remote_amount_currency),
                currency=remote_amount_currency,
            )
        return entities.RemoteTransactionStatus(
            operation_status=status,
            raw_data=parsed_data,
            transaction_id=self.trx.id,
            id_in_payment_system=id_in_payment_system,
            decline_code=decline_code,
            decline_reason=decline_reason,
            remote_amount=remote_amount,
        )

    def _build_deposit_payload(
        self,
        card_data: entities.CardData,
        user_data: entities.UserData,
        browser_data: CardBrowserDataSerializerModel,
        request_3ds_challenge: bool,
    ) -> dict[str, Any]:
        assert card_data.card_cvv
        assert user_data.phone

        if request_3ds_challenge:
            return {
                "paymentService": {
                    "@version": "1.4",
                    "@merchantCode": self.creds.merchant_code.get_secret_value(),
                    "submit": {
                        "order": {
                            "@orderCode": self.trx.uuid.hex,
                            "description": f"Order {self.trx.uuid.hex}",
                            "amount": {
                                "@value": int(
                                    to_minor_units(self.trx.amount, self.trx.currency)
                                ),
                                "@currencyCode": self.trx.currency,
                                "@exponent": "2",
                            },
                            "paymentDetails": {
                                "CARD-SSL": {
                                    "cardNumber": card_data.card_num.get_secret_value(),
                                    "expiryDate": {
                                        "date": {
                                            "@month": card_data.expiry_month,
                                            "@year": card_data.expiry_year,
                                        }
                                    },
                                    "cardHolderName": card_data.card_holder,
                                    "cvc": card_data.card_cvv.get_secret_value(),
                                    "cardAddress": {
                                        "address": {
                                            "address1": user_data.address,
                                            "postalCode": user_data.post_code,
                                            "city": user_data.city,
                                            "countryCode": user_data.country,
                                            "telephoneNumber": self._standardize_phone_number(
                                                user_data.phone,
                                            ),
                                        }
                                    },
                                },
                                "session": {
                                    "@shopperIPAddress": user_data.ip_address,
                                    "@id": self.trx.uuid.hex,
                                },
                            },
                            "shopper": {
                                "shopperEmailAddress": user_data.email,
                                "browser": {
                                    "acceptHeader": browser_data.accept_header,
                                    "userAgentHeader": browser_data.user_agent,
                                    "timeZone": browser_data.time_difference + "00",
                                    "browserLanguage": browser_data.language,
                                    "browserJavaEnabled": browser_data.java_enabled,
                                    "browserJavaScriptEnabled": browser_data.javascript_enabled,
                                    "browserColourDepth": browser_data.color_depth,
                                    "browserScreenHeight": browser_data.screen_height,
                                    "browserScreenWidth": browser_data.screen_width,
                                },
                            },
                            "additional3DSData": {
                                "@dfReferenceId": self.trx.extra.get(
                                    WorldpayTransactionExtraFields.SESSION_ID
                                ),
                                "@challengeWindowSize": "fullPage",
                                "@challengePreference": "challengeRequested",
                            },
                        },
                    },
                },
            }
        return {}

    # def _build_withdraw_payload(self, card_data: entities.CardData) -> str:
    #     return {
    #         "paymentService": {
    #             "@version": "1.4",
    #             "@merchantCode": self.creds.merchant_code.get_secret_value(),
    #             "submit": {
    #                 "order": {
    #                     "@orderCode": self.trx.uuid.hex,
    #                     "description": f"Order {self.trx.uuid.hex}",
    #                     "amount": {
    #                         "@value": str(self.trx.amount * 100),
    #                         "@currencyCode": self.trx.currency,
    #                         "@exponent": "2",
    #                     },
    #                     "paymentDetails": {
    #                         # Yes, `REFUND` is correct here.
    #                         "@action": "REFUND",
    #                         "CARD-SSL": {
    #                             "cardNumber": card_data.card_num.get_secret_value(),
    #                             "expiryDate": {
    #                                 "date": {
    #                                     "@month": card_data.expiry_month,
    #                                     "@year": card_data.expiry_year,
    #                                 }
    #                             },
    #                             "cardHolderName": card_data.card_holder,
    #                         },
    #                     },
    #                 },
    #             },
    #         },
    #     }

    def _build_get_status_payload(self) -> dict[str, Any]:
        return {
            "paymentService": {
                "@version": "1.4",
                "@merchantCode": self.creds.merchant_code.get_secret_value(),
                "inquiry": {
                    "orderInquiry": {"@orderCode": self.trx.uuid.hex},
                },
            },
        }

    def _build_deposit_finalize_payload(self) -> dict[str, Any]:
        return {
            "paymentService": {
                "@version": "1.4",
                "@merchantCode": self.creds.merchant_code.get_secret_value(),
                "submit": {
                    "order": {
                        "@orderCode": self.trx.uuid.hex,
                        "info3DSecure": {"completedAuthentication": None},
                        "session": {"@id": self.trx.uuid.hex},
                    },
                },
            },
        }

    @staticmethod
    def _get_error_details(
        parsed_data: dict[str, ty.Any],
        payload_type: WorldpayPayloadType,
    ) -> tuple[str | None, str | None]:
        if payload_type in {
            WorldpayPayloadType.CREATE_ORDER,
            WorldpayPayloadType.GET_STATUS,
        }:
            reply_entity: dict[str, Any] = parsed_data["paymentService"]["reply"]
            if order_entity := reply_entity.get("orderStatus"):
                error_code: str | None = order_entity.get("error", {}).get("@code")
                error_reason: str | None = order_entity.get("error", {}).get("#text")
            else:
                error_code = reply_entity.get("error", {}).get("@code")
                error_reason = reply_entity.get("error", {}).get("#text")

        elif payload_type == WorldpayPayloadType.CALLBACK:
            order_entity = parsed_data["paymentService"]["notify"]["orderStatusEvent"]
            error_code = order_entity.get("error", {}).get("@code")
            error_reason = order_entity.get("error", {}).get("#text")
        else:
            raise ValueError(f"Unknown payload type: {payload_type}")
        return error_code, error_reason

    @staticmethod
    def _handle_foreign_amounts(
        *,
        trx_id: TransactionId,
        id_in_payment_system: str,
        balance_data: dict[str, ty.Any] | list[dict[str, ty.Any]],
    ) -> tuple[Decimal, str]:
        final_amount: Decimal
        final_currency: str

        if isinstance(balance_data, dict):
            final_amount = Decimal(balance_data["amount"]["@value"])
            final_currency = balance_data["amount"]["@currencyCode"]
        else:
            commission_value: Decimal | None = None
            commission_currency: str | None = None
            net_value: Decimal | None = None
            net_currency: str | None = None

            for balance in balance_data:
                if balance.get("@accountType") == "SETTLED_BIBIT_NET":
                    net_value = Decimal(balance["amount"]["@value"])
                    net_currency = balance["amount"]["@currencyCode"]
                elif balance.get("@accountType") == "SETTLED_BIBIT_COMMISSION":
                    commission_value = Decimal(balance["amount"]["@value"])
                    commission_currency = balance["amount"]["@currencyCode"]
                else:
                    raise ValueError(
                        f"Unknown balance account type: {balance.get('@accountType')}"
                    )

            assert net_value and commission_value
            assert (
                net_currency
                and commission_currency
                and net_currency == commission_currency
            )

            # NOTE: For now we ignore commission and credit `net + commission` to user
            final_amount = net_value + commission_value
            final_currency = net_currency

            logger.info(
                "Worldpay commission and NET data",
                extra={
                    "commission": commission_value,
                    "net": net_value,
                    "currency": final_currency,
                    "final_amount": final_amount,
                    "trx_id": trx_id,
                    "id_in_payment_system": id_in_payment_system,
                },
            )

        return final_amount, final_currency

    @staticmethod
    def _format_cookies_for_header(cookies: dict[str, str]) -> str:
        """Format cookies dict into Cookie header value.

        Example: {'machine': '0aa20016', 'sessionID': '1_517e8a88'}
        -> 'machine=0aa20016; sessionID=1_517e8a88'
        """
        return "; ".join(f"{name}={value}" for name, value in cookies.items())

    def _standardize_phone_number(self, phone: str) -> str:
        # Remove spaces, hyphens, plus, and other non-digit characters
        phone = "".join(c for c in phone if c.isdigit())
        if len(phone) > 15:
            # Worldpay expects 15 digits, so we truncate the number
            logger.error(  # pragma: no cover
                "Phone number is too long for Worldpay, truncating",
                extra={
                    "phone": phone,
                    "trx_id": self.trx.id,
                },
            )
            phone = phone[:15]
        return phone

    def _get_iframe_size(
        self,
        browser_data: CardBrowserDataSerializerModel,
        three_ds_challenge_details: dict[str, ty.Any],
    ) -> tuple[int, int]:
        three_ds_version = three_ds_challenge_details["threeDSVersion"]
        if three_ds_version == "2.1.0":
            return 390, 400
        return browser_data.screen_height, browser_data.screen_width


class WorldpaySandboxClient(
    base_classes.BaseSandboxClientMixin[WorldpayCreds], WorldpayClient
):
    pass
