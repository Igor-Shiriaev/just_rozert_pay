from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import (  # type: ignore[attr-defined]
    BaseUserCreationForm,
    SetUnusablePasswordMixin,
)
from django.utils.translation import gettext_lazy as _
from rozert_pay.account import models


class _CreateUserForm(SetUnusablePasswordMixin, BaseUserCreationForm):
    usable_password = SetUnusablePasswordMixin.create_usable_password_field()


@admin.register(models.User)
class UserAdmin(DjangoUserAdmin):
    # add_form = _CreateUserForm
    list_display = ("email", "first_name", "last_name", "is_staff")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-date_joined",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "usable_password", "password1", "password2"),
            },
        ),
    )

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return super().changeform_view(request, object_id, form_url, extra_context)
