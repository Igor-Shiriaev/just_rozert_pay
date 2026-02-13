from collections import defaultdict

from bm.constants import InstanceId
from bm.entities.shared import BrandConfiguration
from bm.entities.messaging import SendgridIPPoolName
from pydantic import BaseModel, Field
from s3.entities import AccountConfig


class DomainGroupConfig(BaseModel):
    domain_web_main: str
    unsubscribe_url: str
    brand_config_by_brand: dict[str, BrandConfiguration]
    sendgrid_ip_pool_name: SendgridIPPoolName


class PromotionsConfig(BaseModel):
    is_cashback_accepted_after_issuance: bool = False


# There is a problem with make dict from instance of BaseModel EnvConstants
# where keys are instances of Enum (s3 field is dict, not AccountConfigsRegistry).
class EnvConstants(BaseModel):
    brands: list[str]
    domain_groups: list[str]
    markets: list[str]
    market_other: str
    brand_by_domain_group: dict[str, str]
    s3: dict[str, AccountConfig]
    domain_groups_config: dict[str, DomainGroupConfig]
    promotions_config: PromotionsConfig = Field(default_factory=PromotionsConfig)
    instance_id: InstanceId = InstanceId.development

    @property
    def domain_groups_by_brand(self) -> dict[str, list[str]]:
        result = defaultdict(list)
        for domain_group, brand in self.brand_by_domain_group.items():
            result[brand].append(domain_group)
        return result
