from django.db import models

from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.feature_flags.const import FeatureFlagName


class FeatureFlag(BaseDjangoModel):
    name: FeatureFlagName = models.CharField(max_length=255, choices=FeatureFlagName.choices)
    status = models.BooleanField(default=False)

