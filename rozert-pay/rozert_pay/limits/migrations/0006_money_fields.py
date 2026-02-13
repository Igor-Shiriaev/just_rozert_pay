from decimal import Decimal

import rozert_pay.common.fields
from django.core.validators import MinValueValidator
from django.db import migrations
from rozert_pay.limits import const as limit_const


class Migration(migrations.Migration):
    dependencies = [
        (
            "limits",
            "0005_globalriskmerchantlimit_alter_customerlimit_category_and_more",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="customerlimit",
            name="min_operation_amount",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text="Minimum amount allowed for a single operation",
                null=True,
                validators=[MinValueValidator(Decimal("0.01"))],
                verbose_name=limit_const.VERBOSE_NAME_MIN_AMOUNT_SINGLE_OPERATION,
            ),
        ),
        migrations.AlterField(
            model_name="customerlimit",
            name="max_operation_amount",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text="Maximum amount allowed for a single operation",
                null=True,
                validators=[MinValueValidator(Decimal("0.01"))],
                verbose_name=limit_const.VERBOSE_NAME_MAX_AMOUNT_SINGLE_OPERATION,
            ),
        ),
        migrations.AlterField(
            model_name="customerlimit",
            name="total_successful_amount",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text="Maximum total amount of all successful operations for the specified period",
                null=True,
                validators=[MinValueValidator(Decimal("0.01"))],
                verbose_name="Total amount of successful operations per period",
            ),
        ),
        migrations.AlterField(
            model_name="merchantlimit",
            name="min_amount",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text="Minimum amount",
                null=True,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="merchantlimit",
            name="max_amount",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text="Maximum amount",
                null=True,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AlterField(
            model_name="merchantlimit",
            name="total_amount",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text="Total amount per period",
                null=True,
                validators=[MinValueValidator(0)],
            ),
        ),
    ]
