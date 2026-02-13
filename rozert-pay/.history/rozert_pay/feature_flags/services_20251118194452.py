from rozert_pay.feature_flags.const import FeatureFlagName
from rozert_pay.feature_flags.models import FeatureFlag


ACTIVE_LIMITS_CACHE_KEY: CacheKey = CacheKey("active_limits")
CACHE_TIMEOUT = timedelta(minutes=1)  # 1 minute


def update_feature_flag_status(*, name: FeatureFlagName, status: bool) -> None:
    FeatureFlag.objects.filter(name=name).update(status=status)


def get_feature_flag_status(*, name: FeatureFlagName) -> bool:
    return FeatureFlag.objects.filter(name=name).first().status
