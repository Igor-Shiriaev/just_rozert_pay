from rozert_pay.feature_flags.models import FeatureFlag
from rozert_pay.feature_flags.const import FeatureFlagName


def update_feature_flag(name: FeatureFlagName, status: bool) -> None:
    FeatureFlag.objects.filter(name=name).update(status=status)
