from django.db import models

# Create your models here.
class FeatureFlag(BaseDjangoModel):
    name = models.CharField(max_length=255)
    value = models.BooleanField(default=False)