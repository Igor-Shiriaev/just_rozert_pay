

class RiskControlMixin:
    def enable_risk_control(self, request: HttpRequest, queryset: QuerySet[CustomerLimit]) -> None:
        update_feature_flag_status(name=FeatureFlagName.RISK_CONTROL_ENABLED, status=True)
        self.message_user(request, _("Risk control enabled successfully."))

    def disable_risk_control(self, request: HttpRequest, queryset: QuerySet[CustomerLimit]) -> None:
        update_feature_flag_status(name=FeatureFlagName.RISK_CONTROL_ENABLED, status=False)
        self.message_user(request, _("Risk control disabled successfully."))