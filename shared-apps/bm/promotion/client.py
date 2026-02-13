from decimal import Decimal
from typing import Dict, List, Optional, Union, cast
from uuid import UUID

from bm import better_lru
from bm.datatypes import Money
from bm.eventbus.events import UserRewardedEventPayload
from bm.exceptions import BadRequest
from bm.promotion.dto import (
    CampaignDetail,
    FreebetRewardDetails,
    FreespinRewardDetails,
    WagerRewardDetails,
    BaseRewardDetails,
    CampaignUserStatus,
    UserPromoCodeResponse,
)
from bm.utils import requests_retry_session
from .constants import RewardType

from ..serializers import serialize_decimal
from .entities import PromoCode


class PromotionHTTPClient:
    def __init__(self, base_url: str, token: str, timeout: int = 2):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout

    def get_promocode(self, code: str) -> PromoCode:
        response = self._send_request(
            url=f'{self.base_url}/api/promocode/{code}/',
            method='get'
        )
        assert isinstance(response, dict)  # mypy
        return PromoCode(**response)

    def apply_promocode(
        self,
        user_uuid: UUID,
        user_currency: str,
        code: str,
        language: str = None
    ) -> Dict:
        response = self._send_request(
            url=f'{self.base_url}/api/apply-promocode/',
            language=language,
            data={
                'user_id': str(user_uuid),
                'user_currency': user_currency,
                'code': code
            }
        )
        assert isinstance(response, dict)  # mypy
        if response['reward']:
            response['reward'] = UserRewardedEventPayload(**response['reward'])
        return cast(Dict, response)

    def can_accept_campaign(
        self,
        user_uuid: UUID,
        campaign_id: int
    ) -> bool:
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/can-accept/',
            method='get',
            data={'user_id': str(user_uuid)}
        )
        response = cast(Dict, response)
        return response['can_accept']

    def accept_campaign(
        self,
        user_uuid: UUID,
        user_currency: str,
        campaign_id: int,
        language: str
    ) -> Dict:
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/accept/',
            language=language,
            data={
                'user_id': str(user_uuid),
                'user_currency': user_currency
            }
        )
        return cast(Dict, response)

    def create_participant(
        self,
        user_uuid: UUID,
        user_currency: str,
        campaign_id: int,
        accepted: bool,
        purchase_amount: Optional[Money] = None
    ) -> Dict:
        data: dict[str, Union[str, bool]] = {
            'user_id': str(user_uuid),
            'user_currency': user_currency,
            'accepted': accepted,
        }
        if purchase_amount is not None:
            assert purchase_amount.currency == user_currency, 'for now promo purchase currency should match user currency'
            data['purchase_amount'] = serialize_decimal(purchase_amount.value)
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/participate/',
            data=data,
        )
        return cast(Dict, response)

    def create_participant_with_state(
        self,
        user_uuid: UUID,
        user_currency: str,
        campaign_id: int,
        accepted: bool,
        amount: Decimal,
    ) -> Dict:
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/participate-with-state/',
            data={
                'user_id': str(user_uuid),
                'user_currency': user_currency,
                'accepted': accepted,
                'amount': serialize_decimal(amount),
            }
        )
        return cast(Dict, response)

    def deactivate_participant(
        self,
        user_uuid: UUID,
        campaign_id: int,
        apply_unconditional_reward: bool = True,
    ) -> None:
        self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/deactivate-participant/',
            data={
                'user_id': str(user_uuid),
                'apply_unconditional_reward': apply_unconditional_reward
            }
        )

    def can_participate(
        self,
        user_uuid: UUID,
        campaign_id: int
    ) -> bool:
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/can-participate/',
            method='get',
            data={'user_id': str(user_uuid)}
        )
        response = cast(Dict, response)
        return response['can_participate']

    def can_participate_via_public_api(
        self,
        user_uuid: UUID,
        campaign_id: int
    ) -> bool:
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/can-participate-via-public-api/',
            method='get',
            data={'user_id': str(user_uuid)}
        )
        response = cast(Dict, response)
        return response['can_participate']

    def can_participate_by_promocode(
        self,
        user_uuid: UUID,
        code: str,
    ) -> bool:
        response = self._send_request(
            url=f'{self.base_url}/api/promocode/{code}/can-participate/{user_uuid}/',
            method='get'
        )
        response = cast(Dict, response)
        return response['can_participate']

    def get_active_participant(
        self,
        user_uuid: UUID,
        campaign_id: int
    ) -> Dict:
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/active-participant/{user_uuid}/',
            method='get'
        )
        return cast(Dict, response)

    def get_user_campaigns(
        self,
        user_uuid: UUID,
        language: str
    ) -> List[Dict]:
        response = self._send_request(
            url=f'{self.base_url}/api/{user_uuid}/campaigns/',
            language=language,
            method='get'
        )
        return cast(List[Dict], response)

    def get_user_promocodes(
        self,
        user_uuid: UUID,
        language: str = None
    ) -> List[PromoCode]:
        response = self._send_request(
            url=f'{self.base_url}/api/{user_uuid}/promocodes/',
            language=language,
            method='get'
        )
        return [PromoCode(**item) for item in response]

    def get_user_promocode(
        self,
        user_uuid: UUID,
        code: str,
        language: str = None
    ) -> UserPromoCodeResponse:
        response = self._send_request(
            url=f'{self.base_url}/api/{user_uuid}/promocodes/{code}/',
            language=language,
            method='get'
        )
        assert isinstance(response, dict)  # mypy
        return UserPromoCodeResponse.parse_obj(response)

    def get_user_meta(
        self, user_uuid: UUID
    ) -> Dict:
        response = self._send_request(
            url=f'{self.base_url}/api/{user_uuid}/meta/',
            method='get'
        )
        assert isinstance(response, dict)  # mypy
        return response

    def get_campaign_templates(self) -> List[Dict]:
        response = self._send_request(
            url=f'{self.base_url}/api/campaign-templates/',
            method='get'
        )
        return cast(List[Dict], response)

    def get_campaigns(
        self,
        marketing_campaign_id: Optional[int] = None,
        exclude_expired: bool = False,
        with_detailed_participants_count: bool = False,
    ) -> List[Dict]:
        params = {}
        if marketing_campaign_id:
            params['marketing_campaign_id'] = marketing_campaign_id
        if exclude_expired:
            params['exclude_expired_campaigns'] = exclude_expired
        if with_detailed_participants_count:
            params['with_detailed_participants_count'] = with_detailed_participants_count
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/',
            method='get',
            params=params
        )
        return cast(List[Dict], response)

    def get_campaign_user_status(
        self,
        user_uuid: UUID,
        campaign_id: int
    ) -> CampaignUserStatus:
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/user-status/',
            method='get',
            data={'user_id': str(user_uuid)}
        )
        return CampaignUserStatus.parse_obj(response)

    def get_active_accepted_participants_by_campaign_id(self, campaign_id: int) -> list[dict]:
        participants = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/participants/',
            method='get',
            params={'active': True, 'accepted': True}
        )
        return cast(list[dict], participants)

    def get_all_accepted_participants_by_campaign_id(self, campaign_id: int) -> list[dict]:
        participants = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/participants/',
            method='get',
            params={'accepted': True}
        )
        return cast(list[dict], participants)

    def create_campaign_from_template(
        self,
        campaign_template_id: int,
        users: List[Dict] = None
    ) -> Dict:
        users = users or []
        response = self._send_request(
            url=f'{self.base_url}/api/campaign-templates/{campaign_template_id}/create-campaign/',
            method='post',
            data={'users': users}
        )
        return cast(Dict, response)

    def get_campaigns_without_marketing_campaign(self) -> List[Dict]:
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/',
            method='get',
            params={
                'marketing_campaign_id__isnull': True
            }
        )
        return cast(List[Dict], response)

    def set_marketing_campaign_id_to_campaigns(
        self, campaign_ids: List[int], marketing_campaign_id: Optional[int]
    ) -> None:
        self._send_request(
            url=f'{self.base_url}/api/campaigns/set-marketing-campaign-id/',
            method='post',
            data={
                'campaign_ids': campaign_ids,
                'marketing_campaign_id': marketing_campaign_id,
            }
        )

    @better_lru.lru_cache(ttl_seconds=600)
    def get_campaign(
        self,
        campaign_id: int,
    ) -> CampaignDetail:
        return CampaignDetail.parse_obj(
            self._send_request(
                method='get',
                url=f'{self.base_url}/api/campaigns/{campaign_id}/',
            )
        )

    def get_campaign_reward_details(
        self,
        campaign_id: int,
        currency: str,
    ) -> BaseRewardDetails:
        response = self._send_request(
            url=f'{self.base_url}/api/campaigns/{campaign_id}/reward/',
            method='get',
            data={'currency': currency}
        )
        assert isinstance(response, dict)
        payload_class = {
            RewardType.FREEBET: FreebetRewardDetails,
            RewardType.FREESPIN: FreespinRewardDetails,
            RewardType.PROMO_MONEY: WagerRewardDetails,
        }.get(response['reward_type'], BaseRewardDetails)
        return payload_class.parse_obj(response)  # type: ignore[attr-defined]

    def _send_request(
        self,
        url: str,
        language: str = None,
        method: str = 'post',
        data: Dict = None,
        params: Dict = None
    ) -> Union[Dict, List[Dict]]:
        headers = {'Authorization': f'Bearer {self.token}'}
        if language:
            headers['X-Language'] = language
        response = getattr(requests_retry_session(retries=1), method)(
            url,
            headers=headers,
            json=data,
            params=params,
            timeout=self.timeout
        )
        if response.status_code == 400:
            raise BadRequest(response.json())
        response.raise_for_status()
        return response.json()


class AdminUrls:
    def add_participant_to_campaign_form_url(
        self,
        base_url: str,
        campaign_id: int,
        user_id: UUID,
        user_currency: str
    ) -> str:
        return (
            f'{base_url}/promo-admin/promotion/campaign/{campaign_id}/actions/'
            f'action_create_participant_obj/?user_id={user_id}&user_currency={user_currency}'
        )

    def event_log_detail(self, pk: str, base_url: str = '') -> str:
        return f'{base_url}/promo-admin/promotion/eventlog/{pk}/change/'

    def event_log_by_bet_uuid_url(self, base_url: str, bet_uuid: UUID, user_uuid: UUID) -> str:
        bet_id = f'{user_uuid}__{bet_uuid}'
        return f'{base_url}/promo-admin/promotion/eventlog/?bet_id={bet_id}'

    def event_log_by_transaction_uuid_url(
        self,
        base_url: str,
        transaction_uuid: UUID,
        user_uuid: UUID
    ) -> str:
        payment_transaction_id = f'{user_uuid}__{transaction_uuid}'
        return f'{base_url}/promo-admin/promotion/eventlog/?payment_transaction_id={payment_transaction_id}'

    def participant_detail_by_wallet_account_url(
        self,
        wallet_account: str,
        base_url: str = '',
    ) -> str:
        return f'{base_url}/promo-admin/promotion/participant/by-wallet-account/{wallet_account}/'


admin_urls = AdminUrls()
