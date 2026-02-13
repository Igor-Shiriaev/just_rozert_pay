from typing import Any

from django.utils.functional import cached_property
from storages.backends.s3boto3 import S3Boto3Storage
from storages.base import BaseStorage

from .const import AccountType
from .entities import AccountConfig, AccountConfigsRegistry


class BackendPrivateS3Storage(S3Boto3Storage):
    CONFIG: AccountConfigsRegistry

    def __init__(self, **settings: dict[str, Any]) -> None:
        account_config = self.CONFIG.get_account_config(AccountType.BACKEND_INTERNAL)
        bucket = account_config.get_bucket_config()

        # key.get_value() is dropped because SettingsReferenceProxy is not currently used
        access_key = account_config.credentials.access_key_id
        secret_key = account_config.credentials.secret_access_key

        config: dict[str, Any] = dict(
            access_key=access_key,
            secret_key=secret_key,
            bucket_name=bucket.name,
            default_acl=bucket.acl,
            region_name=account_config.region_name,
            file_overwrite=False,
        )
        super().__init__(**(settings | config))


class LazyBackendPrivateS3Storage(BaseStorage):
    CONFIG: AccountConfig

    @cached_property
    def _backend(self) -> S3Boto3Storage:
        self.init()
        bucket = self.CONFIG.get_bucket_config()

        # key.get_value() is dropped because SettingsReferenceProxy is not currently used
        access_key = self.CONFIG.credentials.access_key_id
        secret_key = self.CONFIG.credentials.secret_access_key

        return S3Boto3Storage(
            access_key=access_key,
            secret_key=secret_key,
            bucket_name=bucket.name,
            default_acl=bucket.acl,
            region_name=self.CONFIG.region_name,
            file_overwrite=False,
        )

    def exists(self, name):  # type: ignore
        return self._backend.exists(name)

    def path(self, name):  # type: ignore
        return self._backend.path(name)

    def open(self, name, mode='rb'):  # type: ignore
        return self._backend.open(name, mode)

    def save(self, name, content, max_length=None):  # type: ignore
        return self._backend.save(name, content, max_length)

    def get_valid_name(self, name):  # type: ignore
        return self._backend.get_valid_name(name)

    def get_alternative_name(self, file_root, file_ext):  # type: ignore
        return self._backend.get_alternative_name(file_root, file_ext)

    def get_available_name(self, name, max_length=None):  # type: ignore
        return self._backend.get_available_name(name, max_length)

    def generate_filename(self, filename):  # type: ignore
        return self._backend.generate_filename(filename)

    def delete(self, name):  # type: ignore
        return self._backend.delete(name)

    def listdir(self, path):  # type: ignore
        return self._backend.listdir(path)

    def size(self, name):  # type: ignore
        return self._backend.size(name)

    def url(self, name):  # type: ignore
        return self._backend.url(name)

    def __init__(self, **kwargs):  # type: ignore
        self._kwargs = kwargs

    def init(self) -> None:
        pass

    def deconstruct(self):  # type: ignore
        return f'messaging.{self.__class__.__name__}', tuple(), {'_kwargs': self._kwargs}
