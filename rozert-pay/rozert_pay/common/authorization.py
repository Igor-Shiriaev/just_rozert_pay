import base64
import hashlib
import hmac
import logging
from dataclasses import dataclass

from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rozert_pay.account import models as account_models
from rozert_pay.common import const
from rozert_pay.payment.models import Merchant

logger = logging.getLogger(__name__)


@dataclass
class AuthData:
    merchant: Merchant


class BetmasterSecretKeyAuthentication(BasicAuthentication):
    def authenticate(
        self, request: Request
    ) -> tuple["account_models.User", None] | None:
        secret_key_from_header = request.headers.get(const.BACK_SECRET_KEY_HEADER)
        if not secret_key_from_header:
            return None

        if not settings.BACK_SECRET_KEY:
            logger.warning("BACK_SECRET_KEY is not set.")
            return None

        if not hmac.compare_digest(secret_key_from_header, settings.BACK_SECRET_KEY):
            raise AuthenticationFailed("Invalid Betmaster secret key.")

        try:
            user = account_models.User.objects.get(email=settings.SYSTEM_USER_EMAIL)
        except account_models.User.DoesNotExist:
            logger.error(
                "System user not found.", extra={"email": settings.SYSTEM_USER_EMAIL}
            )
            raise AuthenticationFailed("System user not configured.")

        return user, None


class BetmasterSecretKeyAuthenticationScheme(OpenApiAuthenticationExtension):  # type: ignore
    target_class = "rozert_pay.common.authorization.BetmasterSecretKeyAuthentication"
    name = "BetmasterSecretKeyAuthentication"

    def get_security_definition(self, auto_schema) -> dict[str, str]:  # type: ignore
        return {
            "type": "apiKey",
            "in": "header",
            "name": const.BACK_SECRET_KEY_HEADER,
        }


class HMACAuthentication(BasicAuthentication):
    def authenticate(
        self, request: Request
    ) -> tuple["account_models.User", AuthData] | None:
        merchant_id = request.headers.get("X-Merchant-Id")
        signature = request.headers.get("X-Signature")
        sandbox_mode = request.headers.get("X-Sandbox-Mode", False) == "true"

        if not merchant_id:
            logger.info("merchant id not found in headers")
            return None

        if not signature:
            logger.info("signature not found in headers")
            return None

        try:
            merchant = Merchant.objects.select_related("merchant_group__user").get(
                uuid=merchant_id
            )
        except Merchant.DoesNotExist:
            logger.info(
                "merchant not found",
                extra={
                    "merchant_id": merchant_id,
                },
            )
            return None

        if merchant.sandbox != sandbox_mode:
            logger.warning(
                "sandbox mode mismatch",
                extra={
                    "merchant_id": merchant_id,
                    "expected_sandbox": merchant.sandbox,
                    "sandbox": sandbox_mode,
                },
            )
            return None

        if not merchant.secret_key:
            logger.warning(
                "merchant has no secret key",
                extra={
                    "merchant_id": merchant_id,
                },
            )
            return None

        secret_key = merchant.secret_key.encode()
        message = request.body
        expected_signature = hmac.new(secret_key, message, hashlib.sha256).digest()
        expected_signature = base64.b64encode(expected_signature)

        if not hmac.compare_digest(signature.encode(), expected_signature):
            logger.warning(
                "signature mismatch",
                extra={
                    "merchant_id": merchant_id,
                    "expected_signature": expected_signature,
                    "signature": signature,
                },
            )
            return None

        return merchant.merchant_group.user, AuthData(merchant)


class HMACAuthenticationScheme(OpenApiAuthenticationExtension):  # type: ignore
    target_class = "rozert_pay.common.authorization.HMACAuthentication"
    name = "HMACAuthentication"

    def get_security_definition(self, auto_schema):  # type: ignore
        return [
            {
                "type": "apiKey",
                "in": "header",
                "name": "X-Merchant-Id",
            },
            {
                "type": "apiKey",
                "in": "header",
                "name": "X-Signature",
            },
        ]
