import json
import logging
import typing as ty
from datetime import timedelta
from typing import cast

import requests
from django.db import transaction
from rozert_pay.common.helpers.cache import (
    CacheKey,
    memory_cache_get_set,
    memory_cache_invalidate,
)
from rozert_pay.common.helpers.validation_mexico import validate_clabe
from rozert_pay.payment.systems.muwe_spei import muwe_spei_const, muwe_spei_helpers
from rozert_pay.payment.systems.muwe_spei.models import MuweSpeiBank

logger = logging.getLogger(__name__)


def fetch_bank_list(
    *,
    base_api_url: str,
    mch_id: str,
    api_key: str,
) -> dict[str, str] | None:
    url = f"{base_api_url}/common/query/bank"

    payload = {
        "mchId": mch_id,
        "nonceStr": muwe_spei_helpers.generate_nonce_str(),
    }

    payload["sign"] = muwe_spei_helpers.calculate_signature(payload, api_key)

    response = requests.post(
        url=url,
        json=payload,
        headers={
            "Content-Type": "application/json",
            "tmId": "sipe_mx",
        },
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()

    if data.get("resCode") != muwe_spei_const.RESPONSE_CODE_SUCCESS:
        logger.error("Fetch bank list: Failed to fetch bank list", extra={"data": data})
        return None

    if not muwe_spei_helpers.verify_signature(data, api_key):
        logger.error("Fetch bank list: Invalid signature in bank list response")
        return None

    banks_json = data.get("banks")
    if not banks_json:
        logger.error("No banks data in response")
        return None

    banks_dict: dict[str, str] = json.loads(banks_json)

    logger.info(
        "Fetch bank list: Successfully fetched some banks from MUWE API",
        extra={"banks": banks_dict},
    )
    return banks_dict


def sync_bank_list(
    *,
    base_api_url: str,
    mch_id: str,
    api_key: str,
) -> bool:
    banks_dict = fetch_bank_list(
        base_api_url=base_api_url,
        mch_id=mch_id,
        api_key=api_key,
    )

    if banks_dict is None:
        return False

    all_existing_codes = set(MuweSpeiBank.objects.values_list("code", flat=True))

    with transaction.atomic():
        api_bank_codes = set(banks_dict.keys())

        MuweSpeiBank.objects.exclude(code__in=api_bank_codes).update(is_active=False)

        MuweSpeiBank.objects.bulk_create(
            [
                MuweSpeiBank(
                    code=code,
                    name=name,
                    is_active=True,
                )
                for code, name in banks_dict.items()
            ],
            update_conflicts=True,
            update_fields=["name", "is_active"],
            unique_fields=["code"],
        )

        logger.info(
            "Sync bank list: Successfully synced banks to database",
            extra={"banks": banks_dict},
        )

    codes_to_invalidate = all_existing_codes | set(banks_dict.keys())
    for bank_code in codes_to_invalidate:
        memory_cache_invalidate(_get_bank_code_cache_key(bank_code))

    return True


def get_bank_name_by_code(bank_code: str) -> str | None:
    def _fetch_bank_name() -> str | None:
        try:
            return MuweSpeiBank.objects.get(code=bank_code, is_active=True).name
        except MuweSpeiBank.DoesNotExist:
            logger.warning(
                "Bank code not found in database", extra={"bank_code": bank_code}
            )
            return None

    cache_key = _get_bank_code_cache_key(bank_code)

    return memory_cache_get_set(
        key=cache_key,
        tp=str,
        on_miss=cast(ty.Callable[[], str], _fetch_bank_name),
        ttl=timedelta(days=1),
    )


def get_bank_code_by_clabe(clabe: str) -> str:
    validate_clabe(clabe)

    prefix = clabe[:3]
    bank = MuweSpeiBank.objects.filter(code__endswith=prefix, is_active=True).first()

    assert (
        bank is not None
    ), f"Could not determine bankCode from CLABE prefix '{prefix}' (accountNo={clabe})"
    return bank.code


def _get_bank_code_cache_key(bank_code: str) -> CacheKey:
    return CacheKey(f"muwe_spei:bank_code:{bank_code}")
