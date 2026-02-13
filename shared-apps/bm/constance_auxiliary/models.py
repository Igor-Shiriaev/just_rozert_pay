from django.db import models
from django.db.models.fields import AutoField

from . import local_settings


class AbstractConstanceAuxiliaryPermissionsManagementFakeModel(models.Model):
    # This model is needed only for permissions management
    id = AutoField(primary_key=True)

    class Meta:
        abstract = True
        managed = False
        default_permissions = ()
        permissions = [
            (f'change_{name}', f'Can change {name} (custom)')
            for name in local_settings.FIELDS_WITH_OWN_CHANGE_PERMISSION
        ]
