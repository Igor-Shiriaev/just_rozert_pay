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
