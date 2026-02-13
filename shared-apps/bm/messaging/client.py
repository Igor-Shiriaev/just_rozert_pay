import datetime
import logging
from datetime import timedelta
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from django.utils import timezone

from bm.entities.messaging import (
    ChannelType,
    DbAutomatedCampaignResponseModel,
    DeleteSmsGatewayForPhoneRequest,
    GatewayType, GetCampaignsRequest,
    GetMarketingCampaignRelatedObjectsRequest,
    GetMessagesForUserRequest,
    GetMessagesInfoResponse,
    GetSmsGatewayForPhoneRequest,
    GetSmsGatewayForPhoneResponse,
    MessageForUserModel,
    MessagingCampaignResponseModel,
    OptimasterTriggeredCampaign,
    OptimoveTemplate,
    PostSmsGatewayForPhoneRequest,
    SetMarketingCampaignIdToObjectsRequest, OptimasterScheduledCampaign
)
from bm.messaging import const
from bm.utils import requests_retry_session
from django.conf import settings

logger = logging.getLogger(__name__)


class MessagingClient:
    DEFAULT_RETRIES = 5
    DEFAULT_TIMEOUT = 20

    def __init__(self, retries: Optional[int] = None, request_timeout: Optional[int] = None):
        _timeout = request_timeout if request_timeout is not None else self.DEFAULT_TIMEOUT
        _retries = retries if retries is not None else self.DEFAULT_RETRIES
        self.timeout = _timeout
        self.session = requests_retry_session(retries=_retries, backoff_factor=0.5)
        self.api_key = settings.PRIVATE_API_MESSAGING_AUTH_TOKEN        # type: ignore

    def _make_request(
            self,
            *,
            request_type: Literal['get', 'post', 'delete'],
            url: str,
            query_params: dict = None,
            json_data: dict = None,
            json_response: bool = True,
        ) -> Any:
        messaging_base_url = getattr(settings, 'MESSAGING_BASE_URL', None)
        if not messaging_base_url:
            raise RuntimeError('no MESSAGING_BASE_URL in settings. making requests is not available')
        resp = getattr(self.session, request_type)(
            url=f'{messaging_base_url}{url}', json=json_data, params=query_params, timeout=self.timeout,
            headers={
                'X-Messaging-Auth-Token': self.api_key,
            }
        )
        if not resp.ok:
            req = resp.request
            logger.warning(
                'error requesting messaging API',
                extra={
                    'request': repr(req.body),
                    'request_url': repr(req.path_url),
                    'request_full_url': req.url,
                    'response': resp.text,
                    'response_status': resp.status_code,
                },
            )
        resp.raise_for_status()
        if json_response:
            return resp.json()
        else:
            return resp.text

    def get_task_infos(
        self, external_ids: List[str]
    ) -> Dict[str, GetMessagesInfoResponse]:
        result = self._make_request(
            request_type='post',
            url=const.API_PRIVATE_GET_MESSAGES_INFO_URL,
            json_data={
                'external_identities': external_ids,
            },
        )
        return {
            item['identity_foreign']: GetMessagesInfoResponse(**item)
            for item in result
        }

    def get_optimove_bound_promo_campaign_ids(self) -> List[str]:
        return self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_OPTIMOVE_BOUND_CAMPAIGNS_IDS,
            json_data={}
        )

    def get_sms_gateway_for_phone(
            self,
            *,
            phone_number: str,
            user_uuid: UUID,
        ) -> GetSmsGatewayForPhoneResponse:
        return GetSmsGatewayForPhoneResponse(
            **self._make_request(
                request_type='get',
                url=const.API_PRIVATE_SMS_GATEWAY_FOR_PHONE,
                query_params=GetSmsGatewayForPhoneRequest(
                    phone_number=phone_number,
                    user_uuid=user_uuid,
                ).dict()
            )
        )

    def set_sms_gateway_for_phone(
        self, phone_number: str, custom_gateway: GatewayType,
    ) -> None:
        self._make_request(
            request_type='post',
            json_response=False,
            url=const.API_PRIVATE_SMS_GATEWAY_FOR_PHONE,
            query_params=PostSmsGatewayForPhoneRequest(
                phone_number=phone_number, custom_gateway=custom_gateway,
            ).dict()
        )

    def delete_sms_gateway_for_phone(self, phone_number: str) -> None:
        self._make_request(
            request_type='delete',
            json_response=False,
            url=const.API_PRIVATE_SMS_GATEWAY_FOR_PHONE,
            query_params=DeleteSmsGatewayForPhoneRequest(
                phone_number=phone_number
            ).dict()
        )

    def get_campaigns_without_marketing_campaign(
        self
    ) -> List[MessagingCampaignResponseModel]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_MESSAGING_CAMPAIGNS,
            query_params=GetCampaignsRequest(
                exclude_bound_to_marketing_campaign=True,
                created_at_from=timezone.now() - timedelta(days=30),
            ).dict()
        )
        return [
            MessagingCampaignResponseModel.parse_obj(item)
            for item in data['items']
        ]

    def get_messaging_campaigns(
        self,
        marketing_campaign_id: int,
        include_tasks_count: bool = False
    ) -> List[MessagingCampaignResponseModel]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_MESSAGING_CAMPAIGNS,
            query_params=GetCampaignsRequest(
                marketing_campaign_id=marketing_campaign_id,
                include_tasks_count=include_tasks_count,
            ).dict()
        )
        return [
            MessagingCampaignResponseModel.parse_obj(item)
            for item in data['items']
        ]

    def set_marketing_campaign_id_to_messaging_campaigns(
        self,
        campaign_ids: List[int],
        marketing_campaign_id: Optional[int]
    ) -> None:
        self._make_request(
            request_type='post',
            url=const.API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_CAMPAIGNS,
            json_data=SetMarketingCampaignIdToObjectsRequest(
                objects_ids=campaign_ids,
                marketing_campaign_id=marketing_campaign_id,
            ).dict(),
            json_response=False
        )

    def get_db_automated_campaigns_without_marketing_campaign(
        self
    ) -> List[DbAutomatedCampaignResponseModel]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_DB_AUTOMATED_CAMPAIGNS,
            query_params=GetCampaignsRequest(
                exclude_bound_to_marketing_campaign=True,
                created_at_from=timezone.now() - timedelta(days=30),
            ).dict()
        )
        return [
            DbAutomatedCampaignResponseModel.parse_obj(item)
            for item in data['items']
        ]

    def get_db_automated_campaigns(
        self,
        marketing_campaign_id: int
    ) -> List[DbAutomatedCampaignResponseModel]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_DB_AUTOMATED_CAMPAIGNS,
            query_params=GetMarketingCampaignRelatedObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
            ).dict()
        )
        return [
            DbAutomatedCampaignResponseModel.parse_obj(item)
            for item in data['items']
        ]

    def set_marketing_campaign_id_to_db_automated_campaigns(
        self,
        campaign_ids: List[int],
        marketing_campaign_id: Optional[int]
    ) -> None:
        self._make_request(
            request_type='post',
            url=const.API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_DB_AUTOMATED_CAMPAIGNS,
            json_data=SetMarketingCampaignIdToObjectsRequest(
                objects_ids=campaign_ids,
                marketing_campaign_id=marketing_campaign_id,
            ).dict(),
            json_response=False
        )

    def get_messages_sent_to_user(
        self, user_uuid: str, channel_types: Optional[List[ChannelType]] = None
    ) -> List[MessageForUserModel]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_MESSAGES_FOR_USER,
            query_params=GetMessagesForUserRequest(
                user_uuid=user_uuid,
                channel_types=channel_types,
            ).dict(exclude_none=True),
        )
        return [MessageForUserModel.parse_obj(item) for item in data['items']]

    def get_optimove_email_templates(
        self,
        *,
        marketing_campaign_id: Optional[int],
        created_at__gte: Optional[datetime.datetime] = None,
    ) -> List[OptimoveTemplate]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_OPTIMOVE_EMAIL_TEMPLATES,
            query_params=GetMarketingCampaignRelatedObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                created_at__gte=int(created_at__gte.timestamp()) if created_at__gte else None,
            ).dict(exclude_none=True),
        )
        return [OptimoveTemplate.parse_obj(item) for item in data['items']]

    def get_optimove_sms_templates(
        self,
        *,
        marketing_campaign_id: Optional[int],
        created_at__gte: Optional[datetime.datetime] = None,
    ) -> List[OptimoveTemplate]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_OPTIMOVE_SMS_TEMPLATES,
            query_params=GetMarketingCampaignRelatedObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                created_at__gte=int(created_at__gte.timestamp()) if created_at__gte else None,
            ).dict(exclude_none=True),
        )
        return [OptimoveTemplate.parse_obj(item) for item in data['items']]

    def get_optimove_push_templates(
        self,
        *,
        marketing_campaign_id: Optional[int],
        created_at__gte: Optional[datetime.datetime] = None,
    ) -> List[OptimoveTemplate]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_OPTIMOVE_PUSH_TEMPLATES,
            query_params=GetMarketingCampaignRelatedObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                created_at__gte=int(created_at__gte.timestamp()) if created_at__gte else None,
            ).dict(exclude_none=True),
        )
        return [OptimoveTemplate.parse_obj(item) for item in data['items']]

    def get_optimaster_triggered_campaigns(
        self,
        *,
        marketing_campaign_id: Optional[int],
        created_at__gte: Optional[datetime.datetime] = None,
    ) -> List[OptimasterTriggeredCampaign]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_OPTIMASTER_TRIGGERED_CAMPAIGNS,
            query_params=GetMarketingCampaignRelatedObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                created_at__gte=int(created_at__gte.timestamp()) if created_at__gte else None,
            ).dict(exclude_none=True),
        )
        return [OptimasterTriggeredCampaign.parse_obj(item) for item in data['items']]

    def get_optimaster_scheduled_campaigns(
        self,
        *,
        marketing_campaign_id: Optional[int],
        created_at__gte: Optional[datetime.datetime] = None,
    ) -> List[OptimasterScheduledCampaign]:
        data = self._make_request(
            request_type='get',
            url=const.API_PRIVATE_GET_OPTIMASTER_SCHEDULED_CAMPAIGNS,
            query_params=GetMarketingCampaignRelatedObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                created_at__gte=int(created_at__gte.timestamp()) if created_at__gte else None,
            ).dict(exclude_none=True),
        )
        return [OptimasterScheduledCampaign.parse_obj(item) for item in data['items']]

    def set_marketing_campaign_id_to_optimove_email_templates(
        self,
        *,
        marketing_campaign_id: Optional[int],
        templates_ids: List[int],
    ) -> None:
        self._make_request(
            request_type='post',
            url=const.API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMOVE_EMAIL_TEMPLATES,
            json_data=SetMarketingCampaignIdToObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                objects_ids=templates_ids,
            ).dict(),
            json_response=False
        )

    def set_marketing_campaign_id_to_optimove_sms_templates(
        self,
        *,
        marketing_campaign_id: Optional[int],
        templates_ids: List[int],
    ) -> None:
        self._make_request(
            request_type='post',
            url=const.API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMOVE_SMS_TEMPLATES,
            json_data=SetMarketingCampaignIdToObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                objects_ids=templates_ids,
            ).dict(),
            json_response=False
        )

    def set_marketing_campaign_id_to_optimove_push_templates(
        self,
        *,
        marketing_campaign_id: Optional[int],
        templates_ids: List[int],
    ) -> None:
        self._make_request(
            request_type='post',
            url=const.API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMOVE_PUSH_TEMPLATES,
            json_data=SetMarketingCampaignIdToObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                objects_ids=templates_ids,
            ).dict(),
            json_response=False
        )

    def set_marketing_campaign_id_to_optimaster_triggered_campaigns(
        self,
        *,
        marketing_campaign_id: Optional[int],
        templates_ids: List[int],
    ) -> None:
        self._make_request(
            request_type='post',
            url=const.API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMASTER_TRIGGERED_CAMPAIGNS,
            json_data=SetMarketingCampaignIdToObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                objects_ids=templates_ids,
            ).dict(),
            json_response=False
        )

    def set_marketing_campaign_id_to_optimaster_scheduled_campaigns(
        self,
        *,
        marketing_campaign_id: Optional[int],
        templates_ids: List[int],
    ) -> None:
        self._make_request(
            request_type='post',
            url=const.API_PRIVATE_SET_MARKETING_CAMPAIGN_ID_TO_OPTIMASTER_SCHEDULED_CAMPAIGNS,
            json_data=SetMarketingCampaignIdToObjectsRequest(
                marketing_campaign_id=marketing_campaign_id,
                objects_ids=templates_ids,
            ).dict(),
            json_response=False
        )

    def start_whatsapp_registration_flow(
        self,
        user_uuid: UUID,
        contact_uuid: UUID,
    ) -> dict:
        return self._make_request(
            request_type='post',
            url=const.API_PRIVATE_WHATSAPP_START_REGISTRATION_FLOW,
            json_data={
                'user_uuid': str(user_uuid),
                'target_uuid': str(contact_uuid),
            },
            json_response=False,
        )

    def send_follow_up_message(
        self,
        user_uuid: UUID,
        contact_uuid: UUID,
    ) -> dict:
        return self._make_request(
            request_type='post',
            url=const.API_PRIVATE_WHATSAPP_SEND_REGISTRATION_FOLLOW_UP,
            json_data={
                'user_uuid': str(user_uuid),
                'target_uuid': str(contact_uuid),
            },
            json_response=False,
        )

    def update_whatsapp_message_status(
        self,
        message_foreign_id: str,
        current_status: str,
        webhook_data: str,
    ) -> dict:
        return self._make_request(
            request_type='post',
            url=const.API_PRIVATE_WHATSAPP_UPDATE_MESSAGE_STATUS,
            json_data={
                'message_foreign_id': message_foreign_id,
                'current_status': current_status,
                'webhook_data': webhook_data,
            },
            json_response=False,
        )

    def rebind_messages_to_registered_user(
        self,
        old_user_uuid: UUID,
        new_user_uuid: UUID,
        contact_uuid: UUID,
    ) -> dict:
        return self._make_request(
            request_type='post',
            url=const.API_PRIVATE_WHATSAPP_REBIND_MESSAGES_TO_REGISTERED_USER,
            json_data={
                'old_user_uuid': str(old_user_uuid),
                'new_user_uuid': str(new_user_uuid),
                'target_uuid': str(contact_uuid),
            },
            json_response=False,
        )
