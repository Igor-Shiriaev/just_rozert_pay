from rozert_pay.feature_flags.const import FeatureFlagName
from rozert_pay.feature_flags.models import FeatureFlag


def update_feature_flag_status(*, name: FeatureFlagName, status: bool) -> None:
    FeatureFlag.objects.filter(name=name).update(status=status)

def 
