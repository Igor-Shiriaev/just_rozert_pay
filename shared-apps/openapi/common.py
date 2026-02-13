import os
from typing import (
    TypedDict,
    Any,
)

import yaml


class CurrencyConfig(TypedDict):
    name: str
    crypto: bool
    minor_unit_multiplier: int
    is_natively_supported: bool


class ResponsibleGamblingTimeout(TypedDict):
    products: list[str]


class ResponsibleGamblingConfig(TypedDict):
    timeouts: ResponsibleGamblingTimeout


class Favorites(TypedDict):
    types: list[str]


class Promotion(TypedDict):
    group_types: list[str]


class DataValues(TypedDict):
    languageCodes: list[str]
    currencies: list[CurrencyConfig]
    sportradarSportIds: dict[str, str]
    pinnacleSportsData: list[dict[str, Any]]
    oddinSportIds: dict[str, str]
    pythiaSportIds: dict[str, str]
    coreBrands: dict[str, int]
    coreMarkets: dict[str, int]
    coreDomainGroups: dict[str, int]
    responsible_gambling: ResponsibleGamblingConfig
    favorites: Favorites
    promotion: Promotion
    sex: list[str]
    userLevel: list[str]
    agreementType: list[str]
    countries: list[str]
    coreLicenses: dict[str, int]
    actionsRejectionCode: dict[str, int]


# NOTE: this should be in django utils directory.
def get_openapi_yaml_data_values() -> DataValues:
    from django.conf import settings

    filename = os.path.join(
        settings.PROJECT_COMMON_ROOT, 'api', 'data-values.yml'
    )
    with open(filename) as f:
        data_values = yaml.safe_load(f)
    return data_values
