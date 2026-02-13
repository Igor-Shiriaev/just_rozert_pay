from django.db import models

from rozert_pay.common.models import BaseDjangoModel
from rozert_pay.feature_flags.const import FeatureFlagName


# Create your models here.
class FeatureFlag(BaseDjangoModel):
    name: FeatureFlagName = models.CharField(max_length=255, )
    value = models.BooleanField(default=False)
