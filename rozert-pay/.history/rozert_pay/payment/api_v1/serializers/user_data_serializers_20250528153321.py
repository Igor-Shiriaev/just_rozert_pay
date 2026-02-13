import typing as ty
from copy import deepcopy
from typing import Literal

from rest_framework import serializers
from rest_framework.serializers import SerializerMetaclass
from rozert_pay.payment import entities


class UserDataSerializer(serializers.Serializer):
    email = serializers.EmailField(
        help_text="Customer email address",
    )
    phone = serializers.CharField(required=False)
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    post_code = serializers.CharField(required=False)
    city = serializers.CharField(required=False)
    country = serializers.CharField(required=False)
    state = serializers.CharField(required=False)
    address = serializers.CharField(required=False)
    language = serializers.CharField(
        help_text="Language code",
        max_length=2,
        min_length=2,
        required=False,
    )


_UserDataSerializerKey = Literal[
    "email",
    "phone",
    "first_name",
    "last_name",
    "post_code",
    "city",
    "country",
    "state",
    "address",
    "language",
]


assert set(ty.cast(ty.Any, _UserDataSerializerKey).__args__) == set(
    UserDataSerializer().get_fields().keys()
), "Ключи в _UserDataSerializerKey должны соответствовать полям UserDataSerializer"


assert set(entities.UserData.__annotations__) == set(
    UserDataSerializer().get_fields().keys()
), "Поля в UserDataSerializer должны соответствовать полям UserData"


class UserDataSerializerMixin(serializers.Serializer):
    user_data = UserDataSerializer()


def user_data_serializer_mixin_factory(
    required_fields: list[_UserDataSerializerKey],
) -> SerializerMetaclass:
    """
    Создает подкласс UserDataSerializer с указанными обязательными полями.

    Args:
        required_fields: Множество полей, которые должны быть обязательными

    Returns:
        Подкласс UserDataSerializer с настроенными обязательными полями
    """

    declared_fields = deepcopy(UserDataSerializer._declared_fields)

    # Some magic, because Field.__deepcopy__ resets state from Field._args/._kwargs parameters from __init__ method
    for name, f in declared_fields.items():
        field = ty.cast(ty.Any, f)

        if name in required_fields:
            field.required = True
            field._kwargs["required"] = True
        else:
            field.required = False
            field._kwargs["required"] = False

    CustomUserDataSerializer = SerializerMetaclass(
        "CustomUserDataSerializer",
        (serializers.Serializer,),
        deepcopy(declared_fields),
    )

    return SerializerMetaclass(
        "CustomUserDataSerializerMixin",
        (serializers.Serializer,),
        {
            "user_data": CustomUserDataSerializer(),
        },
    )
