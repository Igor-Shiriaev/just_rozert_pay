import datetime
import logging
from typing import Optional, TypeVar, NoReturn
import zoneinfo

import requests
from pydantic import SecretStr, BaseModel
import jwt

from bm import better_lru
from bm.constants import TTL
from bm.utils import requests_retry_session
from bm.sds.api_models import (
    SDItem,
)
from bm.sds.type_aliases import SDET, SDDHT

from .api_models import (
    SDItem,
    EncryptAndDeterministicHashResponse,
    EncryptOneResponse,
    EncryptOneWithUpdateResponse,
    EncryptManyResponse,
    DeterministicHashOneResponse,
    DeterministicHashManyResponse,
)

T_ResponseModel = TypeVar('T_ResponseModel')


class DecryptOneResponse(BaseModel):
    item: Optional[SDItem]


class DecryptManyResponse(BaseModel):
    items: list[Optional[SDItem]]


logger = logging.getLogger(__name__)


class SDSError(Exception):
    pass


class MissingSDET(SDSError):

    def __init__(self, missing_tokens: list[SDET]):
        self.missing_tokens = missing_tokens
        super().__init__()


class SDSClient:

    def __init__(self, base_api_url: str, jwt_token_path: str, client_tls_cert_path: str, ca_tls_cert_path: str) -> None:
        if base_api_url[-1] == '/':
            self.base_api_url = base_api_url[:-1]
        else:
            self.base_api_url = base_api_url

        self.jwt_token_path = jwt_token_path
        self.ca_tls_cert_path = ca_tls_cert_path
        self.client_tls_cert_path = client_tls_cert_path

    def encrypt_one(self, item: SDItem) -> SDET:
        response = self._send_request(
            path='/encryption/encrypt/one',
            data={
                'item': item.dict(),
            },
            response_model=EncryptOneResponse,
        )
        return response.token

    def encrypt_many(self, items: list[SDItem]) -> list[SDET]:
        response = self._send_request(
            path='/encryption/encrypt/many',
            data={
                'items': [item.dict() for item in items],
            },
            response_model=EncryptManyResponse,
        )
        return response.tokens

    def decrypt_one(self, token: SDET, ignore_missing: bool) -> Optional[SDItem]:
        try:
            response = self._send_request(
                path='/encryption/decrypt/one',
                data={
                    'token': token,
                    'ignore_missing': ignore_missing,
                },
                response_model=DecryptOneResponse,
            )
        except requests.HTTPError as exc:
            self._maybe_process_errors(exc)
        else:
            return response.item

    def decrypt_many(self, tokens: list[SDET], ignore_missing: bool) -> list[Optional[SDItem]]:
        try:
            response = self._send_request(
                path='/encryption/decrypt/many',
                data={
                    'tokens': tokens,
                    'ignore_missing': ignore_missing,
                },
                response_model=DecryptManyResponse,
            )
        except requests.HTTPError as exc:
            self._maybe_process_errors(exc)
        else:
            return response.items

    def encrypt_one_with_update(self, token: SDET, new_item: SDItem) -> SDET:
        try:
            response = self._send_request(
                path='/encryption/encrypt-and-update/one',
                data={
                    'item': new_item.dict(),
                    'token': token,
                },
                response_model=EncryptOneWithUpdateResponse,
            )
        except requests.HTTPError as exc:
            self._maybe_process_errors(exc)
        else:
            return response.token

    def deterministic_hash_one(self, item: SDItem, create_if_missing: bool) -> Optional[SDDHT]:
        response = self._send_request(
            path='/deterministic-hashing/one',
            data={
                'item': item.dict(),
                'create_if_missing': create_if_missing,
            },
            response_model=DeterministicHashOneResponse
        )
        return response.token

    def deterministic_hash_many(self, items: list[SDItem], create_if_missing: bool) -> list[Optional[SDDHT]]:
        response = self._send_request(
            path='/deterministic-hashing/many',
            data={
                'items': [item.dict() for item in items],
                'create_if_missing': create_if_missing,
            },
            response_model=DeterministicHashManyResponse,
        )
        return response.tokens

    def encrypt_and_deterministic_hash(
        self,
        encryption_items: list[SDItem],
        deterministic_hashing_items: list[SDItem],
        deterministic_hashing_create_if_missing: bool
    ) -> EncryptAndDeterministicHashResponse:
        return self._send_request(
            path='/encrypt-and-deterministic-hash/',
            data={
                'encryption': {
                    'items': [item.dict() for item in encryption_items],   
                },
                'deterministic_hashing': {
                    'items': [item.dict() for item in deterministic_hashing_items],
                    'create_if_missing': deterministic_hashing_create_if_missing,
                },
            },
            response_model=EncryptAndDeterministicHashResponse,
        )

    @better_lru.lru_cache(ttl_seconds=TTL.hours_1)
    def _get_jwt_token(self) -> SecretStr:
        """Once in several hours jwt auth token will be upadted on disk by separate flow.
        Since expiration time for each token will be about 24 hours, it's totally ok to
        update the token once in an hour (multiple jwt tokens coould be valid at the same time,
        as long as they are generated with the same secret).
        """

        def _alert_if_about_to_expire() -> None:
            payload = jwt.decode(jwt_token.get_secret_value(), options={'verify_signature': False})
            UTC = zoneinfo.ZoneInfo('UTC')
            now = datetime.datetime.now(UTC)
            expires_at = datetime.datetime.utcfromtimestamp(payload['exp']).replace(tzinfo=UTC)
            if expires_at - now < datetime.timedelta(hours=10):
                logger.critical('SDS token is about to expire', extra={'_payload': payload})

        with open(self.jwt_token_path, 'r') as f:
            jwt_token = SecretStr(f.read().strip())
        _alert_if_about_to_expire()
        return jwt_token

    def _send_request(self, path: str, data: dict, response_model: type[T_ResponseModel]) -> T_ResponseModel:
        response = requests_retry_session().post(
            url=f'{self.base_api_url}/{path}',
            headers={'Authorization': f'Bearer {self._get_jwt_token().get_secret_value()}'},
            cert=self.client_tls_cert_path,
            verify=self.ca_tls_cert_path,
            json=data,
        )
        # TODO sds: do not log raw payload on error.
        # TODO sds: prevent sentry to collect raw variables.
        response.raise_for_status()
        return response_model.parse_obj(response.json())  # type: ignore[attr-defined]

    def _maybe_process_errors(self, exc: requests.HTTPError) -> NoReturn:
        if exc.response is not None and exc.response.status_code == 404:
            raise MissingSDET(missing_tokens=exc.response.json()['missing_tokens'])
        raise exc
