from django.shortcuts import render

# Create your views here.

def switch_feature_flag(name: FeatureFlagName, value: bool) -> None: