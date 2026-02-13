import time
import uuid
from typing import Any

import jwt
import xmltodict
from pydantic import SecretStr


def generate_worldpay_xml(payload: dict[str, Any]) -> str:
    """Generate WorldPay XML with proper DOCTYPE declaration."""
    xml_response = xmltodict.unparse(
        payload,
        pretty=True,
        full_document=True,
        encoding="UTF-8",
    )
    doctype = (
        "<!DOCTYPE paymentService PUBLIC "
        '"-//Worldpay//DTD Worldpay PaymentService v1//EN" '
        '"http://dtd.worldpay.com/paymentService_v1.dtd">'
    )
    parts = xml_response.split("\n", 1)
    return f"{parts[0]}\n{doctype}\n{parts[1]}"


def generate_ddc_jwt(
    jwt_issuer: SecretStr,
    jwt_org_unit_id: SecretStr,
    jwt_mac_key: SecretStr,
    exp_seconds: int = 7200,
) -> str:
    current_time = int(time.time())
    session_id = str(uuid.uuid4())

    payload = {
        "jti": session_id,
        "iat": current_time,
        "iss": jwt_issuer.get_secret_value(),
        "exp": current_time + exp_seconds,
        "OrgUnitId": jwt_org_unit_id.get_secret_value(),
    }

    headers = {
        "typ": "JWT",
        "alg": "HS256",
    }

    token = jwt.encode(
        payload,
        jwt_mac_key.get_secret_value(),
        algorithm="HS256",
        headers=headers,
    )

    return token


def generate_3ds_jwt(
    jwt_issuer: SecretStr,
    jwt_org_unit_id: SecretStr,
    jwt_mac_key: SecretStr,
    return_url: str,
    acs_url: str,
    cardinal_payload: str,
    transaction_id: str,
) -> str:


    Returns:
        Encoded JWT token signed with HS256

    Example JWT structure:
        {
            "jti": "54438b3a-bb53-12cd-8643-1536be73ff35",
            "iat": 1234567890,
            "iss": "5bd9e0e4444dce153428c940",
            "OrgUnitId": "5bd9b55e4444761ac0af1c80",
            "ReturnUrl": "https://merchant.example.com/3ds-callback",
            "Payload": {
                "ACSUrl": "https://merchantacsstag.cardinalcommerce.com/...",
                "Payload": "P.25de9db33221a55eedc6ac352b927a8c3a08d747...",
                "TransactionId": "sRMPWCQoQrEiVxehTnu0"
            },
            "ObjectifyPayload": true
        }
    """
    current_time = int(time.time())

    payload = {
        "jti": str(uuid.uuid4()),
        "iat": current_time,
        "iss": jwt_issuer.get_secret_value(),
        "OrgUnitId": jwt_org_unit_id.get_secret_value(),
        "ReturnUrl": return_url,
        "Payload": {
            "ACSUrl": acs_url,
            "Payload": cardinal_payload,
            "TransactionId": transaction_id,
        },
        "ObjectifyPayload": True,
    }

    headers = {
        "alg": "HS256",
        "typ": "JWT",
    }

    return jwt.encode(
        payload,
        jwt_mac_key.get_secret_value(),
        algorithm="HS256",
        headers=headers,
    )
