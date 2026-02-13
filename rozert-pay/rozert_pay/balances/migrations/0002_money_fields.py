from decimal import Decimal

import rozert_pay.common.fields
from django.core.validators import MinValueValidator
from django.db import migrations
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):
    dependencies = [
        ("balances", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="balancetransaction",
            name="amount2",
            field=rozert_pay.common.fields.MoneyField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="balancetransaction",
            name="operational_before2",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text=_(
                    "The total funds (including pending and frozen) before the operation."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="balancetransaction",
            name="operational_after2",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text=_("The total funds after the operation."),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="balancetransaction",
            name="frozen_before2",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text=_(
                    "The portion of operational funds that was frozen before the operation."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="balancetransaction",
            name="frozen_after2",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text=_(
                    "The portion of operational funds that is frozen after the operation."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="balancetransaction",
            name="pending_before2",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text=_(
                    "The portion of operational funds awaiting settlement before the operation."
                ),
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="balancetransaction",
            name="pending_after2",
            field=rozert_pay.common.fields.MoneyField(
                blank=True,
                help_text=_(
                    "The portion of operational funds awaiting settlement after the operation."
                ),
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="rollingreservehold",
            name="amount",
            field=rozert_pay.common.fields.MoneyField(
                validators=[MinValueValidator(Decimal("0.01"))]
            ),
        ),
    ]
