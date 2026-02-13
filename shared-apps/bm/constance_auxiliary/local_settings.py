from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

FIELDS_WITH_OWN_CHANGE_PERMISSION = getattr(
    settings, 'CONSTANCE_AUXILIARY_FIELDS_WITH_OWN_CHANGE_PERMISSION', ()
)

if len(set(FIELDS_WITH_OWN_CHANGE_PERMISSION)) != len(FIELDS_WITH_OWN_CHANGE_PERMISSION):
    raise ImproperlyConfigured(
        'CONSTANCE_AUXILIARY_FIELDS_WITH_OWN_CHANGE_PERMISSION has duplicate items'
    )


FIELD_VALIDATORS = getattr(settings, 'CONSTANCE_AUXILIARY_FIELD_VALIDATORS', {})
