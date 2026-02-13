from rozert_pay.feature_flags.models import FeatureFlag
from rozert_pay.feature_flags.const import FeatureFlagName

def switch_feature_flag(name: FeatureFlagName, value: bool) -> None:
    FeatureFlag.objects.update_or_create(name=name, defaults={'value': value})
