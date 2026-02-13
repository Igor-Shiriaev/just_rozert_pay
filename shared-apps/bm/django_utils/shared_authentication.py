import logging
from abc import ABC, abstractmethod
from typing import Set, Optional

from bm.betmaster_api import BetmasterServerAPI
from django.conf import settings
from django.contrib import auth
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.contrib.auth.models import Permission, User
from django.http import HttpRequest

logger = logging.getLogger(__name__)


class BaseRemoteAuthenticationMiddleware(AuthenticationMiddleware):
    BETMASTER_SESSION_COOKIE_NAME = 'bmt_sid'
    client: BetmasterServerAPI

    def process_request(self, request: HttpRequest) -> None:
        if getattr(settings, 'DO_NOT_USE_SHARED_AUTHENTICATION', False):
            logger.debug('skip shared authentication because settings.DO_NOT_USE_SHARED_AUTHENTICATION is set')
            return

        if getattr(request, 'DO_NOT_USE_SHARED_AUTHENTICATION', False):
            logger.debug('skip shared authentication because request.DO_NOT_USE_SHARED_AUTHENTICATION is set')
            return

        betmaster_session_key = request.COOKIES.get(self.BETMASTER_SESSION_COOKIE_NAME)
        if not betmaster_session_key or request.user.is_authenticated:
            logger.debug('skip shared authentication because no bmt_sid found')
            return

        user = self._get_or_create_user_from_remote(betmaster_session_key)
        if user:
            auth.login(request, user)

    def _get_or_create_user_from_remote(self, session_key: str) -> Optional[User]:
        try:
            user_auth_info = self.client.get_user_auth_info_by_session_key(
                session_key
            )
        except Exception:
            logger.exception('Exception in %s', self.__class__.__name__)
            return None

        if not user_auth_info.is_staff:
            return None

        user, created = get_user_model().objects.update_or_create(
            username=user_auth_info.email,
            defaults=dict(
                email=user_auth_info.email,
            )
        )
        if created:
            user.set_unusable_password()
            user.save()
        user_auth_info.sync_to_user(user)
        return user


class BaseSharedAuthBackend(ModelBackend, ABC):
    @property
    @abstractmethod
    def bm_api(self) -> BetmasterServerAPI:
        pass

    def get_all_permissions(self, user_obj: User, obj: User = None) -> Set[str]:        # type: ignore
        if getattr(settings, 'DO_NOT_USE_SHARED_AUTHENTICATION', False):
            return super().get_all_permissions(user_obj, obj)

        try:
            auth_info = self.bm_api.get_user_auth_info_by_email(user_obj.username)

            perms = list(Permission.objects.filter(id__in=auth_info.services_permissions[self.bm_api.affiliate_service_name]).values_list(
                'content_type__app_label', 'codename'
            ).order_by())
            return {"%s.%s" % (ct, name) for ct, name in perms}
        except:
            return super().get_all_permissions(user_obj, obj)
