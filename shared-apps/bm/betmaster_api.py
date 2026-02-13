import logging
from functools import cached_property  # type: ignore
from typing import Any, Dict, List, Type, TypeVar, Union, overload

from bm.datatypes import ServiceNameType
from bm.entities import shared
from bm.memoize import memoize_cache
from bm.utils import requests_retry_session
from django.conf import settings
from pydantic import BaseModel
from requests import Response

logger = logging.getLogger(__name__)


class UserAuthInfo(BaseModel):
    id: int

    is_staff: bool
    is_superuser: bool
    is_active: bool

    email: str
    services_permissions: Dict[ServiceNameType, List[str]]

    def sync_to_user(self, user: Any) -> None:      # type: ignore
        changed = False

        def sync_field(field_name: str) -> None:
            nonlocal changed
            actual_value = getattr(self, field_name)
            if getattr(user, field_name) != actual_value:
                setattr(user, field_name, actual_value)
                changed = True

        for field in ['is_staff', 'is_superuser', 'is_active']:
            sync_field(field)

        if changed:
            user.save()


T_model = TypeVar('T_model', bound=BaseModel)


class BetmasterServerAPI:
    BACK_INTERNAL_API_URL: str = settings.BACK_INTERNAL_API_URL
    BACK_INTERNAL_API_TOKEN: str = settings.BACK_INTERNAL_API_TOKEN
    affiliate_service_name: ServiceNameType

    TTL_1_min = 60
    TTL_10_min = 10 * TTL_1_min
    TIMEOUT = 10

    session = requests_retry_session(backoff_factor=1, retries=5, status_forcelist=[500, 502, 503, 504])

    def call_remote_method(self, name: str, **kwargs: Any) -> Any:  # type: ignore
        return self.call_api(
            url=f'/private-api/messaging/{name}/',
            params=kwargs,
        )

    @overload
    def call_api(self, url: str, method: str = 'get',
                 timeout: float = None,
                 params: Dict = None, json: Dict = None) -> Dict: ...

    @overload
    def call_api(self, url: str, model: Type[T_model], method: str = 'get',
                 timeout: float = None,
                 params: Dict = None, json: Dict = None) -> T_model: ...

    def call_api(self, url: str, method: str = 'get',   # type: ignore
                 params: Dict = None, json: Dict = None,
                 timeout: float = None,
                 model: Type[T_model] = None,) -> Union[Dict, T_model]:
        result: Response = getattr(self.session, method)(
            url=f'{self.BACK_INTERNAL_API_URL}{url}',
            params=params,
            headers=self.auth_headers,
            json=json,
            timeout=timeout or self.TIMEOUT,
        )

        log_ctx = {
            '_status_code': result.status_code,
            '_response': result.text[:200],
            '_url': result.request.url,
        }
        if result.ok:
            logger.info(
                'made request to betmaster base api',
                extra=log_ctx
            )
        else:
            logger.warning(
                'got error response from betmaster base api',
                extra=log_ctx,
            )

        result.raise_for_status()
        result_dict = result.json()    # type: ignore
        if model:
            return model(**result_dict)
        return result_dict

    @cached_property
    def auth_headers(self) -> Dict[str, str]:       # type: ignore
        return {
            'Authorization': f'Bearer {self.BACK_INTERNAL_API_TOKEN}'
        }

    def sync_permissions_to_bmt(self, clean_previous_permissions: bool = False) -> None:
        try:
            from django.contrib.auth.models import Permission
        except ImportError:
            raise RuntimeError('Method can be used only in Django context!')

        try:
            request_data = {
                'service_name': self.affiliate_service_name,
                'permissions': [
                    {
                        'id': p.id,
                        'name': p.name,
                        'codename': p.codename,
                    }
                    for p in Permission.objects.all()
                ],
                'clean_previous_permissions': clean_previous_permissions,
            }
            self.call_api(
                url=f'/private-api/permissions/sync/',
                method='post',
                json=request_data,
            )
        except Exception:
            logger.exception('error while syncing permissions')

    @memoize_cache(TTL_1_min)
    def get_user_auth_info_by_session_key(self, session_key: str) -> UserAuthInfo:
        return self.call_api(
            '/private-api/permissions/getuser',
            json={
                'session_key': session_key,
                'service_name': self.affiliate_service_name,
            },
            method='post',
            model=UserAuthInfo,
        )

    @memoize_cache(TTL_1_min)
    def get_user_auth_info_by_email(self, email: str) -> UserAuthInfo:
        return self.call_api(
            '/private-api/permissions/getuserbyemail/',
            params={
                'email': email,
                'service_name': self.affiliate_service_name,
            },
            model=UserAuthInfo,
        )

    @memoize_cache(TTL_10_min)
    def get_current_env_configuration(self) -> shared.SharedEnvConfiguration:
        return self.call_api(
            '/private-api/configurations/env/',
            model=shared.SharedEnvConfiguration,
        )

    @memoize_cache(TTL_10_min)
    def get_currency_exchange_rates(self) -> shared.GetCurrencyExchangeRatesResponse:
        return self.call_api(
            '/private-api/currency/exchange-rates/',
            model=shared.GetCurrencyExchangeRatesResponse,
        )

    def get_link_redirectors_ids(self, links: list[str]) -> dict[str, int]:
        return self.call_api(
            '/private-api/marketing/link-redirectors/',
            params={'urls': links},
        )

    def __repr__(self) -> str:
        return f'BetmasterServerAPI()'
