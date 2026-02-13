"""
Define custom user model with email as unique identifier.
"""
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from rozert_pay.payment.permissions import CommonUserPermissions


# Manager and QS
class UserManager(BaseUserManager["User"]):
    def create_user(self, email: str, password: str) -> "User":
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email))
        user.set_password(password)  # type: ignore
        user.save()
        return user  # type: ignore

    def create_superuser(self, email: str, password: str) -> "User":
        user = self.create_user(email, password)
        user.is_superuser = True
        user.is_staff = True
        user.save()
        return user


class User(AbstractUser):
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()  # type: ignore

    email = models.EmailField(unique=True)
    username = None  # type: ignore

    class Meta:
        permissions = [
            CommonUserPermissions.CAN_VIEW_PERSONAL_DATA.to_meta_tuple(),
            CommonUserPermissions.CAN_VIEW_WALLET_CREDENTIALS.to_meta_tuple(),
            CommonUserPermissions.CAN_VIEW_CUSTOMER_CARD_DATA.to_meta_tuple(),
        ]

    def __str__(self) -> str:
        return self.email
