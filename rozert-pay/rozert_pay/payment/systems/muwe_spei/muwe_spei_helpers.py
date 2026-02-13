"""
MUWE SPEI Helper Functions

Signature calculation, CLABE validation, and utility functions for MUWE SPEI.
"""

import hashlib
import json
import random
import string
from typing import Any

from django.conf import settings
from rozert_pay.payment.systems.muwe_spei.muwe_spei_const import (
    MUWE_SPEI_IDENTIFIER,
    MUWE_SPEI_MCH_ORDER_NO,
)


def generate_nonce_str(length: int = 16) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def calculate_signature(payload: dict[str, Any], api_key: str) -> str:
    """
    Calculate MD5 signature for MUWE API request/response.

    Algorithm (from MUWE API documentation):
    1. Filter out null/empty values
    2. Sort parameters by key name (ASCII/lexicographic order)
    3. Build string: key1=value1&key2=value2...
    4. Append: &key={api_key}
    5. Calculate MD5 hash
    6. Convert to uppercase

    Special handling:
    - Arrays are serialized to JSON for signature calculation
    - The "sign" field itself does not participate in signature

    Args:
        payload: Request/response parameters (dict)
        api_key: MUWE API key

    Returns:
        MD5 signature (uppercase hex string)

    Example:
        >>> payload = {"mchId": "123", "amount": 100, "nonceStr": "abc"}
        >>> calculate_signature(payload, "secret_key")
        'A1B2C3D4E5F6...'
    """
    # Step 1: Filter out null/empty values and 'sign' field
    filtered = {
        k: v for k, v in payload.items() if v not in (None, "", []) and k != "sign"
    }

    # Special handling for arrays (e.g., events in webhook creation)
    filtered_for_sign = {}
    for k, v in filtered.items():
        if isinstance(v, list):
            # Arrays are serialized to JSON for signature
            filtered_for_sign[k] = json.dumps(v, separators=(",", ":"))
        else:
            filtered_for_sign[k] = v

    # Step 2: Sort by parameter name (ASCII order)
    sorted_items = sorted(filtered_for_sign.items())

    # Step 3: Build key=value string
    string_a = "&".join(f"{k}={v}" for k, v in sorted_items)

    # Step 4: Append API key
    string_sign_temp = f"{string_a}&key={api_key}"

    # Step 5: MD5 hash
    md5_hash = hashlib.md5(string_sign_temp.encode()).hexdigest()

    # Step 6: Uppercase
    signature = md5_hash.upper()

    return signature


def verify_signature(payload: dict[str, Any], api_key: str) -> bool:
    """
    Verify signature of incoming webhook or API response.

    Args:
        payload: Request/response with 'sign' field
        api_key: MUWE API key

    Returns:
        True if signature is valid, False otherwise
    """
    received_sign = payload.get("sign", "")
    if not received_sign:
        return False

    expected_sign = calculate_signature(payload, api_key)

    return received_sign == expected_sign


def extract_order_id_from_identifier(identifier: str) -> str | None:
    # For now, just return the identifier itself
    # In future, may need to parse specific format if documented
    return identifier if identifier else None


def build_transaction_extra_data(webhook_payload: dict[str, Any]) -> dict[str, Any]:
    extra_data = {}

    # identifier - MUWE transaction tracking key (equivalent to clave_rastreo in other SPEI systems)
    if MUWE_SPEI_IDENTIFIER in webhook_payload:
        extra_data[MUWE_SPEI_IDENTIFIER] = webhook_payload[MUWE_SPEI_IDENTIFIER]

    # For withdrawals - store our merchant order number for reference
    if MUWE_SPEI_MCH_ORDER_NO in webhook_payload:
        extra_data[MUWE_SPEI_MCH_ORDER_NO] = webhook_payload[MUWE_SPEI_MCH_ORDER_NO]

    return extra_data


def build_notify_url() -> str:
    return f"{settings.EXTERNAL_ROZERT_HOST}/api/payment/v1/callback/muwe-spei/"
