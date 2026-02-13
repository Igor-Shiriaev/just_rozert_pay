from datetime import timedelta
from rozert_pay.common.helpers.cache import CacheKey, memory_cache_get_set, memory_cache_invalidate
from rozert_pay.feature_flags.const import FeatureFlagName
from rozert_pay.feature_flags.models import FeatureFlag


FEATURE_FLAGS_CACHE_KEY: CacheKey = CacheKey("feature_flags_{name}")
CACHE_TIMEOUT = timedelta(minutes=1)


def update_feature_flag_status(*, name: FeatureFlagName, status: bool) -> None:
    FeatureFlag.objects.filter(name=name).update(status=status)
    memory_cache_invalidate(FEATURE_FLAGS_CACHE_KEY.format(name=name))


def get_feature_flag_status(*, name: FeatureFlagName) -> bool:
    def _fetch_feature_flag_status() -> bool:
        return FeatureFlag.objects.get(name=name).status

    return memory_cache_get_set(
        key=FEATURE_FLAGS_CACHE_KEY.format(name=name),
        tp=bool,
        on_miss=_fetch_feature_flag_status,
        ttl=CACHE_TIMEOUT,
    )
