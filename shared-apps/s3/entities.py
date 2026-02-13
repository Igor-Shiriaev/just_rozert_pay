from typing import Optional, TYPE_CHECKING, Any

from pydantic import BaseModel, root_validator, validator

from .const import AccountType

if TYPE_CHECKING:
    from common.configurations.settings_reference_proxy import SettingsReferenceProxy
else:
    # For runtime: create a fake generic that always returns Any
    class SettingsReferenceProxy:
        def __class_getitem__(cls, item):
            return Any


class Credentials(BaseModel):
    # access_key_id: SettingsReferenceProxy[str]
    # secret_access_key: SettingsReferenceProxy[str]
    access_key_id: str
    secret_access_key: str

    class Config:
        arbitrary_types_allowed = True  # Allow SettingsReferenceProxy types


class CDNConfig(BaseModel):
    domain: str

    @property
    def url(self) -> str:
        return f'https://{self.domain}'


class BucketConfig(BaseModel):
    name: str
    use_server_side_encryption: bool
    acl: str
    # In Cloudflare R2 we have custom domain 'img.slotshub.io' attacked to 'img' bucket,
    # and correct final url is https://img.slotshub.io/<object_key>, e.g.:
    #   https://img.slotshub.io/casino/games/casinogame/d293d7f5-7c14-42d7-8899-5f98e2713161.png
    # But in case of S3 and 'bmstatic.cloud' custom domain for bucket 'bmstorage' final url is:
    #   https://bmstatic.cloud/bmstorage/<object_key>.
    # So we use it as False only for CF R2 for now.
    add_bucket_name_to_url: bool = True
    content_types: Optional[list[str]] = None
    cdn_config: Optional[CDNConfig] = None


class AccountConfig(BaseModel):
    region_name: Optional[str]
    credentials: Credentials
    endpoint_url: str
    # NOTE: by default aws uses 'https://<endpoint_domain>/<bucket>' urls,
    # so bucket is not part of the resulting url domain.
    # NOTE: for non-aws s3 instances (like https://min.io/) bucket
    # is part of domain, and while uploading files via boto client
    # argument `Bucket` to `s3.put_object` function would be just
    # part of the final file url: 'https://<bucket>.<endpoint_domain>/bucket/...'
    bucket_as_dns: bool
    bucket_configs: dict[str, BucketConfig]

    @root_validator(pre=True)
    def transform_buckets_field(cls, values: dict) -> dict:
        if 'bucket_configs' not in values:
            values['bucket_configs'] = {
                b['name']: b for b in values['buckets']
            }
        return values

    def get_bucket_config(self, bucket: Optional[str] = None) -> BucketConfig:
        if bucket is None:
            if len(self.bucket_configs) > 1:
                raise ValueError(f'Bucket name should be specified explicitly, got None.')
            # get config for the only defined bucket
            bucket_config = list(self.bucket_configs.values())[0]
        else:
            # get config for the specified bucket name
            bucket_config = self.bucket_configs[bucket]
        return bucket_config


class AccountConfigsRegistry(BaseModel):
    __root__: dict[AccountType, AccountConfig]

    def get_account_config(self, account_type: AccountType) -> AccountConfig:
        return self.__root__[account_type]

    @property
    def config_for_public_static_bucket(self) -> BucketConfig:
        return self.get_account_config(AccountType.PUBLIC_STATIC).get_bucket_config()

    @property
    def private_url_for_public_static_bucket(self) -> str:
        account_config = self.get_account_config(AccountType.PUBLIC_STATIC)
        bucket_config = account_config.get_bucket_config()
        return f'{account_config.endpoint_url}/{bucket_config.name}'

    @property
    def public_url_for_public_static_bucket(self) -> str:
        bucket_config = self.config_for_public_static_bucket
        if bucket_config.cdn_config is None:
            return self.private_url_for_public_static_bucket
        return f'{bucket_config.cdn_config.url}/{bucket_config.name}'

    @validator('__root__')
    def check_all_account_types_configured(cls, v):  # type: ignore
        for account_type in AccountType:
            assert account_type in v, f'Config for account {account_type} is not registered'
        return v
