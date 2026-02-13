from django.shortcuts import render


def switch_feature_flag(name: FeatureFlagName, value: bool) -> None:
    FeatureFlag.objects.update_or_create(name=name, defaults={'value': value})