from django.db import models
from rozert_pay.common.models import BaseDjangoModel

class RiskSettings(BaseDjangoModel):
    risk_limits_enabled: bool = models.BooleanField(default=True, db_index=True)

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        from rozert_pay.limits.services.risk_settings import invalidate_risk_settings_cache
        invalidate_risk_settings_cache()